"""Hybrid Automated + Interactive Target and Internal Render Resolution Analyzer."""
from __future__ import annotations

from collections import deque
from typing import Any, Optional
import cv2
import numpy as np

from frametime_analyzer.models import AnalyzerConfig, FramePacket, StairStepSample


# Common 16:9 and console/PC internal render resolution tiers (vertical heights)
STANDARD_HEIGHT_TIERS: list[tuple[int, str]] = [
    (360, "360p"),
    (480, "480p"),
    (540, "540p"),
    (600, "600p"),
    (720, "720p"),
    (792, "792p"),
    (810, "810p"),
    (864, "864p"),
    (900, "900p"),
    (972, "972p"),
    (1080, "1080p"),
    (1152, "1152p"),
    (1260, "1260p"),
    (1296, "1296p"),
    (1440, "1440p"),
    (1512, "1512p"),
    (1620, "1620p"),
    (1800, "1800p"),
    (1944, "1944p"),
    (2160, "2160p (4K)"),
]


def match_standard_resolution_tier(height: int, snap_tolerance_px: int = 28) -> tuple[int, str]:
    """Match an estimated vertical pixel height to the closest standard tier if within tolerance."""
    best_h, best_label = height, f"~{height}p"
    best_dist = 999999
    for tier_h, label in STANDARD_HEIGHT_TIERS:
        dist = abs(height - tier_h)
        if dist < best_dist:
            best_dist = dist
            best_h, best_label = tier_h, label
    if best_dist <= snap_tolerance_px:
        return best_h, best_label
    return height, f"~{height}p"


