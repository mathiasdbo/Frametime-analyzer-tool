"""Cross-platform desktop GUI (PySide6 / Qt) for customizing the HUD and processing capture videos.

Launch with ``fta gui`` or ``fta-gui``.
"""
from __future__ import annotations

from dataclasses import fields
import json
from pathlib import Path
import sys
from threading import Event
from typing import Callable, Optional

from PySide6.QtCore import QSettings, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QCloseEvent, QColor, QDesktopServices, QDragEnterEvent, QDropEvent, QKeySequence, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from frametime_analyzer.gui.preview import (
    PREVIEW_STATES,
    PreviewCanvas,
    PreviewFrameSource,
    is_video_file,
    preview_metrics,
    prime_preview_history,
)
from frametime_analyzer.processing import ProcessingJob, ProcessingResult, process_video
from frametime_analyzer.render.hud_layout import (
    ANCHORS,
    ELEMENT_NAMES,
    ELEMENT_TITLES,
    LABEL_TITLES,
    HUDLabels,
    HUDLayout,
)
from frametime_analyzer.render.hud_renderer import HUDRenderer

APP_NAME = "Frametime Analyzer Studio"
PLATFORM_CHOICES = (
    "PS5", "PS5 Pro", "PS4", "PS3", "PS2", "PS1",
    "Xbox Series X", "Xbox Series S", "Xbox One", "Xbox 360", "Xbox",
    "Switch 2", "Switch", "Wii U", "Wii", "GameCube", "N64",
    "Steam Deck", "PC", "Elgato",
)
VIDEO_FILTER = "Videos (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.ts *.flv);;All files (*)"
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All files (*)"
LAYOUT_FILTER = "HUD layout (*.json)"


class ProcessingThread(QThread):
    """Runs :func:`process_video` off the UI thread."""

    progress = Signal(int, int)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, job: ProcessingJob) -> None:
        super().__init__()
        self.job = job
        self.cancel_event = Event()

    def run(self) -> None:
        try:
            result = process_video(self.job, progress=self.progress.emit, cancel_event=self.cancel_event)
        except Exception as exc:  # Surface any failure in the UI instead of killing the thread silently
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.succeeded.emit(result)


class PathPicker(QWidget):
    """Line edit + browse (+ optional clear) button for a file path."""

    changed = Signal()

    def __init__(
        self,
        dialog: Callable[[QWidget, str, str, str], tuple[str, str]],
        caption: str,
        file_filter: str,
        placeholder: str = "",
        clearable: bool = False,
    ) -> None:
        super().__init__()
        self._dialog = dialog
        self._caption = caption
        self._filter = file_filter
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.textChanged.connect(self.changed)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.edit, 1)
        row.addWidget(browse)
        if clearable:
            clear = QPushButton("Clear")
            clear.clicked.connect(lambda: self.edit.setText(""))
            row.addWidget(clear)

    def _browse(self) -> None:
        start = self.edit.text() or str(Path.home())
        path, _ = self._dialog(self, self._caption, start, self._filter)
        if path:
            self.edit.setText(path)

    def text(self) -> str:
        return self.edit.text().strip()

    def set_text(self, value: Optional[str]) -> None:
        self.edit.setText(value or "")


class OutputRow(QWidget):
    """Checkbox-enabled output path picker."""

    changed = Signal()

    def __init__(self, title: str, caption: str, file_filter: str, checked: bool = True) -> None:
        super().__init__()
        self.check = QCheckBox(title)
        self.check.setChecked(checked)
        self.check.setMinimumWidth(170)
        self.picker = PathPicker(QFileDialog.getSaveFileName, caption, file_filter)
        self.check.toggled.connect(self.picker.setEnabled)
        self.check.toggled.connect(self.changed)
        self.picker.changed.connect(self.changed)
        self.picker.setEnabled(checked)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.check)
        row.addWidget(self.picker, 1)

    def path(self) -> Optional[Path]:
        return Path(self.picker.text()).expanduser() if self.check.isChecked() and self.picker.text() else None


