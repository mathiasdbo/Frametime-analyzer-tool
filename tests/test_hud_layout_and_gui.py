"""Tests for the customizable HUD layout, the shared processing job and the PySide6 desktop GUI."""
from __future__ import annotations

import json
from pathlib import Path
import cv2
import numpy as np
import pytest
from typer.testing import CliRunner

from frametime_analyzer.cli.cli import app as cli_app
from frametime_analyzer.demo_generator import generate_demo_capture_video
from frametime_analyzer.models import FrameMetrics
from frametime_analyzer.processing import ProcessingJob, process_video
from frametime_analyzer.render.hud_layout import ElementPlacement, HUDLayout
from frametime_analyzer.render.hud_renderer import HUDRenderer


def _metrics(torn: bool = False) -> FrameMetrics:
    return FrameMetrics(
        frame_index=0,
        timestamp_ms=0.0,
        frame_duration_ms=16.67,
        is_duplicate=False,
        is_torn=torn,
        tear_line_y=[300] if torn else [],
    )


@pytest.mark.parametrize(
    ("anchor", "expected"),
    [
        ("top-left", (36, 36)),
        ("top-right", (1920 - 100 - 36, 36)),
        ("bottom-left", (36, 1080 - 50 - 36)),
        ("bottom-right", (1920 - 100 - 36, 1080 - 50 - 36)),
        ("center", ((1920 - 100) // 2 + 36, (1080 - 50) // 2 + 36)),
        ("top-center", ((1920 - 100) // 2 + 36, 36)),
        ("middle-right", (1920 - 100 - 36, (1080 - 50) // 2 + 36)),
    ],
)
def test_anchor_resolution(anchor: str, expected: tuple[int, int]) -> None:
    assert ElementPlacement(True, anchor, 36, 36).resolve(1920, 1080, 100, 50, 1.0) == expected


def test_nudge_and_clamp_follow_anchor_direction() -> None:
    p = ElementPlacement(True, "bottom-right", 36, 36)
    p.nudge(10, 10)  # Dragging right/down moves towards the anchored corner
    assert (p.offset_x, p.offset_y) == (26, 26)
    p.nudge(5000, -5000)
    p.clamp_to_canvas(1920, 1080, 100, 50, 1.0)
    assert (p.offset_x, p.offset_y) == (0, 1030)
    with pytest.raises(ValueError):
        ElementPlacement(True, "nowhere", 0, 0)


def test_layout_json_round_trip_and_partial_load(tmp_path: Path) -> None:
    layout = HUDLayout(platform_name="Switch 2", extra_info_title="Zelda", extra_info_lines=["Docked", "4K"])
    layout.labels.fps_unit = "IPS"
    layout.elements["stats_card"] = ElementPlacement(False, "bottom-center", 0, 12)
    path = layout.save(tmp_path / "layout.json")
    assert HUDLayout.load(path) == layout

    partial = HUDLayout.from_dict({"labels": {"fps_unit": "X"}, "elements": {"fps_graph": {"anchor": "top-left"}}, "bogus": 1})
    assert partial.labels.fps_unit == "X"
    assert partial.labels.one_percent_low == "1% LOW"
    assert partial.element("fps_graph").anchor == "top-left"
    assert partial.element("fps_graph").offset_x == 36


def test_renderer_respects_layout(tmp_path: Path) -> None:
    logo_path = tmp_path / "logo.png"
    logo = np.zeros((40, 80, 4), dtype=np.uint8)
    logo[:, :] = (0, 0, 255, 255)
    cv2.imwrite(str(logo_path), logo)

    layout = HUDLayout(
        extra_info_title="Game Title",
        extra_info_lines=["Performance Mode"],
        brand_logo_path=str(logo_path),
        platform_label="CUSTOM BADGE",
    )
    layout.elements["frametime_graph"].visible = False
    layout.elements["stats_card"] = ElementPlacement(True, "center", 0, 0)
    hud = HUDRenderer(layout=layout)
    overlay = hud.render_rgba_overlay(1920, 1080, _metrics(torn=True))

    rects = hud.last_element_rects
    assert "frametime_graph" not in rects
    assert {"platform_badge", "stats_card", "fps_graph", "extra_info", "brand_logo"} <= set(rects)
    x0, y0, x1, y1 = rects["stats_card"]
    assert abs((x0 + x1) / 2 - 960) <= 2 and abs((y0 + y1) / 2 - 540) <= 2
    bx0, by0, bx1, by1 = rects["brand_logo"]
    assert (bx1 - bx0, by1 - by0) == (180, 90)
    assert tuple(overlay[by0 + 10, bx0 + 10]) == (0, 0, 255, 255)
    # Elements are kept on-canvas even with extreme offsets
    layout.elements["extra_info"].offset_x = 99999
    hud = HUDRenderer(layout=layout)
    hud.render_rgba_overlay(1280, 720, _metrics())
    assert hud.last_element_rects["extra_info"][2] <= 1280


def test_default_layout_matches_legacy_positions() -> None:
    hud = HUDRenderer()
    hud.render_rgba_overlay(1920, 1080, _metrics())
    assert hud.last_element_rects["stats_card"][:2] == (1920 - 410 - 36, 78)
    assert hud.last_element_rects["fps_graph"][3] == 1080 - 36
    assert "extra_info" not in hud.last_element_rects  # No extra info configured


def test_processing_job_and_cli_layout(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    generate_demo_capture_video(clip, width=640, height=360, fps=60.0, total_frames=20)
    layout = HUDLayout(extra_info_lines=["From layout"])
    progress: list[tuple[int, int]] = []
    result = process_video(
        ProcessingJob(video_path=clip, output_video=tmp_path / "out.mp4", output_csv=tmp_path / "t.csv", layout=layout),
        progress=lambda done, total: progress.append((done, total)),
    )
    assert not result.cancelled and result.summary.total_frames == 20
    assert progress[-1] == (20, 20)
    assert (tmp_path / "out.mp4").stat().st_size > 1000 and (tmp_path / "t.csv").exists()

    layout_path = layout.save(tmp_path / "layout.json")
    cli = CliRunner().invoke(
        cli_app,
        ["analyze", str(clip), "--layout", str(layout_path), "--info", "Line A", "-j", str(tmp_path / "s.json"), "--max-frames", "10"],
    )
    assert cli.exit_code == 0, cli.output
    assert json.loads((tmp_path / "s.json").read_text())["summary"]["total_frames"] == 10


def test_gui_main_window_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # Missing system Qt libraries (e.g. libEGL) on headless CI
        pytest.skip(f"Qt not loadable: {exc}")
    from PySide6.QtCore import QSettings

    from frametime_analyzer.gui import app as gui_app
    from frametime_analyzer.gui.app import MainWindow

    # Never block on modal dialogs in tests
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(gui_app.QMessageBox, name, staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(gui_app.QMessageBox, "question", staticmethod(lambda *a, **k: gui_app.QMessageBox.StandardButton.Yes))

    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path / "qsettings"))
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "qsettings"))
    qapp = QApplication.instance() or QApplication([])

    clip = tmp_path / "gui_clip.mp4"
    generate_demo_capture_video(clip, width=640, height=360, fps=60.0, total_frames=12)
    window = MainWindow(video_path=clip)
    window._render_preview()
    assert window.frame_slider.maximum() == 11
    assert window.out_video.path() == tmp_path / "gui_clip_analyzed.mp4"

    # Editing widgets updates the layout model
    window.label_edits["fps_unit"].setText("IPS")
    window.info_lines.setPlainText("Line 1\nLine 2")
    window.element_editors["stats_card"].anchor.setCurrentIndex(0)  # top-left
    assert window.layout_model.labels.fps_unit == "IPS"
    assert window.layout_model.extra_info_lines == ["Line 1", "Line 2"]
    assert window.layout_model.element("stats_card").anchor == "top-left"

    # Dragging in the preview moves the element and updates the spin boxes
    window._render_preview()
    window._on_element_pressed("fps_graph")
    window._on_element_dragged("fps_graph", 20.0, -20.0)
    fps_graph = window.layout_model.element("fps_graph")
    assert fps_graph.offset_x > 36 and fps_graph.offset_y > 36
    assert window.element_editors["fps_graph"].offset_x.value() == fps_graph.offset_x

    # Run a full processing job through the worker thread
    window.out_alpha.check.setChecked(False)
    job = window._build_job()
    assert job is not None and job.layout.labels.fps_unit == "IPS"
    window.start_processing()
    worker = window._worker
    assert worker is not None
    assert worker.wait(60_000)
    qapp.processEvents()
    assert (tmp_path / "gui_clip_analyzed.mp4").stat().st_size > 1000
    window.close()