class ResolutionAnalyzer:
    """Estimates Target (Output) Resolution and Internal 3D Render Resolution from video frames."""

    def __init__(self, config: Optional[AnalyzerConfig] = None) -> None:
        self.config = config or AnalyzerConfig()
        self._scale_history: deque[float] = deque(maxlen=max(1, self.config.drs_smoothing_window))
        self._last_result: Optional[dict[str, Any]] = None

    def reset(self) -> None:
        self._scale_history.clear()
        self._last_result = None

    def detect_active_target_bounds(self, bgr: np.ndarray) -> tuple[int, int, int, int]:
        """Detect active viewport bounds (x0, y0, x1, y1), stripping black letterbox/pillarbox bars."""
        h, w = bgr.shape[:2]
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        row_max = np.percentile(gray, 98, axis=1)
        col_max = np.percentile(gray, 98, axis=0)
        black_threshold = 12.0

        active_rows = np.where(row_max > black_threshold)[0]
        active_cols = np.where(col_max > black_threshold)[0]

        if len(active_rows) < h // 4 or len(active_cols) < w // 4:
            return 0, 0, w, h

        y0 = int(active_rows[0])
        y1 = int(active_rows[-1]) + 1
        x0 = int(active_cols[0])
        x1 = int(active_cols[-1]) + 1

        # Snap near-full bounds (within 6 pixels) to container edges
        if y0 <= 6:
            y0 = 0
        if h - y1 <= 6:
            y1 = h
        if x0 <= 6:
            x0 = 0
        if w - x1 <= 6:
            x1 = w

        return x0, y0, x1, y1

    def _build_3d_viewport_gray(self, bgr: np.ndarray, bounds: tuple[int, int, int, int]) -> np.ndarray:
        """Extract active grayscale viewport and mask out configured HUD boxes."""
        x0, y0, x1, y1 = bounds
        crop = bgr[y0:y1, x0:x1]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
        ch, cw = gray.shape

        # Zero out gradients inside HUD exclusion boxes or HUD reference box so only 3D scene is measured
        boxes = list(self.config.hud_exclusion_boxes)
        if self.config.hud_reference_box is not None:
            boxes.append(self.config.hud_reference_box)

        for bx1, by1, bx2, by2 in boxes:
            px1 = max(0, min(cw, int(round(bx1 * cw))))
            px2 = max(0, min(cw, int(round(bx2 * cw))))
            py1 = max(0, min(ch, int(round(by1 * ch))))
            py2 = max(0, min(ch, int(round(by2 * ch))))
            if px2 > px1 and py2 > py1:
                gray[py1:py2, px1:px2] = np.median(gray)

        return gray

    def _measure_normalized_edge_slope(self, gray: np.ndarray) -> tuple[float, float, float]:
        """Measure 1-pixel edge step concentration across monotonic edge ramps.

        When a step edge of contrast Delta_C is upscaled by factor S = H_target / H_render:
        - The peak 1-pixel difference at the ramp center is |g[x]| = Delta_C / S
        - The sum of same-sign differences across the 4-pixel monotonic ramp is Delta_C
        - Their ratio |g[x]| / RampSum(x) equals 1 / S = H_render / H_target.

        Returns:
            (estimated_scale_ratio, fwhm_px, confidence)
        """
        # Signed 1-pixel differences along X and Y
        gx = gray[:, 1:] - gray[:, :-1]
        gy = gray[1:, :] - gray[:-1, :]

        ratios_list: list[np.ndarray] = []

        # Analyze horizontal step transitions (along X)
        if gx.shape[1] >= 6:
            c = gx[:, 2:-2]
            abs_c = np.abs(c)
            sign_c = np.sign(c)
            # Peak of monotonic ramp (break ties on the first pixel of a symmetric 2-pixel step)
            is_peak_x = (abs_c > np.abs(gx[:, 1:-3])) & (abs_c >= np.abs(gx[:, 3:-1])) & (abs_c >= 12.0)
            # Sum of same-sign steps across [x-2, x-1, x, x+1, x+2]
            ramp_sum_x = (
                abs_c
                + np.abs(gx[:, 1:-3]) * (np.sign(gx[:, 1:-3]) == sign_c)
                + np.abs(gx[:, 3:-1]) * (np.sign(gx[:, 3:-1]) == sign_c)
                + np.abs(gx[:, 0:-4]) * (np.sign(gx[:, 0:-4]) == sign_c)
                + np.abs(gx[:, 4:]) * (np.sign(gx[:, 4:]) == sign_c)
            )
            valid_x = is_peak_x & (ramp_sum_x >= 60.0)
            if np.any(valid_x):
                ratios_list.append(abs_c[valid_x] / ramp_sum_x[valid_x])

        # Analyze vertical step transitions (along Y)
        if gy.shape[0] >= 6:
            cy = gy[2:-2, :]
            abs_cy = np.abs(cy)
            sign_cy = np.sign(cy)
            is_peak_y = (abs_cy > np.abs(gy[1:-3, :])) & (abs_cy >= np.abs(gy[3:-1, :])) & (abs_cy >= 12.0)
            ramp_sum_y = (
                abs_cy
                + np.abs(gy[1:-3, :]) * (np.sign(gy[1:-3, :]) == sign_cy)
                + np.abs(gy[3:-1, :]) * (np.sign(gy[3:-1, :]) == sign_cy)
                + np.abs(gy[0:-4, :]) * (np.sign(gy[0:-4, :]) == sign_cy)
                + np.abs(gy[4:, :]) * (np.sign(gy[4:, :]) == sign_cy)
            )
            valid_y = is_peak_y & (ramp_sum_y >= 60.0)
            if np.any(valid_y):
                ratios_list.append(abs_cy[valid_y] / ramp_sum_y[valid_y])

        if not ratios_list:
            return 1.0, 1.0, 0.25

        all_ratios = np.concatenate(ratios_list)
        edge_count = int(all_ratios.size)
        if edge_count < 10:
            return 1.0, 1.0, 0.25

        # Blending the mean and 75th percentile averages across both half-pixel and 1/6-pixel phases
        mean_ratio = float(np.mean(all_ratios))
        p75_ratio = float(np.percentile(all_ratios, 75))
        raw_scale = 0.50 * mean_ratio + 0.50 * p75_ratio

        scale_ratio = float(np.clip(raw_scale, 0.25, 1.0))
        fwhm_px = 1.0 / max(0.25, scale_ratio)
        confidence = float(np.clip(min(1.0, edge_count / 250.0) * 0.85 + 0.15, 0.3, 0.98))
        return scale_ratio, fwhm_px, confidence

    def _measure_spectral_and_residual_scale(self, gray: np.ndarray) -> float:
        """Measure scale-space re-upscaling gradient retention to cross-validate edge slope."""
        h, w = gray.shape
        # Work on a central crop up to 512x512 for fast scale-space testing
        ch = min(h, 512)
        cw = min(w, 512)
        y0 = (h - ch) // 2
        x0 = (w - cw) // 2
        patch = gray[y0 : y0 + ch, x0 : x0 + cw]

        gx = cv2.Sobel(patch, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(patch, cv2.CV_32F, 0, 1, ksize=3)
        base_grad = np.hypot(gx, gy)
        base_energy = float(np.sum(base_grad))
        if base_energy < 1e-3:
            return 1.0

        # Test how much gradient energy survives a 0.5x downscale-upscale cycle:
        # A native 1.0x sharp image loses a large fraction of gradient energy at 0.5x;
        # an already-upscaled 0.5x image retains almost all of its gradient energy.
        half_w = max(8, cw // 2)
        half_h = max(8, ch // 2)
        down = cv2.resize(patch, (half_w, half_h), interpolation=cv2.INTER_AREA)
        re_up = cv2.resize(down, (cw, ch), interpolation=cv2.INTER_LINEAR)
        rx = cv2.Sobel(re_up, cv2.CV_32F, 1, 0, ksize=3)
        ry = cv2.Sobel(re_up, cv2.CV_32F, 0, 1, ksize=3)
        re_energy = float(np.sum(np.hypot(rx, ry)))

        retention_at_half = re_energy / base_energy
        # For linear upscaling: retention_at_half ~ 0.52 at native 1.0x, ~0.85+ at <=0.5x
        estimated_scale = float(np.clip((0.92 - retention_at_half) / 0.38, 0.25, 1.0))
        return estimated_scale

    def process_frame(self, packet: FramePacket, force: bool = False) -> dict[str, Any]:
        """Estimate target and internal render resolution for the given frame."""
        h_cont, w_cont = packet.height, packet.width
        container_res = (w_cont, h_cont)

        if not self.config.detect_resolution:
            return {
                "container_resolution": container_res,
                "target_resolution": container_res,
                "estimated_render_resolution": container_res,
                "render_scale_percent": 100.0,
                "resolution_tier_label": f"{h_cont}p",
                "resolution_confidence": 1.0,
                "esf_fwhm_px": 1.0,
                "spectral_cutoff_ratio": 1.0,
            }

        should_sample = (
            force
            or self._last_result is None
            or (packet.frame_index % max(1, self.config.resolution_sample_interval) == 0)
        )
        if not should_sample and self._last_result is not None:
            return self._last_result

        x0, y0, x1, y1 = self.detect_active_target_bounds(packet.raw_bgr)
        target_w = max(1, x1 - x0)
        target_h = max(1, y1 - y0)
        target_res = (target_w, target_h)

        gray_3d = self._build_3d_viewport_gray(packet.raw_bgr, (x0, y0, x1, y1))
        slope_scale, fwhm_px, confidence = self._measure_normalized_edge_slope(gray_3d)
        spectral_scale = self._measure_spectral_and_residual_scale(gray_3d)

        # Normalized Edge-Spread slope is a direct physical measurement of upscale ramp width;
        # use it directly when sufficient strong edges exist, blending spectral scale only on low-edge scenes.
        if confidence >= 0.55:
            combined_scale = slope_scale
        else:
            combined_scale = 0.70 * slope_scale + 0.30 * spectral_scale
        self._scale_history.append(combined_scale)

        smoothed_scale = float(np.median(self._scale_history))
        raw_render_h = int(round(target_h * smoothed_scale))
        snapped_h, tier_label = match_standard_resolution_tier(raw_render_h, snap_tolerance_px=max(16, target_h // 45))
        snapped_h = min(target_h, max(180, snapped_h))
        aspect = target_w / float(target_h)
        snapped_w = int(round((snapped_h * aspect) / 2.0) * 2)

        actual_scale_pct = (snapped_h / float(target_h)) * 100.0

        result = {
            "container_resolution": container_res,
            "target_resolution": target_res,
            "estimated_render_resolution": (snapped_w, snapped_h),
            "render_scale_percent": round(actual_scale_pct, 1),
            "resolution_tier_label": tier_label,
            "resolution_confidence": round(confidence, 2),
            "esf_fwhm_px": round(fwhm_px, 2),
            "spectral_cutoff_ratio": round(spectral_scale, 2),
        }
        self._last_result = result
        return result

    def count_edge_stair_steps(
        self,
        bgr: np.ndarray,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
    ) -> StairStepSample:
        """Digital Foundry-style stair-step pixel counter along a selected edge segment."""
        h_cont, w_cont = bgr.shape[:2]
        tx0, ty0, tx1, ty1 = self.detect_active_target_bounds(bgr)
        target_w = max(1, tx1 - tx0)
        target_h = max(1, ty1 - ty0)

        x1 = int(np.clip(x1, 0, w_cont - 1))
        x2 = int(np.clip(x2, 0, w_cont - 1))
        y1 = int(np.clip(y1, 0, h_cont - 1))
        y2 = int(np.clip(y2, 0, h_cont - 1))

        dx = x2 - x1
        dy = y2 - y1
        abs_dx = abs(dx)
        abs_dy = abs(dy)
        dominant_axis = "horizontal" if abs_dx >= abs_dy else "vertical"
        span_pixels = max(abs_dx, abs_dy, 1)

        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)

        # Sample intensity and cross-edge centroid along the dominant axis
        num_samples = span_pixels + 1
        xs = np.linspace(x1, x2, num_samples)
        ys = np.linspace(y1, y2, num_samples)

        # Unit normal vector perpendicular to the segment
        length = float(np.hypot(dx, dy)) or 1.0
        nx = -dy / length
        ny = dx / length

        edge_profile: list[float] = []
        perp_slopes: list[float] = []
        half_strip = 5

        for i in range(num_samples):
            cx, cy = xs[i], ys[i]
            strip_vals: list[float] = []
            for offset in range(-half_strip, half_strip + 1):
                sx = int(np.clip(round(cx + nx * offset), 0, w_cont - 1))
                sy = int(np.clip(round(cy + ny * offset), 0, h_cont - 1))
                strip_vals.append(float(gray[sy, sx]))

            strip_arr = np.array(strip_vals, dtype=np.float32)
            strip_grad = np.abs(np.diff(strip_arr))
            strip_contrast = float(np.max(strip_arr) - np.min(strip_arr))
            if strip_contrast > 10.0:
                perp_slopes.append(float(np.max(strip_grad) / strip_contrast))

            # Intensity right on the user's line
            ix = int(np.clip(round(cx), 0, w_cont - 1))
            iy = int(np.clip(round(cy), 0, h_cont - 1))
            edge_profile.append(float(gray[iy, ix]))

        prof_arr = np.array(edge_profile, dtype=np.float32)
        grad_arr = np.abs(np.diff(prof_arr)) if len(prof_arr) > 1 else np.array([0.0], dtype=np.float32)

        # Count discrete stair-step transitions along the edge profile
        grad_thresh = max(1.5, float(np.percentile(grad_arr, 55)) * 0.55)
        step_positions: list[int] = []
        for idx, g_val in enumerate(grad_arr):
            if g_val >= grad_thresh:
                # Avoid double-counting a 2-pixel bilinear ramp as 2 separate steps if we are at local peak
                is_local_peak = (
                    (idx == 0 or g_val >= grad_arr[idx - 1])
                    and (idx == len(grad_arr) - 1 or g_val >= grad_arr[idx + 1])
                )
                if is_local_peak:
                    step_positions.append(int(idx))

        raw_step_ratio = len(step_positions) / float(span_pixels) if span_pixels > 0 else 1.0
        perp_scale = float(np.percentile(perp_slopes, 85)) if perp_slopes else raw_step_ratio

        # Combine direct step count and perpendicular edge transition width
        if 0.25 <= raw_step_ratio <= 1.0 and abs(raw_step_ratio - perp_scale) < 0.22:
            scale_ratio = raw_step_ratio
        else:
            scale_ratio = float(np.clip(0.5 * raw_step_ratio + 0.5 * perp_scale, 0.25, 1.0))

        counted_steps = max(1, min(span_pixels, int(round(scale_ratio * span_pixels))))
        scale_ratio = counted_steps / float(span_pixels)

        est_h = int(round(target_h * scale_ratio))
        snapped_h, tier_label = match_standard_resolution_tier(est_h, snap_tolerance_px=max(18, target_h // 40))
        snapped_w = int(round((snapped_h * (target_w / float(target_h))) / 2.0) * 2)

        return StairStepSample(
            x1=x1,
            y1=y1,
            x2=x2,
            y2=y2,
            dominant_axis=dominant_axis,
            span_pixels=span_pixels,
            counted_steps=counted_steps,
            step_positions=step_positions,
            edge_profile=[round(v, 2) for v in edge_profile],
            gradient_profile=[round(float(v), 2) for v in grad_arr],
            container_width=w_cont,
            container_height=h_cont,
            target_width=target_w,
            target_height=target_h,
            estimated_render_width=snapped_w,
            estimated_render_height=snapped_h,
            scale_ratio=round(scale_ratio, 4),
            confidence=0.90 if perp_slopes else 0.70,
            standard_Tier_match=tier_label,
        )

    def auto_find_stair_step_candidates(self, bgr: np.ndarray, max_candidates: int = 5) -> list[StairStepSample]:
        """Automatically detect high-contrast diagonal edges suitable for stair-step pixel counting."""
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 80, 180)
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180.0,
            threshold=35,
            minLineLength=24,
            maxLineGap=4,
        )
        if lines is None:
            return []

        candidates: list[StairStepSample] = []
        for line in lines[:, 0, :]:
            x1, y1, x2, y2 = int(line[0]), int(line[1]), int(line[2]), int(line[3])
            dx, dy = abs(x2 - x1), abs(y2 - y1)
            span = max(dx, dy)
            if span < 20:
                continue
            angle_deg = float(np.degrees(np.arctan2(dy, dx)))
            # Ideal stair-step edges are shallow diagonals (8..38 deg or 52..82 deg)
            if (8.0 <= angle_deg <= 38.0) or (52.0 <= angle_deg <= 82.0):
                sample = self.count_edge_stair_steps(bgr, x1, y1, x2, y2)
                candidates.append(sample)
                if len(candidates) >= max_candidates:
                    break

        return candidates