class ElementEditor(QWidget):
    """Visibility / anchor / offset controls for one HUD element."""

    changed = Signal()

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name
        self.visible = QCheckBox(ELEMENT_TITLES[name].replace("&", "&&"))
        self.visible.setMinimumWidth(190)
        self.anchor = QComboBox()
        for a in ANCHORS:
            self.anchor.addItem(a.replace("-", " ").title(), a)
        self.offset_x = QSpinBox()
        self.offset_y = QSpinBox()
        for spin, axis in ((self.offset_x, "X"), (self.offset_y, "Y")):
            spin.setRange(-4000, 4000)
            spin.setPrefix(f"{axis}: ")
            spin.setSuffix(" px")
            spin.setToolTip("Offset from the anchored edge, in 1080p reference pixels (scales with the video)")
            spin.valueChanged.connect(self.changed)
        self.visible.toggled.connect(self.changed)
        self.anchor.currentIndexChanged.connect(self.changed)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.visible)
        row.addWidget(self.anchor)
        row.addWidget(self.offset_x)
        row.addWidget(self.offset_y)


class MainWindow(QMainWindow):
    def __init__(self, video_path: Optional[Path] = None, layout_path: Optional[Path] = None) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1500, 900)
        self.setAcceptDrops(True)

        self.settings = QSettings("FrametimeAnalyzer", "Studio")
        self.layout_model = self._initial_layout(layout_path)
        self.frame_source = PreviewFrameSource()
        self.preview_hud = HUDRenderer(layout=self.layout_model)
        self._syncing = False
        self._worker: Optional[ProcessingThread] = None
        self._drag_start: Optional[tuple[str, int, int]] = None
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(25)
        self._preview_timer.timeout.connect(self._render_preview)

        self._build_menu()
        self._build_ui()
        self._sync_widgets_from_layout()
        prime_preview_history(self.preview_hud)

        if video_path is not None:
            self.open_video(str(video_path))
        else:
            self._schedule_preview()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _initial_layout(self, layout_path: Optional[Path]) -> HUDLayout:
        if layout_path is not None:
            return HUDLayout.load(layout_path)
        stored = self.settings.value("layout_json", "")
        if stored:
            try:
                return HUDLayout.from_dict(json.loads(str(stored)))
            except (ValueError, TypeError):
                pass
        return HUDLayout()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self._add_action(file_menu, "&Open Video…", self._browse_video, QKeySequence.StandardKey.Open)
        file_menu.addSeparator()
        self._add_action(file_menu, "&Load HUD Layout…", self._load_layout_dialog, "Ctrl+L")
        self._add_action(file_menu, "&Save HUD Layout…", self._save_layout_dialog, QKeySequence.StandardKey.Save)
        self._add_action(file_menu, "&Reset HUD Layout", self._reset_layout)
        file_menu.addSeparator()
        self._add_action(file_menu, "&Quit", self.close, QKeySequence.StandardKey.Quit)

        view_menu = self.menuBar().addMenu("&View")
        guides = self._add_action(view_menu, "Show Element &Guides", self._toggle_guides)
        guides.setCheckable(True)
        guides.setChecked(True)

        help_menu = self.menuBar().addMenu("&Help")
        self._add_action(help_menu, "&About", self._about)

    def _add_action(self, menu: object, text: str, slot: Callable[[], object], shortcut: object = None) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)  # type: ignore[arg-type]
        action.triggered.connect(slot)
        menu.addAction(action)  # type: ignore[attr-defined]
        return action

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_preview_panel())
        splitter.addWidget(self._build_settings_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([900, 600])

        central = QWidget()
        root = QVBoxLayout(central)
        root.addWidget(splitter, 1)
        root.addWidget(self._build_process_panel())
        self.setCentralWidget(central)
        self.statusBar().showMessage("Open a capture video (File ▸ Open, or drag & drop it onto the window).")

    def _build_preview_panel(self) -> QWidget:
        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(0, 0, 0, 0)

        self.canvas = PreviewCanvas()
        self.canvas.element_selected.connect(self._on_element_pressed)
        self.canvas.element_dragged.connect(self._on_element_dragged)
        col.addWidget(self.canvas, 1)

        controls = QHBoxLayout()
        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setRange(0, 0)
        self.frame_slider.valueChanged.connect(self._schedule_preview)
        self.frame_label = QLabel("No video")
        self.frame_label.setMinimumWidth(130)
        self.preview_state = QComboBox()
        self.preview_state.addItems(PREVIEW_STATES)
        self.preview_state.setToolTip("Preview how each frame status is labelled on the HUD")
        self.preview_state.currentIndexChanged.connect(self._schedule_preview)
        controls.addWidget(QLabel("Frame"))
        controls.addWidget(self.frame_slider, 1)
        controls.addWidget(self.frame_label)
        controls.addWidget(QLabel("Preview status"))
        controls.addWidget(self.preview_state)
        col.addLayout(controls)

        hint = QLabel("Tip: drag HUD elements directly in the preview to reposition them.")
        hint.setStyleSheet("color: #9aa3ad;")
        col.addWidget(hint)
        return panel

    def _build_settings_panel(self) -> QWidget:
        self.tabs = QTabWidget()
        self.tabs.addTab(self._scroll(self._build_files_tab()), "Input && Output")
        self.tabs.addTab(self._scroll(self._build_platform_tab()), "Platform && Logos")
        self.tabs.addTab(self._scroll(self._build_labels_tab()), "Labels")
        self.tabs.addTab(self._scroll(self._build_info_tab()), "Extra Info")
        self.tabs.addTab(self._scroll(self._build_layout_tab()), "Placement")
        return self.tabs

    @staticmethod
    def _scroll(widget: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(widget)
        return area

    def _build_files_tab(self) -> QWidget:
        tab = QWidget()
        col = QVBoxLayout(tab)

        src = QGroupBox("Source video")
        src_form = QFormLayout(src)
        self.input_picker = PathPicker(QFileDialog.getOpenFileName, "Open capture video", VIDEO_FILTER, "Capture video (MP4 / MOV / MKV)")
        self.input_picker.edit.editingFinished.connect(lambda: self.open_video(self.input_picker.text(), quiet=True))
        self.input_picker.changed.connect(self._on_input_text_changed)
        src_form.addRow("Video file", self.input_picker)
        self.video_info = QLabel("–")
        self.video_info.setStyleSheet("color: #9aa3ad;")
        src_form.addRow("", self.video_info)
        col.addWidget(src)

        out = QGroupBox("Outputs")
        out_col = QVBoxLayout(out)
        self.out_video = OutputRow("Burned-in video", "Save burned-in HUD video", "Video (*.mp4 *.mov)")
        self.out_alpha = OutputRow("Alpha overlay", "Save transparent overlay", "ProRes 4444 (*.mov);;VP9 alpha (*.webm)", checked=False)
        self.out_csv = OutputRow("CSV telemetry", "Save CSV telemetry", "CSV (*.csv)", checked=False)
        self.out_json = OutputRow("JSON summary", "Save JSON summary", "JSON (*.json)", checked=False)
        for row in (self.out_video, self.out_alpha, self.out_csv, self.out_json):
            out_col.addWidget(row)
        hint = QLabel("Output names are filled in automatically when you open a video.")
        hint.setStyleSheet("color: #9aa3ad;")
        out_col.addWidget(hint)
        col.addWidget(out)

        opts = QGroupBox("Analysis")
        form = QFormLayout(opts)
        self.detect_tearing = QCheckBox("Detect screen tearing")
        self.detect_tearing.setChecked(True)
        self.detect_resolution = QCheckBox("Estimate target && internal render resolution")
        self.detect_resolution.setChecked(True)
        self.max_frames = QSpinBox()
        self.max_frames.setRange(0, 10_000_000)
        self.max_frames.setSpecialValueText("All frames")
        form.addRow(self.detect_tearing)
        form.addRow(self.detect_resolution)
        form.addRow("Frame limit", self.max_frames)
        col.addWidget(opts)
        col.addStretch(1)
        return tab

    def _build_platform_tab(self) -> QWidget:
        tab = QWidget()
        col = QVBoxLayout(tab)

        badge = QGroupBox("Platform badge")
        form = QFormLayout(badge)
        self.platform_combo = QComboBox()
        self.platform_combo.setEditable(True)
        self.platform_combo.addItems(PLATFORM_CHOICES)
        self.platform_combo.setToolTip("Pick a console preset or type any name for a generic badge")
        self.platform_combo.currentTextChanged.connect(self._on_widget_changed)
        self.platform_label = QLineEdit()
        self.platform_label.setPlaceholderText("Optional – e.g. PS5 PRO • 120HZ MODE")
        self.platform_label.textChanged.connect(self._on_widget_changed)
        self.custom_icon = PathPicker(QFileDialog.getOpenFileName, "Choose badge icon", IMAGE_FILTER, "Built-in vector icon", clearable=True)
        self.custom_icon.changed.connect(self._on_widget_changed)
        form.addRow("Platform", self.platform_combo)
        form.addRow("Badge text", self.platform_label)
        form.addRow("Custom icon", self.custom_icon)
        col.addWidget(badge)

        brand = QGroupBox("Brand / channel logo")
        bform = QFormLayout(brand)
        self.brand_logo = PathPicker(QFileDialog.getOpenFileName, "Choose logo image", IMAGE_FILTER, "PNG with transparency recommended", clearable=True)
        self.brand_logo.changed.connect(self._on_widget_changed)
        self.brand_height = QSpinBox()
        self.brand_height.setRange(8, 1080)
        self.brand_height.setSuffix(" px (at 1080p)")
        self.brand_height.valueChanged.connect(self._on_widget_changed)
        self.brand_opacity = QSlider(Qt.Orientation.Horizontal)
        self.brand_opacity.setRange(0, 100)
        self.brand_opacity.valueChanged.connect(self._on_widget_changed)
        bform.addRow("Logo image", self.brand_logo)
        bform.addRow("Height", self.brand_height)
        bform.addRow("Opacity", self.brand_opacity)
        col.addWidget(brand)
        col.addStretch(1)
        return tab

    def _build_labels_tab(self) -> QWidget:
        tab = QWidget()
        col = QVBoxLayout(tab)
        box = QGroupBox("HUD text labels")
        form = QFormLayout(box)
        self.label_edits: dict[str, QLineEdit] = {}
        defaults = HUDLabels()
        for f in fields(HUDLabels):
            edit = QLineEdit()
            edit.setPlaceholderText(getattr(defaults, f.name))
            edit.textChanged.connect(self._on_widget_changed)
            self.label_edits[f.name] = edit
            form.addRow(LABEL_TITLES.get(f.name, f.name), edit)
        col.addWidget(box)
        note = QLabel("Leave a field empty to use its default (shown in grey). Use plain ASCII characters for best results.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #9aa3ad;")
        col.addWidget(note)
        reset = QPushButton("Restore default labels")
        reset.clicked.connect(self._reset_labels)
        col.addWidget(reset, 0, Qt.AlignmentFlag.AlignLeft)
        col.addStretch(1)
        return tab

    def _build_info_tab(self) -> QWidget:
        tab = QWidget()
        col = QVBoxLayout(tab)
        box = QGroupBox("Extra info panel")
        form = QFormLayout(box)
        self.info_title = QLineEdit()
        self.info_title.setPlaceholderText("e.g. Cyberpunk 2077 – Patch 2.1")
        self.info_title.textChanged.connect(self._on_widget_changed)
        self.info_lines = QPlainTextEdit()
        self.info_lines.setPlaceholderText("One line per row, e.g.\nPerformance Mode\nRay Tracing: Off\nCaptured with Elgato 4K S")
        self.info_lines.textChanged.connect(self._on_widget_changed)
        form.addRow("Title", self.info_title)
        form.addRow("Lines", self.info_lines)
        col.addWidget(box)
        note = QLabel("The panel is hidden when both fields are empty. Position it from the Placement tab or by dragging it in the preview.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #9aa3ad;")
        col.addWidget(note)
        col.addStretch(1)
        return tab

    def _build_layout_tab(self) -> QWidget:
        tab = QWidget()
        col = QVBoxLayout(tab)

        glob = QGroupBox("Global")
        grid = QGridLayout(glob)
        self.hud_scale = QDoubleSpinBox()
        self.hud_scale.setRange(0.25, 3.0)
        self.hud_scale.setSingleStep(0.05)
        self.hud_scale.setSuffix(" ×")
        self.hud_scale.valueChanged.connect(self._on_widget_changed)
        self.panel_opacity = QSlider(Qt.Orientation.Horizontal)
        self.panel_opacity.setRange(0, 100)
        self.panel_opacity.valueChanged.connect(self._on_widget_changed)
        self.show_resolution = QCheckBox("Show resolution section")
        self.show_resolution.toggled.connect(self._on_widget_changed)
        self.show_tear_lines = QCheckBox("Show tear-line edge markers")
        self.show_tear_lines.toggled.connect(self._on_widget_changed)
        grid.addWidget(QLabel("HUD size"), 0, 0)
        grid.addWidget(self.hud_scale, 0, 1)
        grid.addWidget(QLabel("Panel opacity"), 1, 0)
        grid.addWidget(self.panel_opacity, 1, 1)
        grid.addWidget(self.show_resolution, 2, 0, 1, 2)
        grid.addWidget(self.show_tear_lines, 3, 0, 1, 2)
        col.addWidget(glob)

        elems = QGroupBox("Elements (visibility, anchor, offset)")
        ecol = QVBoxLayout(elems)
        self.element_editors: dict[str, ElementEditor] = {}
        for name in ELEMENT_NAMES:
            editor = ElementEditor(name)
            editor.changed.connect(self._on_widget_changed)
            self.element_editors[name] = editor
            ecol.addWidget(editor)
        col.addWidget(elems)

        buttons = QHBoxLayout()
        for text, slot in (
            ("Load layout…", self._load_layout_dialog),
            ("Save layout…", self._save_layout_dialog),
            ("Reset to defaults", self._reset_layout),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            buttons.addWidget(btn)
        buttons.addStretch(1)
        col.addLayout(buttons)
        col.addStretch(1)
        return tab

    def _build_process_panel(self) -> QWidget:
        panel = QWidget()
        row = QHBoxLayout(panel)
        row.setContentsMargins(0, 0, 0, 0)
        self.process_btn = QPushButton("▶  Process Video")
        self.process_btn.setMinimumHeight(36)
        self.process_btn.setStyleSheet("QPushButton { background: #2f8f4e; color: white; font-weight: bold; padding: 0 18px; }"
                                       "QPushButton:disabled { background: #3a3f45; color: #888; }")
        self.process_btn.clicked.connect(self.start_processing)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_processing)
        self.open_folder_btn = QPushButton("Open output folder")
        self.open_folder_btn.setEnabled(False)
        self.open_folder_btn.clicked.connect(self._open_output_folder)
        self.progress = QProgressBar()
        self.progress.setFormat("Ready")
        self.progress.setValue(0)
        row.addWidget(self.process_btn)
        row.addWidget(self.cancel_btn)
        row.addWidget(self.progress, 1)
        row.addWidget(self.open_folder_btn)
        return panel

    # ------------------------------------------------------------------
    # Layout model <-> widgets
    # ------------------------------------------------------------------
    def _sync_widgets_from_layout(self) -> None:
        lay = self.layout_model
        self._syncing = True
        try:
            self.platform_combo.setCurrentText(lay.platform_name)
            self.platform_label.setText(lay.platform_label)
            self.custom_icon.set_text(lay.custom_logo_path)
            self.brand_logo.set_text(lay.brand_logo_path)
            self.brand_height.setValue(lay.brand_logo_height)
            self.brand_opacity.setValue(int(round(lay.brand_logo_opacity * 100)))
            defaults = HUDLabels()
            for name, edit in self.label_edits.items():
                value = getattr(lay.labels, name)
                edit.setText("" if value == getattr(defaults, name) else value)
            self.info_title.setText(lay.extra_info_title)
            self.info_lines.setPlainText("\n".join(lay.extra_info_lines))
            self.hud_scale.setValue(lay.hud_scale)
            self.panel_opacity.setValue(int(round(lay.panel_opacity * 100)))
            self.show_resolution.setChecked(lay.show_resolution)
            self.show_tear_lines.setChecked(lay.show_tear_lines)
            for name in ELEMENT_NAMES:
                self._sync_element_editor(name)
        finally:
            self._syncing = False

    def _sync_element_editor(self, name: str) -> None:
        placement = self.layout_model.element(name)
        editor = self.element_editors[name]
        was_syncing = self._syncing
        self._syncing = True
        try:
            editor.visible.setChecked(placement.visible)
            editor.anchor.setCurrentIndex(ANCHORS.index(placement.anchor))
            editor.offset_x.setValue(placement.offset_x)
            editor.offset_y.setValue(placement.offset_y)
        finally:
            self._syncing = was_syncing

    def _layout_from_widgets(self) -> HUDLayout:
        lay = self.layout_model.copy()
        lay.platform_name = self.platform_combo.currentText().strip()
        lay.platform_label = self.platform_label.text().strip()
        lay.custom_logo_path = self.custom_icon.text() or None
        lay.brand_logo_path = self.brand_logo.text() or None
        lay.brand_logo_height = self.brand_height.value()
        lay.brand_logo_opacity = self.brand_opacity.value() / 100.0
        defaults = HUDLabels()
        for name, edit in self.label_edits.items():
            setattr(lay.labels, name, edit.text() or getattr(defaults, name))
        lay.extra_info_title = self.info_title.text()
        lay.extra_info_lines = self.info_lines.toPlainText().splitlines()
        lay.hud_scale = self.hud_scale.value()
        lay.panel_opacity = self.panel_opacity.value() / 100.0
        lay.show_resolution = self.show_resolution.isChecked()
        lay.show_tear_lines = self.show_tear_lines.isChecked()
        for name, editor in self.element_editors.items():
            p = lay.element(name)
            p.visible = editor.visible.isChecked()
            p.anchor = editor.anchor.currentData()
            p.offset_x = editor.offset_x.value()
            p.offset_y = editor.offset_y.value()
        return lay

    def _on_widget_changed(self, *_: object) -> None:
        if self._syncing:
            return
        self.layout_model = self._layout_from_widgets()
        self._schedule_preview()

    def _set_layout(self, layout: HUDLayout) -> None:
        self.layout_model = layout
        self._sync_widgets_from_layout()
        self._schedule_preview()

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------
    def _schedule_preview(self, *_: object) -> None:
        self._preview_timer.start()

    def _render_preview(self) -> None:
        idx = self.frame_slider.value()
        bgr = self.frame_source.frame(idx)
        h, w = bgr.shape[:2]
        self.preview_hud.layout = self.layout_model
        fps = self.frame_source.fps if self.frame_source.path else 60.0
        metrics = preview_metrics(w, h, self.preview_state.currentText(), idx, target_fps=fps)
        composited = self.preview_hud.composite_on_bgr(bgr, metrics, target_fps=fps, update=False)
        self.canvas.set_frame(composited, self.preview_hud.last_element_rects)
        if self.frame_source.path:
            self.frame_label.setText(f"{idx + 1} / {self.frame_source.total_frames}")

    def _on_element_pressed(self, name: str) -> None:
        p = self.layout_model.element(name)
        self._drag_start = (name, p.offset_x, p.offset_y)
        self.tabs.setCurrentIndex(self.tabs.count() - 1)
        self.element_editors[name].visible.setFocus()

    def _on_element_dragged(self, name: str, dx: float, dy: float) -> None:
        if self._drag_start is None or self._drag_start[0] != name:
            return
        size = self.canvas.image_size()
        rect = self.preview_hud.last_element_rects.get(name)
        if size is None or rect is None:
            return
        img_w, img_h = size
        scale = self.preview_hud.scale_for_height(img_h)
        p = self.layout_model.element(name)
        p.offset_x, p.offset_y = self._drag_start[1], self._drag_start[2]
        p.nudge(dx / scale, dy / scale)
        p.clamp_to_canvas(img_w, img_h, rect[2] - rect[0], rect[3] - rect[1], scale)
        self._sync_element_editor(name)
        self._schedule_preview()

    def _toggle_guides(self, checked: bool) -> None:
        self.canvas.show_guides = checked
        self.canvas.update()

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------
    def _browse_video(self) -> None:
        start = self.input_picker.text() or str(self.settings.value("last_dir", str(Path.home())))
        path, _ = QFileDialog.getOpenFileName(self, "Open capture video", start, VIDEO_FILTER)
        if path:
            self.open_video(path)

    def _on_input_text_changed(self) -> None:
        path = self.input_picker.text()
        if path and path != self.frame_source.path and Path(path).is_file() and is_video_file(path):
            self.open_video(path, quiet=True)

    def open_video(self, path: str, quiet: bool = False) -> None:
        if not path or path == self.frame_source.path:
            return
        try:
            self.frame_source.open(path)
        except FileNotFoundError as exc:
            if not quiet:
                QMessageBox.warning(self, APP_NAME, str(exc))
            return
        src = Path(path)
        self.settings.setValue("last_dir", str(src.parent))
        if self.input_picker.text() != path:
            self.input_picker.set_text(path)
        self.out_video.picker.set_text(str(src.with_name(f"{src.stem}_analyzed.mp4")))
        self.out_alpha.picker.set_text(str(src.with_name(f"{src.stem}_overlay_alpha.mov")))
        self.out_csv.picker.set_text(str(src.with_name(f"{src.stem}_telemetry.csv")))
        self.out_json.picker.set_text(str(src.with_name(f"{src.stem}_summary.json")))

        bgr = self.frame_source.frame(0)
        self.frame_slider.blockSignals(True)
        self.frame_slider.setRange(0, self.frame_source.total_frames - 1)
        self.frame_slider.setValue(min(self.frame_source.total_frames - 1, self.frame_source.total_frames // 3))
        self.frame_slider.blockSignals(False)
        prime_preview_history(self.preview_hud, target_fps=max(30.0, self.frame_source.fps))
        fs = self.frame_source
        duration = fs.total_frames / max(1.0, fs.fps)
        self.video_info.setText(
            f"{fs.width}x{fs.height} • {fs.fps:.2f} fps • {fs.total_frames} frames • {duration:.1f}s"
            + ("" if (fs.width, fs.height) == (bgr.shape[1], bgr.shape[0]) else "  (preview downscaled)")
        )
        self.statusBar().showMessage(f"Loaded {src.name}")
        self._schedule_preview()

    def _load_layout_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load HUD layout", str(self.settings.value("layout_dir", str(Path.home()))), LAYOUT_FILTER)
        if not path:
            return
        try:
            self._set_layout(HUDLayout.load(path))
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, APP_NAME, f"Could not load layout:\n{exc}")
            return
        self.settings.setValue("layout_dir", str(Path(path).parent))
        self.statusBar().showMessage(f"Loaded layout {Path(path).name}")

    def _save_layout_dialog(self) -> None:
        start = Path(str(self.settings.value("layout_dir", str(Path.home())))) / "hud_layout.json"
        path, _ = QFileDialog.getSaveFileName(self, "Save HUD layout", str(start), LAYOUT_FILTER)
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        self.layout_model.save(path)
        self.settings.setValue("layout_dir", str(Path(path).parent))
        self.statusBar().showMessage(f"Saved layout to {path}  (use it from the CLI with: fta analyze … --layout {Path(path).name})")

    def _reset_layout(self) -> None:
        self._set_layout(HUDLayout())

    def _reset_labels(self) -> None:
        lay = self.layout_model.copy()
        lay.labels = HUDLabels()
        self._set_layout(lay)

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------
    def _build_job(self) -> Optional[ProcessingJob]:
        src = self.input_picker.text()
        if not src or not Path(src).is_file():
            QMessageBox.warning(self, APP_NAME, "Please choose an existing input video first.")
            return None
        outputs = [r.path() for r in (self.out_video, self.out_alpha, self.out_csv, self.out_json)]
        if not any(outputs):
            QMessageBox.warning(self, APP_NAME, "Enable at least one output (video, overlay, CSV or JSON).")
            return None
        if any(o is not None and o.resolve() == Path(src).resolve() for o in outputs):
            QMessageBox.warning(self, APP_NAME, "An output path is the same as the input video.")
            return None
        existing = [o for o in outputs if o is not None and o.exists()]
        if existing:
            names = "\n".join(str(o) for o in existing)
            answer = QMessageBox.question(self, APP_NAME, f"These files already exist and will be overwritten:\n\n{names}\n\nContinue?")
            if answer != QMessageBox.StandardButton.Yes:
                return None
        return ProcessingJob(
            video_path=Path(src),
            output_video=outputs[0],
            output_alpha=outputs[1],
            output_csv=outputs[2],
            output_json=outputs[3],
            max_frames=self.max_frames.value() or None,
            detect_tearing=self.detect_tearing.isChecked(),
            detect_resolution=self.detect_resolution.isChecked(),
            layout=self.layout_model.copy(),
        )

    def start_processing(self) -> None:
        if self._worker is not None:
            return
        job = self._build_job()
        if job is None:
            return
        self._last_job = job
        self._worker = ProcessingThread(job)
        self._worker.progress.connect(self._on_progress)
        self._worker.succeeded.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_thread_done)
        self.process_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.open_folder_btn.setEnabled(False)
        self.progress.setFormat("%v / %m frames (%p%)")
        self.progress.setRange(0, 0)
        self.statusBar().showMessage(f"Processing {job.video_path.name}…")
        self._worker.start()

    def cancel_processing(self) -> None:
        if self._worker is not None:
            self._worker.cancel_event.set()
            self.cancel_btn.setEnabled(False)
            self.statusBar().showMessage("Cancelling…")

    def _on_progress(self, done: int, total: int) -> None:
        if self.progress.maximum() != total:
            self.progress.setRange(0, total)
        self.progress.setValue(done)

    def _on_finished(self, result: ProcessingResult) -> None:
        s = result.summary
        self.open_folder_btn.setEnabled(True)
        if result.cancelled:
            self.statusBar().showMessage(f"Cancelled after {s.total_frames} frames – partial outputs were kept.")
            return
        self.statusBar().showMessage(f"Done – {s.total_frames} frames, avg {s.avg_fps:.1f} FPS.")
        files = "\n".join(f"• {p}" for p in result.written_files)
        QMessageBox.information(
            self,
            APP_NAME,
            f"Processing complete.\n\n"
            f"Frames: {s.total_frames} ({s.duration_seconds:.1f}s)\n"
            f"Average FPS: {s.avg_fps:.1f}  (1% low {s.fps_1_percent_low:.1f})\n"
            f"Torn frames: {s.torn_frames} ({s.torn_frames_percent:.2f}%)\n"
            f"Median render resolution: {s.median_render_resolution[0]}x{s.median_render_resolution[1]}\n\n"
            f"Saved:\n{files}",
        )

    def _on_failed(self, message: str) -> None:
        self.statusBar().showMessage("Processing failed.")
        QMessageBox.critical(self, APP_NAME, f"Processing failed:\n\n{message}")

    def _on_thread_done(self) -> None:
        self._worker = None
        self.process_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 1)
            self.progress.setValue(0)

    def _open_output_folder(self) -> None:
        job = getattr(self, "_last_job", None)
        target = next((p for p in (job.output_video, job.output_alpha, job.output_csv, job.output_json) if p), None) if job else None
        if target is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.resolve().parent)))

    # ------------------------------------------------------------------
    # Window events
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".json"):
                try:
                    self._set_layout(HUDLayout.load(path))
                except (OSError, ValueError, TypeError) as exc:
                    QMessageBox.warning(self, APP_NAME, f"Could not load layout:\n{exc}")
            elif is_video_file(path):
                self.open_video(path)
            elif path.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                self.brand_logo.set_text(path)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._worker is not None:
            answer = QMessageBox.question(self, APP_NAME, "A video is still being processed. Cancel it and quit?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._worker.cancel_event.set()
            self._worker.wait(10_000)
        self.settings.setValue("layout_json", json.dumps(self.layout_model.to_dict()))
        self.frame_source.close()
        event.accept()

    def _about(self) -> None:
        QMessageBox.about(
            self,
            APP_NAME,
            f"<b>{APP_NAME}</b><br>Frametime, tearing &amp; render-resolution analyzer with a customizable HUD.<br><br>"
            "Layouts saved here can be reused from the terminal with <code>fta analyze VIDEO --layout layout.json</code>.",
        )


def _apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    base, alt, text, accent = QColor(30, 33, 38), QColor(40, 44, 50), QColor(225, 228, 232), QColor(93, 232, 130)
    pal.setColor(QPalette.ColorRole.Window, alt)
    pal.setColor(QPalette.ColorRole.WindowText, text)
    pal.setColor(QPalette.ColorRole.Base, base)
    pal.setColor(QPalette.ColorRole.AlternateBase, alt)
    pal.setColor(QPalette.ColorRole.ToolTipBase, base)
    pal.setColor(QPalette.ColorRole.ToolTipText, text)
    pal.setColor(QPalette.ColorRole.Text, text)
    pal.setColor(QPalette.ColorRole.Button, QColor(52, 57, 64))
    pal.setColor(QPalette.ColorRole.ButtonText, text)
    pal.setColor(QPalette.ColorRole.Highlight, accent.darker(160))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(130, 136, 145))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(120, 124, 130))
    app.setPalette(pal)


def run_gui(video_path: Optional[Path] = None, layout_path: Optional[Path] = None, argv: Optional[list[str]] = None) -> int:
    """Start the Qt event loop and show the main window. Returns the process exit code."""
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv[:1])
    app.setApplicationName(APP_NAME)
    _apply_dark_theme(app)  # type: ignore[arg-type]
    window = MainWindow(video_path=video_path, layout_path=layout_path)
    window.show()
    return app.exec()


def main() -> None:
    """Entry point for the ``fta-gui`` console script."""
    import argparse

    parser = argparse.ArgumentParser(prog="fta-gui", description=APP_NAME)
    parser.add_argument("video", nargs="?", type=Path, help="Optional capture video to open")
    parser.add_argument("--layout", type=Path, help="Optional HUD layout JSON to open")
    args = parser.parse_args()
    sys.exit(run_gui(video_path=args.video, layout_path=args.layout))


if __name__ == "__main__":
    main()
