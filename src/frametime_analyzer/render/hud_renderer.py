"""Studio-grade Digital Foundry / TrDrop style RGBA HUD renderer."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional
import cv2
import numpy as np

from frametime_analyzer.models import FrameMetrics
from frametime_analyzer.render.hud_layout import HUDLayout
from frametime_analyzer.render.platform_logos import (
    draw_platform_badge,
    measure_platform_badge,
    read_image_unchanged,
)

_PlaceFn = Callable[[str, int, int], Optional[tuple[int, int]]]


@dataclass(frozen=True)
class _Palette:
    """HUD colors in BGRA format."""

    panel_bg: tuple[int, int, int, int] = (18, 22, 28, 185)
    panel_border: tuple[int, int, int, int] = (220, 225, 230, 210)
    emerald: tuple[int, int, int, int] = (130, 232, 93, 255)  # #5DE882 DF Green
    cyan: tuple[int, int, int, int] = (240, 210, 80, 255)  # Cyan accent for DRS scale
    amber: tuple[int, int, int, int] = (60, 185, 255, 255)  # Warning amber
    red: tuple[int, int, int, int] = (80, 75, 255, 255)  # Drop / tear red
    white: tuple[int, int, int, int] = (250, 250, 250, 255)
    muted: tuple[int, int, int, int] = (185, 190, 198, 230)
    grid: tuple[int, int, int, int] = (110, 120, 130, 140)



_TEXT_REPLACEMENTS = {"\u2022": "-", "\u2013": "-", "\u2014": "-", "\u00d7": "x", "\u00b0": " deg"}


def _ascii_text(text: str) -> str:
    """OpenCV Hershey fonts only cover ASCII: map common symbols and replace the rest with '?'."""
    for src, dst in _TEXT_REPLACEMENTS.items():
        text = text.replace(src, dst)
    return text.encode("ascii", "replace").decode("ascii")


class HUDRenderer:
    """Renders anti-aliased RGBA performance and resolution overlays at any resolution.

    Appearance (labels, logos, extra info text and element placement) is driven by a
    :class:`~frametime_analyzer.render.hud_layout.HUDLayout`. The legacy keyword arguments
    (``show_tear_lines``, ``show_resolution_badge``, ``platform_name``, ``custom_logo_path``)
    override the corresponding layout fields when given.
    """

    def __init__(
        self,
        fps_history_len: int = 240,
        frametime_history_len: int = 80,
        show_tear_lines: Optional[bool] = None,
        show_resolution_badge: Optional[bool] = None,
        platform_name: Optional[str] = None,
        custom_logo_path: Optional[str] = None,
        layout: Optional[HUDLayout] = None,
    ) -> None:
        self.fps_history_len = fps_history_len
        self.frametime_history_len = frametime_history_len
        self.layout = layout.copy() if layout is not None else HUDLayout()
        if show_tear_lines is not None:
            self.layout.show_tear_lines = show_tear_lines
        if show_resolution_badge is not None:
            self.layout.show_resolution = show_resolution_badge
        if platform_name is not None:
            self.layout.platform_name = platform_name
        if custom_logo_path is not None:
            self.layout.custom_logo_path = custom_logo_path

        # Pixel rectangles (x0, y0, x1, y1) of each element drawn in the last render, used by the GUI for hit-testing.
        self.last_element_rects: dict[str, tuple[int, int, int, int]] = {}
        self._brand_logo_cache: tuple[Optional[str], Optional[np.ndarray]] = (None, None)

        self._fps_history: deque[float] = deque(maxlen=fps_history_len)
        self._tear_history: deque[bool] = deque(maxlen=fps_history_len)
        self._ft_history: deque[float] = deque(maxlen=frametime_history_len)
        self._res_scale_history: deque[float] = deque(maxlen=fps_history_len)

    # Backwards-compatible attribute access to the most common layout fields
    @property
    def platform_name(self) -> str:
        return self.layout.platform_name

    @platform_name.setter
    def platform_name(self, value: str) -> None:
        self.layout.platform_name = value

    @property
    def custom_logo_path(self) -> Optional[str]:
        return self.layout.custom_logo_path

    @custom_logo_path.setter
    def custom_logo_path(self, value: Optional[str]) -> None:
        self.layout.custom_logo_path = value

    @property
    def show_tear_lines(self) -> bool:
        return self.layout.show_tear_lines

    @show_tear_lines.setter
    def show_tear_lines(self, value: bool) -> None:
        self.layout.show_tear_lines = value

    @property
    def show_resolution_badge(self) -> bool:
        return self.layout.show_resolution

    @show_resolution_badge.setter
    def show_resolution_badge(self, value: bool) -> None:
        self.layout.show_resolution = value

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

    def scale_for_height(self, height: int) -> float:
        """Pixel scale of 1080p reference units for a canvas of the given height (includes ``layout.hud_scale``)."""
        return max(0.65, min(2.5, height / 1080.0)) * max(0.25, self.layout.hud_scale)

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

        layout = self.layout
        overlay = np.zeros((height, width, 4), dtype=np.uint8)
        scale = self.scale_for_height(height)
        self.last_element_rects = {}

        panel_alpha = int(round(255 * min(1.0, max(0.0, layout.panel_opacity))))
        pal = _Palette(panel_bg=(18, 22, 28, panel_alpha))

        def place(name: str, elem_w: int, elem_h: int) -> Optional[tuple[int, int]]:
            placement = layout.element(name)
            if not placement.visible or elem_w <= 0 or elem_h <= 0:
                return None
            x, y = placement.resolve(width, height, elem_w, elem_h, scale)
            x = max(0, min(x, width - elem_w))
            y = max(0, min(y, height - elem_h))
            self.last_element_rects[name] = (x, y, min(width, x + elem_w), min(height, y + elem_h))
            return x, y

        # 1. Console / platform logo badge
        if layout.platform_name or layout.custom_logo_path or layout.platform_label:
            badge_w, badge_h = measure_platform_badge(scale, layout.platform_name, layout.platform_label or None)
            pos = place("platform_badge", badge_w + 1, badge_h + 1)
            if pos is not None:
                draw_platform_badge(
                    overlay,
                    pos[0],
                    pos[1],
                    scale,
                    platform_name=layout.platform_name,
                    custom_logo_path=layout.custom_logo_path,
                    label=layout.platform_label or None,
                )

        # 2. FPS & resolution card
        card_w = int(round(410 * scale))
        card_h = int(round((175 if layout.show_resolution else 115) * scale))
        pos = place("stats_card", min(card_w, width), min(card_h, height))
        if pos is not None:
            self._draw_stats_card(overlay, pos[0], pos[1], card_w, card_h, metrics, target_fps, scale, pal)

        # 3. Frametime step-graph & 4. rolling frame-rate graph (titles above, axis labels to the right)
        title_h = int(round(26 * scale))
        axis_w = int(round(55 * scale))
        ft_w, ft_h = int(round(360 * scale)), int(round(105 * scale))
        pos = place("frametime_graph", min(ft_w + axis_w, width), min(ft_h + title_h, height))
        if pos is not None:
            panel_w = min(ft_w, width - axis_w)
            self._draw_frametime_graph(overlay, pos[0], pos[1] + title_h, panel_w, ft_h, target_fps, scale, pal)

        fps_w, fps_h = int(round(620 * scale)), int(round(145 * scale))
        pos = place("fps_graph", min(fps_w + axis_w, width), min(fps_h + title_h, height))
        if pos is not None:
            panel_w = min(fps_w, width - axis_w)
            self._draw_fps_graph(overlay, pos[0], pos[1] + title_h, panel_w, fps_h, target_fps, scale, pal)

        # 5. Free-form extra info panel (game title, settings, capture notes...)
        self._draw_extra_info(overlay, scale, pal, place)

        # 6. Brand / channel logo image
        self._draw_brand_logo(overlay, scale, place)

        # 7. Screen tear scanline indicator ticks (full-height edges, not part of the anchored layout)
        if layout.show_tear_lines and metrics.is_torn:
            tick_w = int(round(28 * scale))
            for ty in metrics.tear_line_y:
                if 0 <= ty < height:
                    cv2.line(overlay, (0, ty), (tick_w, ty), pal.red, max(2, int(round(2.5 * scale))), cv2.LINE_AA)
                    cv2.line(overlay, (width - tick_w, ty), (width - 1, ty), pal.red, max(2, int(round(2.5 * scale))), cv2.LINE_AA)

        return overlay

    # ------------------------------------------------------------------
    # Element drawing
    # ------------------------------------------------------------------
    def _draw_stats_card(
        self,
        overlay: np.ndarray,
        cx0: int,
        cy0: int,
        card_w: int,
        card_h: int,
        metrics: FrameMetrics,
        target_fps: float,
        scale: float,
        pal: _Palette,
    ) -> None:
        labels = self.layout.labels
        height, width = overlay.shape[:2]
        cx1 = min(width - 1, cx0 + card_w)
        cy1 = min(height - 1, cy0 + card_h)

        fps_ratio = metrics.rolling_fps / max(1.0, target_fps)
        if fps_ratio >= 0.92:
            fps_color = pal.emerald
        elif fps_ratio >= 0.75:
            fps_color = pal.amber
        else:
            fps_color = pal.red

        self._draw_panel(overlay, cx0, cy0, cx1, cy1, pal.panel_bg, pal.panel_border, scale)

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
            labels.fps_unit,
            (cx0 + int(round(165 * scale)), cy0 + int(round(62 * scale))),
            font_scale=0.65 * scale,
            color=pal.muted,
            thickness=max(1, int(round(1.5 * scale))),
        )

        # 1% Low & Frametime readout on right side of top card
        self._draw_text(
            overlay,
            f"{labels.one_percent_low}: {metrics.fps_1_percent_low:04.1f}",
            (cx0 + int(round(235 * scale)), cy0 + int(round(36 * scale))),
            font_scale=0.50 * scale,
            color=pal.white,
            thickness=max(1, int(round(1.3 * scale))),
        )
        self._draw_text(
            overlay,
            f"{labels.frametime_short}: {metrics.frametime_ms:04.1f} ms",
            (cx0 + int(round(235 * scale)), cy0 + int(round(64 * scale))),
            font_scale=0.50 * scale,
            color=pal.white,
            thickness=max(1, int(round(1.3 * scale))),
        )

        # Status badge (Duplicate / Tearing / V-Sync status)
        status_y = cy0 + int(round(95 * scale))
        if metrics.is_torn:
            status_text = (
                f"{labels.status_tearing} (Y={metrics.tear_line_y[0]}px)" if metrics.tear_line_y else labels.status_tearing
            )
            status_col = pal.red
        elif metrics.is_duplicate:
            status_text = labels.status_duplicate
            status_col = pal.amber
        else:
            status_text = labels.status_clean
            status_col = pal.emerald

        self._draw_text(
            overlay,
            status_text,
            (cx0 + int(round(20 * scale)), status_y),
            font_scale=0.45 * scale,
            color=status_col,
            thickness=max(1, int(round(1.2 * scale))),
        )

        # Resolution & DRS section
        if self.layout.show_resolution:
            sep_y = cy0 + int(round(110 * scale))
            cv2.line(
                overlay,
                (cx0 + int(round(16 * scale)), sep_y),
                (cx1 - int(round(16 * scale)), sep_y),
                pal.grid,
                max(1, int(round(1 * scale))),
                cv2.LINE_AA,
            )
            tw, th = metrics.target_resolution
            rw, rh = metrics.estimated_render_resolution
            self._draw_text(
                overlay,
                f"{labels.target_output}: {tw}x{th} ({th}p)",
                (cx0 + int(round(20 * scale)), cy0 + int(round(134 * scale))),
                font_scale=0.46 * scale,
                color=pal.muted,
                thickness=max(1, int(round(1.2 * scale))),
            )
            self._draw_text(
                overlay,
                f"{labels.est_render}:   {rw}x{rh} ({metrics.resolution_tier_label} - {metrics.render_scale_percent:.0f}%)",
                (cx0 + int(round(20 * scale)), cy0 + int(round(158 * scale))),
                font_scale=0.48 * scale,
                color=pal.cyan,
                thickness=max(1, int(round(1.4 * scale))),
            )

    def _draw_frametime_graph(
        self,
        overlay: np.ndarray,
        gx0: int,
        ft_y0: int,
        ft_w: int,
        ft_h: int,
        target_fps: float,
        scale: float,
        pal: _Palette,
    ) -> None:
        ft_y1 = ft_y0 + ft_h
        self._draw_panel(overlay, gx0, ft_y0, gx0 + ft_w, ft_y1, pal.panel_bg, pal.panel_border, scale)
        self._draw_text(
            overlay,
            self.layout.labels.frametime_graph_title,
            (gx0 + int(round(8 * scale)), ft_y0 - int(round(8 * scale))),
            font_scale=0.48 * scale,
            color=pal.white,
            thickness=max(1, int(round(1.3 * scale))),
        )

        # Reference lines at 16.7ms and 33.3ms (mapped into [0..50ms] range)
        max_ft_ms = 50.0
        for ref_ms, label in [(16.67, "16.7"), (33.33, "33.3")]:
            ry = int(round(ft_y1 - (ref_ms / max_ft_ms) * ft_h))
            if ft_y0 < ry < ft_y1:
                cv2.line(overlay, (gx0 + 2, ry), (gx0 + ft_w - 2, ry), pal.grid, 1, cv2.LINE_AA)
                self._draw_text(
                    overlay,
                    label,
                    (gx0 + ft_w + int(round(8 * scale)), ry + int(round(4 * scale))),
                    font_scale=0.42 * scale,
                    color=pal.white,
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

                seg_color = pal.amber if curr_val > (1000.0 / target_fps) * 1.4 else pal.emerald
                cv2.line(overlay, (x_prev, y_prev), (x_curr, y_prev), seg_color, max(1, int(round(2 * scale))), cv2.LINE_AA)
                cv2.line(overlay, (x_curr, y_prev), (x_curr, y_curr), seg_color, max(1, int(round(2 * scale))), cv2.LINE_AA)

    def _draw_fps_graph(
        self,
        overlay: np.ndarray,
        gx0: int,
        fps_y0: int,
        fps_w: int,
        fps_h: int,
        target_fps: float,
        scale: float,
        pal: _Palette,
    ) -> None:
        fps_x1 = gx0 + fps_w
        fps_y1 = fps_y0 + fps_h
        self._draw_panel(overlay, gx0, fps_y0, fps_x1, fps_y1, pal.panel_bg, pal.panel_border, scale)
        title = self.layout.labels.fps_graph_title
        (title_w, _), _ = cv2.getTextSize(
            _ascii_text(title), cv2.FONT_HERSHEY_DUPLEX, 0.48 * scale, max(1, int(round(1.3 * scale)))
        )
        self._draw_text(
            overlay,
            title,
            (max(gx0, fps_x1 - title_w - int(round(20 * scale))), fps_y0 - int(round(8 * scale))),
            font_scale=0.48 * scale,
            color=pal.white,
            thickness=max(1, int(round(1.3 * scale))),
        )

        # Midline and axis labels (e.g., 60, 40, 20 or 120, 80, 40)
        top_fps = max(60.0, target_fps)
        mid_fps = top_fps * (2.0 / 3.0)
        low_fps = top_fps * (1.0 / 3.0)
        for ref_val, ratio in [(top_fps, 0.08), (mid_fps, 0.50), (low_fps, 0.92)]:
            ry = int(round(fps_y0 + ratio * fps_h))
            if abs(ratio - 0.50) < 0.05:
                cv2.line(overlay, (gx0 + 2, ry), (fps_x1 - 2, ry), pal.grid, 1, cv2.LINE_AA)
            self._draw_text(
                overlay,
                f"{int(round(ref_val))}",
                (fps_x1 + int(round(8 * scale)), ry + int(round(4 * scale))),
                font_scale=0.42 * scale,
                color=pal.white,
                thickness=max(1, int(round(1.1 * scale))),
            )

        fps_list = list(self._fps_history)
        tear_list = list(self._tear_history)
        if len(fps_list) > 1:
            dx_fps = fps_w / float(max(1, self.fps_history_len - 1))
            pts: list[tuple[int, int]] = []
            for i, val in enumerate(fps_list):
                clamped = min(top_fps, max(0.0, val))
                norm_y = 1.0 - (clamped / top_fps)
                px = int(round(gx0 + i * dx_fps))
                py = int(round(fps_y0 + 6 + norm_y * (fps_h - 12)))
                pts.append((px, py))

                if i < len(tear_list) and tear_list[i]:
                    cv2.line(overlay, (px, fps_y0 + 2), (px, fps_y1 - 2), pal.red, max(1, int(round(1.5 * scale))), cv2.LINE_AA)

            for i in range(1, len(pts)):
                cv2.line(overlay, pts[i - 1], pts[i], pal.emerald, max(1, int(round(2.2 * scale))), cv2.LINE_AA)

    def _draw_extra_info(self, overlay: np.ndarray, scale: float, pal: _Palette, place: _PlaceFn) -> None:
        title = self.layout.extra_info_title.strip()
        lines = [line for line in self.layout.extra_info_lines if line.strip()]
        if not title and not lines:
            return

        pad = int(round(16 * scale))
        title_fs, line_fs = 0.62 * scale, 0.48 * scale
        title_th, line_th = max(1, int(round(1.6 * scale))), max(1, int(round(1.2 * scale)))
        title_lh, line_lh = int(round(34 * scale)), int(round(26 * scale))

        text_w = 0
        if title:
            text_w = cv2.getTextSize(_ascii_text(title), cv2.FONT_HERSHEY_DUPLEX, title_fs, title_th)[0][0]
        for line in lines:
            text_w = max(text_w, cv2.getTextSize(_ascii_text(line), cv2.FONT_HERSHEY_DUPLEX, line_fs, line_th)[0][0])
        box_w = text_w + pad * 2
        box_h = pad * 2 + (title_lh if title else 0) + line_lh * len(lines) - int(round(8 * scale))

        pos = place("extra_info", box_w, box_h)
        if pos is None:
            return
        x0, y0 = pos
        self._draw_panel(overlay, x0, y0, x0 + box_w - 1, y0 + box_h - 1, pal.panel_bg, pal.panel_border, scale)
        y = y0 + pad
        if title:
            y += int(round(22 * scale))
            self._draw_text(overlay, title, (x0 + pad, y), font_scale=title_fs, color=pal.emerald, thickness=title_th)
            y += title_lh - int(round(22 * scale))
        for line in lines:
            y += int(round(18 * scale))
            self._draw_text(overlay, line, (x0 + pad, y), font_scale=line_fs, color=pal.white, thickness=line_th)
            y += line_lh - int(round(18 * scale))

    def _load_brand_logo(self) -> Optional[np.ndarray]:
        path = self.layout.brand_logo_path
        cached_path, cached_img = self._brand_logo_cache
        if path != cached_path:
            img = read_image_unchanged(path)
            if img is not None:
                if img.ndim == 2:
                    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
                elif img.shape[2] == 3:
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
            self._brand_logo_cache = (path, img)
            cached_img = img
        return cached_img

    def _draw_brand_logo(self, overlay: np.ndarray, scale: float, place: _PlaceFn) -> None:
        logo = self._load_brand_logo()
        if logo is None:
            return
        height, width = overlay.shape[:2]
        target_h = max(4, min(height, int(round(self.layout.brand_logo_height * scale))))
        target_w = max(4, min(width, int(round(logo.shape[1] * target_h / max(1, logo.shape[0])))))
        pos = place("brand_logo", target_w, target_h)
        if pos is None:
            return
        x0, y0 = pos
        interp = cv2.INTER_AREA if target_h < logo.shape[0] else cv2.INTER_CUBIC
        resized = cv2.resize(logo, (target_w, target_h), interpolation=interp).astype(np.float32)
        src_a = resized[:, :, 3:4] / 255.0 * min(1.0, max(0.0, self.layout.brand_logo_opacity))
        dst = overlay[y0 : y0 + target_h, x0 : x0 + target_w].astype(np.float32)
        dst_a = dst[:, :, 3:4] / 255.0
        out_a = src_a + dst_a * (1.0 - src_a)
        out_rgb = (resized[:, :, :3] * src_a + dst[:, :, :3] * dst_a * (1.0 - src_a)) / np.maximum(out_a, 1e-6)
        overlay[y0 : y0 + target_h, x0 : x0 + target_w, :3] = np.clip(out_rgb, 0, 255).astype(np.uint8)
        overlay[y0 : y0 + target_h, x0 : x0 + target_w, 3] = np.clip(out_a[:, :, 0] * 255.0, 0, 255).astype(np.uint8)

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
        text = _ascii_text(text)
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
