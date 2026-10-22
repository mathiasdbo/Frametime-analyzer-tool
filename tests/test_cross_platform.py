"""Cross-platform behaviour: encoder selection, ffmpeg error reporting, capture backends and unicode paths."""
from __future__ import annotations

from pathlib import Path
import cv2
import numpy as np
import pytest

from frametime_analyzer.ingest.stream_reader import capture_backends
from frametime_analyzer.render import video_exporter
from frametime_analyzer.render.hud_layout import HUDLayout
from frametime_analyzer.render.hud_renderer import HUDRenderer
from frametime_analyzer.render.platform_logos import read_image_unchanged
from frametime_analyzer.render.video_exporter import (
    SOFTWARE_H264,
    VideoExporter,
    get_ffmpeg_binary,
    hardware_encoder_candidates,
    select_h264_encoder,
)


def test_hardware_encoder_candidates_per_os() -> None:
    assert [e.name for e in hardware_encoder_candidates("Darwin")] == ["h264_videotoolbox"]
    assert [e.name for e in hardware_encoder_candidates("Windows")] == ["h264_nvenc", "h264_qsv", "h264_amf"]
    assert [e.name for e in hardware_encoder_candidates("Linux")] == ["h264_nvenc", "h264_vaapi", "h264_qsv"]


def test_encoder_selection_falls_back_and_can_be_forced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FTA_VIDEO_ENCODER", raising=False)
    monkeypatch.setattr(video_exporter, "_encoder_works", lambda *_: False)
    assert select_h264_encoder("ffmpeg") is SOFTWARE_H264
    assert select_h264_encoder("ffmpeg", use_hardware_accel=False) is SOFTWARE_H264

    monkeypatch.setattr(video_exporter, "_encoder_works", lambda _bin, enc: enc.name == "h264_qsv")
    monkeypatch.setattr(video_exporter.platform, "system", lambda: "Windows")
    assert select_h264_encoder("ffmpeg").name == "h264_qsv"

    monkeypatch.setenv("FTA_VIDEO_ENCODER", "libx264")
    assert select_h264_encoder("ffmpeg") is SOFTWARE_H264


def test_software_encoder_probe_works() -> None:
    ffmpeg = get_ffmpeg_binary()
    assert ffmpeg is not None
    assert video_exporter._encoder_works(ffmpeg, SOFTWARE_H264)


def test_exporter_reports_ffmpeg_failures(tmp_path: Path) -> None:
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    with pytest.raises(RuntimeError, match="ffmpeg"):
        with VideoExporter(tmp_path / "bad.unknown_ext", 64, 64, fps=30.0, use_hardware_accel=False) as exporter:
            for _ in range(200):
                exporter.write_frame(frame)


def test_exporter_writes_mp4(tmp_path: Path) -> None:
    out = tmp_path / "ok.mp4"
    with VideoExporter(out, 128, 72, fps=30.0, use_hardware_accel=False) as exporter:
        for i in range(10):
            exporter.write_frame(np.full((72, 128, 3), i * 20, dtype=np.uint8))
    assert exporter.encoder_name == "libx264"
    cap = cv2.VideoCapture(str(out))
    assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 10
    cap.release()


@pytest.mark.parametrize(
    ("system", "first"),
    [("Darwin", cv2.CAP_AVFOUNDATION), ("Windows", cv2.CAP_DSHOW), ("Linux", cv2.CAP_V4L2)],
)
def test_capture_backends_per_os(system: str, first: int) -> None:
    backends = capture_backends(system)
    assert backends[0] == first and backends[-1] == cv2.CAP_ANY


def test_logos_load_from_non_ascii_paths(tmp_path: Path) -> None:
    folder = tmp_path / "Usuário José 日本"
    folder.mkdir()
    logo_path = folder / "logo ñ.png"
    ok, encoded = cv2.imencode(".png", np.full((20, 40, 4), 255, dtype=np.uint8))
    assert ok
    logo_path.write_bytes(encoded.tobytes())

    img = read_image_unchanged(str(logo_path))
    assert img is not None and img.shape == (20, 40, 4)
    assert read_image_unchanged(str(folder / "missing.png")) is None

    hud = HUDRenderer(layout=HUDLayout(brand_logo_path=str(logo_path), custom_logo_path=str(logo_path)))
    from frametime_analyzer.models import FrameMetrics

    hud.render_rgba_overlay(1280, 720, FrameMetrics(0, 0.0, 16.7, False, False))
    assert "brand_logo" in hud.last_element_rects
