"""Studio-grade Digital Foundry / TrDrop style RGBA HUD renderer."""
from __future__ import annotations

from collections import deque
from typing import Optional
import cv2
import numpy as np

from frametime_analyzer.models import FrameMetrics
from frametime_analyzer.render.platform_logos import draw_platform_badge


class HUDRenderer:
    """Renders anti-aliased RGBA performance and resolution overlays at any resolution."""

    def __init__(
        self,
        fps_history_len: int = 240,
        frametime_history_len: int = 80,
        show_tear_lines: bool = True,
        show_resolution_badge: bool = True,
        platform_name: str = "PS5",
        custom_logo_path: Optional[str] = None,
    ) -> None:
        self.fps_history_len = fps_history_len
        self.frametime_history_len = frametime_history_len
        self.show_tear_lines = show_tear_lines
        self.show_resolution_badge = show_resolution_badge
        self.platform_name = platform_name
        self.custom_logo_path = custom_logo_path

        self._fps_history: deque[float] = deque(maxlen=fps_history_len)
        self._tear_history: deque[bool] = deque(maxlen=fps_history_len)
        self._ft_history: deque[float] = deque(maxlen=frametime_history_len)
        self._res_scale_history: deque[float] = deque(maxlen=fps_history_len)

    def reset(self) -> None:
        self._fps_history.clear()
        self._tear_history.clear()
        self._ft_history.clear()
        self._res_scale_history.clear()

    def update_history(self, metrics: FrameMetrics) -> None:
        self._fps_history.append(metrics.rolling_fps)
        self._tear_history.append(metrics.is_torn)
        self._ft_history.append(metrics.frametime_ms)
        self._res_scale_history.append(metrics.render_scale_percent)

    def render_rgba_overlay(
        self,
        width: int,
        height: int,
        metrics: FrameMetrics,
        target_fps: float = 60.0,
        update: bool = True,
    ) -> np.ndarray:
        """Render a transparent (H, W, 4) BGRA/RGBA overlay buffer for the given frame metrics."""
        if update:
            self.update_history(metrics)

        overlay = np.zeros((height, width, 4), dtype=np.uint8)
        scale = max(0.65, min(2.5, height / 1080.0))

        # Colors in BGRA format
        col_emerald = (130, 232, 93, 255)      # #5DE882 DF Green
        col_cyan = (240, 210, 80, 255)         # Cyan accent for DRS scale
        col_amber = (60, 185, 255, 255)        # Warning amber
        col_red = (80, 75, 255, 255)           # Drop / tear red
        col_white = (250, 250, 250, 255)
        col_muted = (185, 190, 198, 230)
        col_grid = (110, 120, 130, 140)
        col_panel_bg = (18, 22, 28, 185)
        col_panel_border = (220, 225, 230, 210)

        fps_ratio = metrics.rolling_fps / max(1.0, target_fps)
        if fps_ratio >= 0.92:
            fps_color = col_emerald
        elif fps_ratio >= 0.75:
            fps_color = col_amber
        else:
            fps_color = col_red

        # ------------------------------------------------------------------
        # 1. Top-Right Console/Platform Logo Badge + FPS & Resolution Card
        # ------------------------------------------------------------------
        card_w = int(round(410 * scale))
        card_h = int(round((175 if self.show_resolution_badge else 115) * scale))
        margin = int(round(36 * scale))
        badge_h_space = int(round(42 * scale))
        cx0 = max(10, width - card_w - margin)
        cy0 = margin + badge_h_space
        cx1 = min(width - 10, cx0 + card_w)
        cy1 = min(height - 10, cy0 + card_h)

        if self.platform_name:
            draw_platform_badge(
                overlay,
                cx0,
                margin,
                scale,
                platform_name=self.platform_name,
                custom_logo_path=self.custom_logo_path,
            )

        self._draw_panel(overlay, cx0, cy0, cx1, cy1, col_panel_bg, col_panel_border, scale)

        # Big FPS number
        fps_str = f"{metrics.rolling_fps:04.1f}" if metrics.rolling_fps < 99.5 else f"{int(round(metrics.rolling_fps))}"
        self._draw_text(
            overlay,
            fps_str,
            (cx0 + int(round(20 * scale)), cy0 + int(round(62 * scale))),
            font_scale=1.75 * scale,
            color=fps_color,
            thickness=max(2, int(round(3.2 * scale))),
        )
        self._draw_text(
            overlay,
            "FPS",
            (cx0 + int(round(165 * scale)), cy0 + int(round(62 * scale))),
            font_scale=0.65 * scale,
            color=col_muted,
            thickness=max(1, int(round(1.5 * scale))),
        )

        # 1% Low & Frametime readout on right side of top card
        self._draw_text(
            overlay,
            f"1% LOW: {metrics.fps_1_percent_low:04.1f}",
            (cx0 + int(round(235 * scale)), cy0 + int(round(36 * scale))),
            font_scale=0.50 * scale,
            color=col_white,
            thickness=max(1, int(round(1.3 * scale))),
        )
        self._draw_text(
            overlay,
            f"FT: {metrics.frametime_ms:04.1f} ms",
            (cx0 + int(round(235 * scale)), cy0 + int(round(64 * scale))),
            font_scale=0.50 * scale,
            color=col_white,
            thickness=max(1, int(round(1.3 * scale))),
        )

        # Status badge (Duplicate / Tearing / V-Sync status)
        status_y = cy0 + int(round(95 * scale))
        if metrics.is_torn:
            status_text = f"TEARING DETECTED (Y={metrics.tear_line_y[0]}px)" if metrics.tear_line_y else "TEARING DETECTED"
            status_col = col_red
        elif metrics.is_duplicate:
            status_text = "FRAME REPEAT / DROP"
            status_col = col_amber
        else:
            status_text = "UNIQUE FRAME • V-SYNC CLEAN"
            status_col = col_emerald

        self._draw_text(
            overlay,
            status_text,
            (cx0 + int(round(20 * scale)), status_y),
            font_scale=0.45 * scale,
            color=status_col,
            thickness=max(1, int(round(1.2 * scale))),
        )

        # Resolution & DRS section
        if self.show_resolution_badge:
            sep_y = cy0 + int(round(110 * scale))
            cv2.line(
                overlay,
                (cx0 + int(round(16 * scale)), sep_y),
                (cx1 - int(round(16 * scale)), sep_y),
                col_grid,
                max(1, int(round(1 * scale))),
                cv2.LINE_AA,
            )
            tw, th = metrics.target_resolution
            rw, rh = metrics.estimated_render_resolution
            self._draw_text(
                overlay,
                f"TARGET OUTPUT: {tw}x{th} ({th}p)",
                (cx0 + int(round(20 * scale)), cy0 + int(round(134 * scale))),
                font_scale=0.46 * scale,
                color=col_muted,
                thickness=max(1, int(round(1.2 * scale))),
            )
            self._draw_text(
                overlay,
                f"EST. RENDER:   {rw}x{rh} ({metrics.resolution_tier_label} • {metrics.render_scale_percent:.0f}%)",
                (cx0 + int(round(20 * scale)), cy0 + int(round(158 * scale))),
                font_scale=0.48 * scale,
                color=col_cyan,
                thickness=max(1, int(round(1.4 * scale))),
            )

        # ------------------------------------------------------------------
        # 2. Frametime Step-Graph (Bottom-Left Above FPS Graph)
        # ------------------------------------------------------------------
        gx0 = margin
        ft_w = int(round(360 * scale))
        ft_h = int(round(105 * scale))
        fps_h = int(round(145 * scale))
        fps_w = int(round(620 * scale))

        fps_y1 = height - margin
        fps_y0 = max(10, fps_y1 - fps_h)
        ft_y1 = max(10, fps_y0 - int(round(28 * scale)))
        ft_y0 = max(10, ft_y1 - ft_h)

        self._draw_panel(overlay, gx0, ft_y0, gx0 + ft_w, ft_y1, col_panel_bg, col_panel_border, scale)
        self._draw_text(
            overlay,
            "FRAMETIME (MS)",
            (gx0 + int(round(8 * scale)), ft_y0 - int(round(8 * scale))),
            font_scale=0.48 * scale,
            color=col_white,
            thickness=max(1, int(round(1.3 * scale))),
        )

        # Reference lines at 16.7ms and 33.3ms (mapped into [0..50ms] range)
        max_ft_ms = 50.0
        for ref_ms, label in [(16.67, "16.7"), (33.33, "33.3")]:
            ry = int(round(ft_y1 - (ref_ms / max_ft_ms) * ft_h))
            if ft_y0 < ry < ft_y1:
                cv2.line(overlay, (gx0 + 2, ry), (gx0 + ft_w - 2, ry), col_grid, 1, cv2.LINE_AA)
                self._draw_text(
                    overlay,
                    label,
                    (gx0 + ft_w + int(round(8 * scale)), ry + int(round(4 * scale))),
                    font_scale=0.42 * scale,
                    color=col_white,
                    thickness=max(1, int(round(1.1 * scale))),
                )

        # Plot step-graph of frametimes
        ft_list = list(self._ft_history)
        if len(ft_list) > 1:
            step_dx = ft_w / float(max(1, self.frametime_history_len))
            for i in range(1, len(ft_list)):
                prev_val = min(max_ft_ms, max(0.0, ft_list[i - 1]))
                curr_val = min(max_ft_ms, max(0.0, ft_list[i]))
                x_prev = int(round(gx0 + (i - 1) * step_dx))
                x_curr = int(round(gx0 + i * step_dx))
                y_prev = int(round(ft_y1 - (prev_val / max_ft_ms) * (ft_h - 6) - 3))
                y_curr = int(round(ft_y1 - (curr_val / max_ft_ms) * (ft_h - 6) - 3))

                seg_color = col_amber if curr_val > (1000.0 / target_fps) * 1.4 else col_emerald
                cv2.line(overlay, (x_prev, y_prev), (x_curr, y_prev), seg_color, max(1, int(round(2 * scale))), cv2.LINE_AA)
                cv2.line(overlay, (x_curr, y_prev), (x_curr, y_curr), seg_color, max(1, int(round(2 * scale))), cv2.LINE_AA)

        # ------------------------------------------------------------------
        # 3. Rolling Framerate Graph (Bottom-Left)
        # ------------------------------------------------------------------
        fps_x1 = min(width - int(round(60 * scale)), gx0 + fps_w)
        actual_fps_w = max(50, fps_x1 - gx0)
        self._draw_panel(overlay, gx0, fps_y0, fps_x1, fps_y1, col_panel_bg, col_panel_border, scale)
        self._draw_text(
            overlay,
            "FRAME-RATE (FPS)",
            (fps_x1 - int(round(155 * scale)), fps_y0 - int(round(8 * scale))),
            font_scale=0.48 * scale,
            color=col_white,
            thickness=max(1, int(round(1.3 * scale))),
        )

        # Midline and axis labels (e.g., 60, 40, 20 or 120, 60, 0)
        top_fps = max(60.0, target_fps)
        mid_fps = top_fps * (2.0 / 3.0)
        low_fps = top_fps * (1.0 / 3.0)
        for ref_val, ratio in [(top_fps, 0.08), (mid_fps, 0.50), (low_fps, 0.92)]:
            ry = int(round(fps_y0 + ratio * fps_h))
            if abs(ratio - 0.50) < 0.05:
                cv2.line(overlay, (gx0 + 2, ry), (fps_x1 - 2, ry), col_grid, 1, cv2.LINE_AA)
            self._draw_text(
                overlay,
                f"{int(round(ref_val))}",
                (fps_x1 + int(round(8 * scale)), ry + int(round(4 * scale))),
                font_scale=0.42 * scale,
                color=col_white,
                thickness=max(1, int(round(1.1 * scale))),
            )

        fps_list = list(self._fps_history)
        tear_list = list(self._tear_history)
        if len(fps_list) > 1:
            dx_fps = actual_fps_w / float(max(1, self.fps_history_len - 1))
            pts: list[tuple[int, int]] = []
            for i, val in enumerate(fps_list):
                clamped = min(top_fps, max(0.0, val))
                norm_y = 1.0 - (clamped / top_fps)
                px = int(round(gx0 + i * dx_fps))
                py = int(round(fps_y0 + 6 + norm_y * (fps_h - 12)))
                pts.append((px, py))

                if i < len(tear_list) and tear_list[i]:
                    cv2.line(overlay, (px, fps_y0 + 2), (px, fps_y1 - 2), col_red, max(1, int(round(1.5 * scale))), cv2.LINE_AA)

            for i in range(1, len(pts)):
                cv2.line(overlay, pts[i - 1], pts[i], col_emerald, max(1, int(round(2.2 * scale))), cv2.LINE_AA)

        # ------------------------------------------------------------------
        # 4. Screen Tear Scanline Indicator Ticks (if frame is torn)
        # ------------------------------------------------------------------
        if self.show_tear_lines and metrics.is_torn:
            tick_w = int(round(28 * scale))
            for ty in metrics.tear_line_y:
                if 0 <= ty < height:
                    cv2.line(overlay, (0, ty), (tick_w, ty), col_red, max(2, int(round(2.5 * scale))), cv2.LINE_AA)
                    cv2.line(overlay, (width - tick_w, ty), (width - 1, ty), col_red, max(2, int(round(2.5 * scale))), cv2.LINE_AA)

        return overlay

    def composite_on_bgr(
        self,
        bgr_frame: np.ndarray,
        metrics: FrameMetrics,
        target_fps: float = 60.0,
        update: bool = True,
    ) -> np.ndarray:
        """Render HUD overlay and alpha-blend it onto a copy of bgr_frame."""
        h, w = bgr_frame.shape[:2]
        overlay = self.render_rgba_overlay(w, h, metrics, target_fps=target_fps, update=update)
        out = bgr_frame.copy()

        alpha = overlay[:, :, 3:4].astype(np.float32) / 255.0
        active_rows = np.any(overlay[:, :, 3] > 0, axis=1)
        if not np.any(active_rows):
            return out

        out_f = out[active_rows].astype(np.float32)
        ov_f = overlay[active_rows, :, :3].astype(np.float32)
        al_f = alpha[active_rows]
        out[active_rows] = np.clip(ov_f * al_f + out_f * (1.0 - al_f), 0, 255).astype(np.uint8)
        return out

    @staticmethod
    def _draw_panel(
        canvas: np.ndarray,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        bg_color: tuple[int, int, int, int],
        border_color: tuple[int, int, int, int],
        scale: float,
    ) -> None:
        canvas[y0:y1, x0:x1] = bg_color
        cv2.rectangle(
            canvas,
            (x0, y0),
            (x1, y1),
            border_color,
            max(1, int(round(1.6 * scale))),
            cv2.LINE_AA,
        )

    @staticmethod
    def _draw_text(
        canvas: np.ndarray,
        text: str,
        org: tuple[int, int],
        font_scale: float,
        color: tuple[int, int, int, int],
        thickness: int,
    ) -> None:
        shadow_offset = max(1, int(round(font_scale * 2.0)))
        cv2.putText(
            canvas,
            text,
            (org[0] + shadow_offset, org[1] + shadow_offset),
            cv2.FONT_HERSHEY_DUPLEX,
            font_scale,
            (0, 0, 0, 230),
            thickness + 1,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            text,
            org,
            cv2.FONT_HERSHEY_DUPLEX,
            font_scale,
            color,
            thickness,
            cv2.LINE_AA,
        )
