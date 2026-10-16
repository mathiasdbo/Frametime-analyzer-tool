"""Screen tearing detection via temporal row-difference step analysis and seam discontinuity."""
from __future__ import annotations

from typing import Optional
import numpy as np

from frametime_analyzer.models import AnalyzerConfig, FramePacket


class TearingDetector:
    """Detects horizontal screen tear lines and returns their Y-coordinates in native resolution."""

    def __init__(self, config: Optional[AnalyzerConfig] = None) -> None:
        self.config = config or AnalyzerConfig()
        self._prev_luma: Optional[np.ndarray] = None

    def reset(self) -> None:
        self._prev_luma = None

    def process_frame(self, packet: FramePacket) -> tuple[bool, list[int]]:
        """Analyze frame against previous frame for horizontal tear lines.

        Returns:
            (is_torn, tear_lines_native_y)
        """
        if not self.config.detect_tearing:
            return False, []

        luma = packet.luma_small
        if luma is None:
            return False, []

        if self._prev_luma is None or packet.frame_index == 0:
            self._prev_luma = luma.copy()
            return False, []

        curr = luma.astype(np.float32)
        prev = self._prev_luma.astype(np.float32)
        self._prev_luma = luma.copy()

        h_small, _ = curr.shape
        native_h = packet.height
        scale_y = native_h / float(h_small)

        # 1. Temporal row-wise Mean Absolute Difference R(y)
        row_diff = np.mean(np.abs(curr - prev), axis=1)  # shape: (h_small,)
        overall_diff = float(np.mean(row_diff))
        if overall_diff < self.config.noise_floor_luma * 0.5:
            return False, []

        # 2. Temporal seam anomaly S(y): new horizontal discontinuity at row y not present in prev frame
        curr_vgrad = np.abs(curr[1:, :] - curr[:-1, :])
        prev_vgrad = np.abs(prev[1:, :] - prev[:-1, :])
        seam_anomaly = np.mean(np.maximum(0.0, curr_vgrad - prev_vgrad), axis=1)  # shape: (h_small - 1,)

        # 3. Step transition in R(y) using a sliding window above and below row y
        win = max(6, h_small // 20)
        margin = max(win, int(round(h_small * 0.05)))
        if h_small <= 2 * margin + 2:
            return False, []

        step_scores = np.zeros(h_small - 1, dtype=np.float32)
        for y in range(margin, h_small - margin):
            above_p90 = float(np.percentile(row_diff[y - win : y], 90))
            below_p90 = float(np.percentile(row_diff[y : y + win], 90))
            step_mag = abs(above_p90 - below_p90)
            min_side = min(above_p90, below_p90)
            max_side = max(above_p90, below_p90)

            # Classic tear signature: one side is static (duplicate) while the other side updated.
            local_jump = abs(float(row_diff[y]) - float(row_diff[y - 1]))
            is_half_static = (
                min_side < self.config.noise_floor_luma * 1.5
                and max_side > self.config.tear_min_region_diff
            )
            if is_half_static:
                quiet_factor = self.config.noise_floor_luma / (min_side + self.config.noise_floor_luma * 0.25)
                step_scores[y - 1] = step_mag * quiet_factor + local_jump * 2.0 + seam_anomaly[y - 1] * 1.5

        # Check local peaks in step_scores combined with local seam_anomaly z-score
        seam_median = float(np.median(seam_anomaly))
        seam_mad = float(np.median(np.abs(seam_anomaly - seam_median))) + 1e-4
        seam_z = (seam_anomaly - seam_median) / (1.4826 * seam_mad)

        tear_lines_native: list[int] = []
        min_peak_distance = max(12, h_small // 8)

        candidate_indices = np.argsort(step_scores)[::-1]
        selected_small_y: list[int] = []

        for idx in candidate_indices:
            score = float(step_scores[idx])
            if score < self.config.tear_min_region_diff * 2.0:
                break

            y_row = int(idx + 1)
            above_global = float(np.percentile(row_diff[:y_row], 92))
            below_global = float(np.percentile(row_diff[y_row:], 92))
            min_glob = min(above_global, below_global)
            max_glob = max(above_global, below_global)

            half_static_global = (
                min_glob < self.config.noise_floor_luma * 1.8
                and max_glob > self.config.tear_min_region_diff
                and float(seam_z[idx]) >= 2.0
            )

            if half_static_global:
                if all(abs(y_row - prev_y) >= min_peak_distance for prev_y in selected_small_y):
                    selected_small_y.append(y_row)
                    native_y = int(round(y_row * scale_y))
                    tear_lines_native.append(native_y)
                    if len(tear_lines_native) >= 2:
                        break

        tear_lines_native.sort()
        return len(tear_lines_native) > 0, tear_lines_native
