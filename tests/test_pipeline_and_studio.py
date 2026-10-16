"""End-to-end tests for pipeline, exporters, and FastAPI Studio endpoints."""
from __future__ import annotations

from pathlib import Path
from fastapi.testclient import TestClient

from frametime_analyzer.core.pipeline import AnalysisPipeline
from frametime_analyzer.demo_generator import generate_demo_capture_video
from frametime_analyzer.ingest.stream_reader import VideoFileReader
from frametime_analyzer.render.hud_renderer import HUDRenderer
from frametime_analyzer.render.video_exporter import (
    VideoExporter,
    export_summary_json,
    export_telemetry_csv,
)
from frametime_analyzer.ui.server import create_app


def test_end_to_end_pipeline_and_exporters(tmp_path: Path) -> None:
    clip_path = tmp_path / "test_clip.mp4"
    generate_demo_capture_video(clip_path, width=640, height=360, fps=60.0, total_frames=45)

    reader = VideoFileReader(clip_path, analysis_width=320)
    pipeline = AnalysisPipeline()
    hud = HUDRenderer()

    burned_out = tmp_path / "burned.mp4"
    csv_out = tmp_path / "telemetry.csv"
    json_out = tmp_path / "summary.json"

    with VideoExporter(burned_out, width=reader.width, height=reader.height, fps=reader.fps) as exporter:
        for pkt in reader:
            m = pipeline.process_packet(pkt)
            comp = hud.composite_on_bgr(pkt.raw_bgr, m, target_fps=reader.fps)
            exporter.write_frame(comp)

    summary = pipeline.build_summary(source_path=str(clip_path), container_fps=reader.fps)
    export_telemetry_csv(pipeline.metrics_history, csv_out)
    export_summary_json(summary, json_out, pipeline.metrics_history)

    assert summary.total_frames == 45
    assert burned_out.exists() and burned_out.stat().st_size > 1000
    assert csv_out.exists() and csv_out.stat().st_size > 200
    assert json_out.exists() and json_out.stat().st_size > 200


def test_studio_api_endpoints(tmp_path: Path) -> None:
    clip_path = tmp_path / "studio_clip.mp4"
    generate_demo_capture_video(clip_path, width=640, height=360, fps=60.0, total_frames=30)

    app = create_app(initial_video=str(clip_path))
    client = TestClient(app)

    status_res = client.get("/api/status")
    assert status_res.status_code == 200
    assert status_res.json()["loaded"] is True

    tel_res = client.get("/api/telemetry")
    assert tel_res.status_code == 200
    assert len(tel_res.json()["frames"]) == 30

    frame_res = client.get("/api/frame/5?mode=overlay")
    assert frame_res.status_code == 200
    assert frame_res.headers["content-type"] == "image/jpeg"

    pc_res = client.post("/api/pixel-count", json={"frame_index": 5, "x1": 100, "y1": 100, "x2": 180, "y2": 130})
    assert pc_res.status_code == 200
    assert "estimated_render_height" in pc_res.json()
