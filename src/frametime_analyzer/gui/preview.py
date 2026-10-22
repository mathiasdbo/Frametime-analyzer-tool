"""Live HUD preview: frame source, synthetic preview metrics and the interactive (drag-to-place) canvas."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional
import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from frametime_analyzer.models import FrameMetrics
from frametime_analyzer.render.hud_layout import ELEMENT_TITLES
from frametime_analyzer.render.hud_renderer import HUDRenderer

PREVIEW_STATES = ("Clean frame", "Frame repeat", "Screen tearing")
MAX_PREVIEW_HEIGHT = 1080


class PreviewFrameSource:
    """Provides preview frames from a video file (random access) or a synthetic placeholder."""

    def __init__(self) -> None:
        self.path: Optional[str] = None
        self.total_frames = 0
        self.fps = 60.0
        self.width = 0
        self.height = 0
        self._cap: Optional[cv2.VideoCapture] = None

    def open(self, path: str) -> None:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise FileNotFoundError(f"Could not open video file: {path}")
        self.close()
        self._cap = cap
        self.path = path
        self.total_frames = max(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        self.fps = float(cap.get(cv2.CAP_PROP_FPS)) or 60.0
        self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
        self._cap = None
        self.path = None
        self.total_frames = 0

    def frame(self, index: int) -> np.ndarray:
        """Return a BGR frame (downscaled to at most 1080p, which keeps HUD proportions identical)."""
        bgr: Optional[np.ndarray] = None
        if self._cap is not None:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, min(index, self.total_frames - 1)))
            grabbed, bgr = self._cap.read()
            if not grabbed:
                bgr = None
        if bgr is None:
            bgr = placeholder_frame()
        h, w = bgr.shape[:2]
        if h > MAX_PREVIEW_HEIGHT:
            new_w = int(round(w * MAX_PREVIEW_HEIGHT / h))
            bgr = cv2.resize(bgr, (new_w, MAX_PREVIEW_HEIGHT), interpolation=cv2.INTER_AREA)
        return bgr


def placeholder_frame(width: int = 1920, height: int = 1080) -> np.ndarray:
    """A neutral 'game scene' gradient used before a video is opened."""
    ys = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    xs = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    b = 70 + 90 * ys + 20 * xs
    g = 55 + 60 * ys + 30 * (1 - xs)
    r = 40 + 40 * ys + 25 * xs
    frame = np.stack([np.broadcast_to(c, (height, width)) for c in (b, g, r)], axis=-1).astype(np.uint8)
    # Simple horizon + hills silhouette so the HUD can be judged against "content"
    hills = (height * (0.68 + 0.05 * np.sin(np.linspace(0, 7, width)) + 0.03 * np.sin(np.linspace(0, 23, width)))).astype(int)
    for x in range(0, width, 2):
        frame[hills[x] :, x : x + 2] = (38, 62, 44)
    cv2.putText(frame, "Open a video to preview it here", (width // 2 - 430, height // 2), cv2.FONT_HERSHEY_DUPLEX, 1.6, (235, 235, 235), 2, cv2.LINE_AA)
    return frame


def prime_preview_history(hud: HUDRenderer, target_fps: float = 60.0) -> None:
    """Fill the HUD graphs with plausible synthetic data so their look can be judged in the preview."""
    hud.reset()
    for i in range(hud.fps_history_len):
        dip = 0.35 * max(0.0, math.sin(i / 23.0)) ** 6
        fps = target_fps * (1.0 - dip) - 1.5 * abs(math.sin(i / 3.7))
        ft = 1000.0 / target_fps * (2.0 if i % 37 == 0 else 1.0)
        hud.update_history(
            FrameMetrics(
                frame_index=i,
                timestamp_ms=i * 1000.0 / target_fps,
                frame_duration_ms=1000.0 / target_fps,
                is_duplicate=False,
                is_torn=i % 97 == 50,
                rolling_fps=fps,
                frametime_ms=ft,
            )
        )


def preview_metrics(width: int, height: int, state: str, frame_index: int = 0, target_fps: float = 60.0) -> FrameMetrics:
    """Representative metrics for the current preview frame."""
    torn = state == PREVIEW_STATES[2]
    duplicate = state == PREVIEW_STATES[1]
    render_h = int(round(height * 0.75))
    render_w = int(round(width * 0.75))
    return FrameMetrics(
        frame_index=frame_index,
        timestamp_ms=frame_index * 1000.0 / target_fps,
        frame_duration_ms=1000.0 / target_fps,
        is_duplicate=duplicate,
        is_torn=torn,
        tear_line_y=[int(height * 0.42)] if torn else [],
        frametime_ms=1000.0 / target_fps * (2.0 if duplicate else 1.0),
        rolling_fps=target_fps * (0.9 if duplicate else 0.98),
        fps_1_percent_low=target_fps * 0.72,
        container_resolution=(width, height),
        target_resolution=(width, height),
        estimated_render_resolution=(render_w, render_h),
        render_scale_percent=75.0,
        resolution_tier_label=f"{render_h}p",
    )


class PreviewCanvas(QWidget):
    """Displays the composited preview and lets the user drag HUD elements into place.

    Signals:
        element_selected(name): the user pressed on an element (a drag may follow).
        element_dragged(name, dx, dy): total drag distance since the press, in *preview image* pixels.
    """

    element_dragged = Signal(str, float, float)
    element_selected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(480, 270)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self._image: Optional[QImage] = None
        self._rects: dict[str, tuple[int, int, int, int]] = {}
        self._hover: Optional[str] = None
        self._selected: Optional[str] = None
        self._drag_name: Optional[str] = None
        self._drag_origin: Optional[QPointF] = None
        self.show_guides = True

    def set_frame(self, bgr: np.ndarray, element_rects: dict[str, tuple[int, int, int, int]]) -> None:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        self._image = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
        self._rects = dict(element_rects)
        self.update()

    def image_size(self) -> Optional[tuple[int, int]]:
        """(width, height) of the displayed preview image, in image pixels."""
        return (self._image.width(), self._image.height()) if self._image is not None else None

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------
    def _target_rect(self) -> QRectF:
        if self._image is None:
            return QRectF()
        iw, ih = self._image.width(), self._image.height()
        s = min(self.width() / iw, self.height() / ih)
        return QRectF((self.width() - iw * s) / 2, (self.height() - ih * s) / 2, iw * s, ih * s)

    def _view_scale(self) -> float:
        if self._image is None:
            return 1.0
        return self._target_rect().width() / self._image.width()

    def _to_image(self, pos: QPointF) -> QPointF:
        tr = self._target_rect()
        s = self._view_scale()
        return QPointF((pos.x() - tr.x()) / s, (pos.y() - tr.y()) / s)

    def _element_at(self, pos: QPointF) -> Optional[str]:
        p = self._to_image(pos)
        for name in reversed(list(self._rects)):
            x0, y0, x1, y1 = self._rects[name]
            if x0 <= p.x() <= x1 and y0 <= p.y() <= y1:
                return name
        return None

    # ------------------------------------------------------------------
    # Qt events
    # ------------------------------------------------------------------
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt API)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(14, 16, 20))
        if self._image is None:
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        tr = self._target_rect()
        painter.drawImage(tr, self._image)

        if not self.show_guides:
            return
        s = self._view_scale()
        font = QFont(self.font())
        font.setPointSize(9)
        painter.setFont(font)
        for name, (x0, y0, x1, y1) in self._rects.items():
            if name not in (self._hover, self._selected, self._drag_name):
                continue
            rect = QRectF(tr.x() + x0 * s, tr.y() + y0 * s, (x1 - x0) * s, (y1 - y0) * s)
            active = name in (self._selected, self._drag_name)
            pen = QPen(QColor(93, 232, 130) if active else QColor(255, 255, 255, 170), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(rect)
            label = ELEMENT_TITLES.get(name, name)
            label_rect = QRectF(rect.x(), max(tr.y(), rect.y() - 18), max(rect.width(), 150), 16)
            painter.fillRect(QRectF(label_rect.x(), label_rect.y(), painter.fontMetrics().horizontalAdvance(label) + 10, 16), QColor(0, 0, 0, 170))
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(label_rect.adjusted(5, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        name = self._element_at(event.position())
        self._selected = name
        if name is not None:
            self._drag_name = name
            self._drag_origin = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.element_selected.emit(name)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_name is not None and self._drag_origin is not None:
            s = self._view_scale()
            delta = event.position() - self._drag_origin
            if s > 0:
                self.element_dragged.emit(self._drag_name, delta.x() / s, delta.y() / s)
            return
        hover = self._element_at(event.position())
        if hover != self._hover:
            self._hover = hover
            self.setCursor(Qt.CursorShape.OpenHandCursor if hover else Qt.CursorShape.ArrowCursor)
            self.setToolTip(f"Drag to move: {ELEMENT_TITLES.get(hover, hover)}" if hover else "")
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_name is not None:
            self._drag_name = None
            self._drag_origin = None
            self.setCursor(Qt.CursorShape.OpenHandCursor if self._hover else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, event: object) -> None:  # noqa: N802
        self._hover = None
        self.update()


def is_video_file(path: str) -> bool:
    return Path(path).suffix.lower() in {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".ts", ".flv"}
