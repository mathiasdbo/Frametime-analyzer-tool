"""Tile-based duplicate frame, frametime, and frame-pacing detector."""
from __future__ import annotations

from collections import deque
from typing import Optional
import numpy as np

from frametime_analyzer.models import AnalyzerConfig, FramePacket


class FrametimeDetector:
    """Detects duplicate/dropped frames and calculates frametimes, rolling FPS, and 1%/0.1% lows."""

    def __init__(self, config: Optional[AnalyzerConfig] = None) -> None:
        self.config = config or AnalyzerConfig()
        self._prev_luma: Optional[np.ndarray] = None
        self._mask: Optional[np.ndarray] = None
        self._motion_ema: float = 0.0
        self._initialized_ema: bool = False

        # Frame pacing state
        self._accumulated_ms: float = 0.0
        self._last_completed_frametime_ms: float = 16.67
        self._unique_window: deque[tuple[float, int]] = deque()  # (timestamp_ms, is_unique)
        self._unique_frametimes_ms: deque[float] = deque(maxlen=1200)

    def reset(self) -> None:
        self._prev_luma = None
        self._mask = None
        self._motion_ema = 0.0
        self._initialized_ema = False
        self._accumulated_ms = 0.0
        self._last_completed_frametime_ms = 16.67
        self._unique_window.clear()
        self._unique_frametimes_ms.clear()

    def _get_or_build_mask(self, shape: tuple[int, int]) -> np.ndarray:
        """Build a boolean mask (True = include in 3D motion analysis, False = masked HUD)."""
        if self._mask is not None and self._mask.shape == shape:
            return self._mask

        h, w = shape
        mask = np.ones((h, w), dtype=bool)
        for x1_n, y1_n, x2_n, y2_n in self.config.hud_exclusion_boxes:
            x1 = max(0, min(w, int(round(x1_n * w))))
            x2 = max(0, min(w, int(round(x2_n * w))))
            y1 = max(0, min(h, int(round(y1_n * h))))
            y2 = max(0, min(h, int(round(y2_n * h))))
            if x2 > x1 and y2 > y1:
                mask[y1:y2, x1:x2] = False

        self._mask = mask
        return mask

    def process_frame(self, packet: FramePacket) -> dict[str, float | bool]:
        """Process a single frame and return duplicate status and timing metrics."""
        luma = packet.luma_small
        if luma is None:
            raise ValueError("FramePacket.luma_small must be populated before FrametimeDetector.process_frame")

        default_dt_ms = 1000.0 / max(1.0, packet.container_fps)
        dt_ms = packet.duration_ms if packet.duration_ms > 0.1 else default_dt_ms

        if self._prev_luma is None or packet.frame_index == 0:
            self._prev_luma = luma.copy()
            self._accumulated_ms = dt_ms
            self._last_completed_frametime_ms = dt_ms
            self._unique_window.append((packet.timestamp_ms, 1))
            self._unique_frametimes_ms.append(dt_ms)
            return {
                "is_duplicate": False,
                "frametime_ms": dt_ms,
                "rolling_fps": packet.container_fps,
                "instant_fps": 1000.0 / dt_ms,
                "fps_1_percent_low": packet.container_fps,
                "fps_0_1_percent_low": packet.container_fps,
                "mean_luma_diff": 0.0,
                "p95_tile_diff": 0.0,
                "adaptive_threshold": self.config.noise_floor_luma,
            }

        mask = self._get_or_build_mask(luma.shape)
        diff_img = np.abs(luma.astype(np.float32) - self._prev_luma.astype(np.float32))

        # Apply HUD exclusion mask
        masked_diff = diff_img * mask
        active_pixels = max(1, int(np.count_nonzero(mask)))
        mean_diff = float(np.sum(masked_diff) / active_pixels)

        # Compute tile-based statistics (robust against isolated HUD animations)
        h, w = luma.shape
        rows = max(1, self.config.grid_rows)
        cols = max(1, self.config.grid_cols)
        tile_h = max(1, h // rows)
        tile_w = max(1, w // cols)

        tile_means: list[float] = []
        for r in range(rows):
            y0 = r * tile_h
            y1 = h if r == rows - 1 else (r + 1) * tile_h
            for c in range(cols):
                x0 = c * tile_w
                x1 = w if c == cols - 1 else (c + 1) * tile_w
                tile_mask = mask[y0:y1, x0:x1]
                cnt = int(np.count_nonzero(tile_mask))
                if cnt > (tile_h * tile_w) // 4:
                    tile_means.append(float(np.sum(diff_img[y0:y1, x0:x1] * tile_mask) / cnt))

        if tile_means:
            tile_arr = np.array(tile_means, dtype=np.float32)
            p95_tile_diff = float(np.percentile(tile_arr, 95))
            p65_tile_diff = float(np.percentile(tile_arr, 65))
            active_tile_fraction = float(np.mean(tile_arr > (self.config.noise_floor_luma * 2.2)))
        else:
            p95_tile_diff = mean_diff
            p65_tile_diff = mean_diff
            active_tile_fraction = 1.0 if mean_diff > self.config.noise_floor_luma else 0.0

        # Effective scene motion metric suppresses isolated single-tile HUD motion
        effective_diff = p65_tile_diff if active_tile_fraction < 0.15 else mean_diff

        if not self._initialized_ema and effective_diff > self.config.noise_floor_luma:
            self._motion_ema = effective_diff
            self._initialized_ema = True

        # Calculate adaptive threshold
        relative_thresh = self.config.relative_drop_ratio * self._motion_ema
        adaptive_threshold = max(
            self.config.noise_floor_luma,
            min(relative_thresh, self.config.noise_floor_luma * 6.0),
        )

        # Classification: a frame is duplicate if effective_diff falls below the adaptive threshold
        is_duplicate = bool(effective_diff < adaptive_threshold)

        if is_duplicate:
            self._accumulated_ms += dt_ms
            # Gently decay EMA during long static pauses so subtle movement can wake it up
            self._motion_ema = max(self.config.noise_floor_luma, self._motion_ema * 0.96)
            self._unique_window.append((packet.timestamp_ms, 0))
            displayed_frametime_ms = max(self._last_completed_frametime_ms, self._accumulated_ms)
        else:
            # Unique frame arrived: finalize the frametime of the previous unique frame
            completed_ft_ms = self._accumulated_ms if self._accumulated_ms > 0.0 else dt_ms
            self._last_completed_frametime_ms = completed_ft_ms
            self._unique_frametimes_ms.append(completed_ft_ms)
            self._accumulated_ms = dt_ms
            displayed_frametime_ms = completed_ft_ms

            # Update EMA only on unique frames so 30fps cadence doesn't drag EMA down
            alpha = self.config.ema_alpha
            self._motion_ema = (1.0 - alpha) * self._motion_ema + alpha * effective_diff
            self._unique_window.append((packet.timestamp_ms, 1))
            self._prev_luma = luma.copy()

        # Maintain 1000ms sliding window for rolling FPS
        window_span_ms = 1000.0
        cutoff_ms = packet.timestamp_ms - window_span_ms + (dt_ms * 0.5)
        while len(self._unique_window) > 1 and self._unique_window[0][0] < cutoff_ms:
            self._unique_window.popleft()

        expected_frames_in_1s = max(1, int(round(packet.container_fps)))
        while len(self._unique_window) > expected_frames_in_1s:
            self._unique_window.popleft()

        unique_count = sum(flag for _, flag in self._unique_window)
        actual_window_frames = len(self._unique_window)
        if packet.timestamp_ms < 980.0 and actual_window_frames < expected_frames_in_1s and actual_window_frames > 0:
            rolling_fps = float(unique_count) * (packet.container_fps / float(actual_window_frames))
        else:
            rolling_fps = float(unique_count)

        instant_fps = 1000.0 / max(1.0, displayed_frametime_ms)
        fps_1_low, fps_0_1_low = self._compute_low_percentiles(packet.container_fps)

        return {
            "is_duplicate": is_duplicate,
            "frametime_ms": float(displayed_frametime_ms),
            "rolling_fps": float(rolling_fps),
            "instant_fps": float(instant_fps),
            "fps_1_percent_low": float(fps_1_low),
            "fps_0_1_percent_low": float(fps_0_1_low),
            "mean_luma_diff": float(mean_diff),
            "p95_tile_diff": float(p95_tile_diff),
            "adaptive_threshold": float(adaptive_threshold),
        }

    def _compute_low_percentiles(self, default_fps: float) -> tuple[float, float]:
        if not self._unique_frametimes_ms:
            return default_fps, default_fps
        ft_arr = np.array(self._unique_frametimes_ms, dtype=np.float32)
        p99_ft = float(np.percentile(ft_arr, 99.0))
        p999_ft = float(np.percentile(ft_arr, 99.9))
        return 1000.0 / max(1.0, p99_ft), 1000.0 / max(1.0, p999_ft)
