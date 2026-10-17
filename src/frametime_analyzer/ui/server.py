"""FastAPI backend for the Interactive Frametime & Resolution Studio and OBS Live Overlay."""
from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import threading
from typing import Any, Optional
import cv2
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
import numpy as np
from pydantic import BaseModel

from frametime_analyzer.core.pipeline import AnalysisPipeline
from frametime_analyzer.demo_generator import generate_demo_capture_video
from frametime_analyzer.ingest.stream_reader import VideoFileReader, list_capture_devices
from frametime_analyzer.models import AnalysisSummary, AnalyzerConfig, FrameMetrics
from frametime_analyzer.render.hud_renderer import HUDRenderer
from frametime_analyzer.render.video_exporter import (
    VideoExporter,
    export_summary_json,
    export_telemetry_csv,
)


class LoadVideoRequest(BaseModel):
    video_path: Optional[str] = None
    generate_demo: bool = False


class PixelCountRequest(BaseModel):
    frame_index: int
    x1: int
    y1: int
    x2: int
    y2: int


class ExportRequest(BaseModel):
    output_dir: Optional[str] = None
    export_burned_mp4: bool = True
    export_alpha_mov: bool = False
    export_csv: bool = True
    platform_name: str = "PS5"


class StudioState:
    """Holds the currently loaded video, analyzed frame metrics, and background progressive analyzer."""

    INITIAL_SYNC_FRAMES = 60

    def __init__(self, initial_video: Optional[str] = None, max_frames: Optional[int] = None) -> None:
        self.config = AnalyzerConfig()
        self.pipeline = AnalysisPipeline(self.config)
        self.hud = HUDRenderer()
        self.platform_name: str = "PS5"
        self.video_path: Optional[str] = None
        self.reader: Optional[VideoFileReader] = None
        self.metrics: list[FrameMetrics] = []
        self.summary: Optional[AnalysisSummary] = None
        self.is_analyzing: bool = False
        self.total_expected_frames: int = 0
        self.max_frames: Optional[int] = max_frames
        self._reader_lock = threading.Lock()
        self._job_id = 0
        self._temp_dir = Path(tempfile.mkdtemp(prefix="fta_studio_"))

        if initial_video and Path(initial_video).exists():
            self.load_video(initial_video)

    def load_video(self, path: str) -> AnalysisSummary:
        self._job_id += 1
        current_job = self._job_id

        with self._reader_lock:
            if self.reader is not None:
                self.reader.close()
            self.reader = VideoFileReader(path, analysis_width=self.config.analysis_width, max_frames=self.max_frames)
            total_est = self.reader.total_frames
            if self.max_frames is not None and total_est > 0:
                total_est = min(total_est, self.max_frames)
            self.total_expected_frames = total_est

        # Synchronously analyze the first INITIAL_SYNC_FRAMES so startup is instant (<0.3s)
        sync_limit = self.INITIAL_SYNC_FRAMES
        if self.max_frames is not None:
            sync_limit = min(sync_limit, self.max_frames)

        stream_reader = VideoFileReader(path, analysis_width=self.config.analysis_width, max_frames=self.max_frames)
        self.pipeline.reset()
        self.hud.reset()
        initial_metrics: list[FrameMetrics] = []
        stream_iter = iter(stream_reader)
        for _ in range(sync_limit):
            try:
                pkt = next(stream_iter)
            except StopIteration:
                break
            initial_metrics.append(self.pipeline.process_packet(pkt))

        self.metrics = initial_metrics
        self.video_path = path
        self.summary = self.pipeline.build_summary(source_path=path, container_fps=stream_reader.fps)

        # If more frames remain in the stream, continue analyzing progressively in a background thread
        has_more = (self.max_frames is None or len(initial_metrics) < self.max_frames) and (
            len(initial_metrics) == sync_limit
        )
        if has_more:
            self.is_analyzing = True
            worker = threading.Thread(
                target=self._continue_analysis_worker,
                args=(current_job, path, stream_reader, stream_iter),
                daemon=True,
            )
            worker.start()
        else:
            self.is_analyzing = False
            self.total_expected_frames = len(self.metrics)
            stream_reader.close()

        return self.summary

    def _continue_analysis_worker(
        self,
        job_id: int,
        path: str,
        stream_reader: VideoFileReader,
        stream_iter: Any,
    ) -> None:
        try:
            count_since_update = 0
            for pkt in stream_iter:
                if self._job_id != job_id:
                    return
                m = self.pipeline.process_packet(pkt)
                self.metrics.append(m)
                count_since_update += 1
                if count_since_update >= 90:
                    self.summary = self.pipeline.build_summary(source_path=path, container_fps=stream_reader.fps)
                    count_since_update = 0
            if self._job_id == job_id:
                self.summary = self.pipeline.build_summary(source_path=path, container_fps=stream_reader.fps)
                self.total_expected_frames = len(self.metrics)
                self.is_analyzing = False
        finally:
            stream_reader.close()

    def load_or_create_demo(self) -> AnalysisSummary:
        demo_path = self._temp_dir / "elgato_synthetic_demo.mp4"
        if not demo_path.exists():
            generate_demo_capture_video(demo_path, width=1280, height=720, fps=60.0, total_frames=180)
        return self.load_video(str(demo_path))


def create_app(initial_video: Optional[str] = None, max_frames: Optional[int] = None) -> FastAPI:
    app = FastAPI(title="Frametime & Resolution Analyzer Studio", version="0.1.0")
    state = StudioState(initial_video=initial_video, max_frames=max_frames)
    static_dir = Path(__file__).parent / "static"

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index_page() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/obs-overlay", response_class=HTMLResponse)
    def obs_overlay_page() -> FileResponse:
        return FileResponse(static_dir / "obs_overlay.html")

    @app.get("/api/status")
    def get_status() -> dict[str, Any]:
        if state.summary is None:
            state.load_or_create_demo()
        return {
            "loaded": state.video_path is not None,
            "video_path": state.video_path,
            "platform_name": state.platform_name,
            "is_analyzing": state.is_analyzing,
            "analyzed_frames": len(state.metrics),
            "total_expected_frames": state.total_expected_frames,
            "summary": state.summary.to_dict() if state.summary else None,
        }

    @app.get("/api/devices")
    def get_devices() -> dict[str, Any]:
        return {"capture_devices": list_capture_devices(max_devices=3)}

    @app.post("/api/load")
    def load_video_endpoint(req: LoadVideoRequest) -> dict[str, Any]:
        if req.generate_demo or not req.video_path:
            summary = state.load_or_create_demo()
        else:
            if not Path(req.video_path).exists():
                raise HTTPException(status_code=404, detail=f"Video file not found: {req.video_path}")
            summary = state.load_video(req.video_path)
        return {
            "video_path": state.video_path,
            "summary": summary.to_dict(),
            "total_frames": len(state.metrics),
            "is_analyzing": state.is_analyzing,
            "total_expected_frames": state.total_expected_frames,
        }

    @app.get("/api/telemetry")
    def get_telemetry() -> dict[str, Any]:
        if state.summary is None:
            state.load_or_create_demo()
        return {
            "video_path": state.video_path,
            "is_analyzing": state.is_analyzing,
            "analyzed_frames": len(state.metrics),
            "total_expected_frames": state.total_expected_frames,
            "summary": state.summary.to_dict() if state.summary else None,
            "frames": [m.to_dict() for m in state.metrics],
        }

    @app.get("/api/frame/{frame_index}")
    def get_frame_image(
        frame_index: int,
        mode: str = Query("raw", description="raw | overlay | diff"),
        platform: str = Query("PS5", description="Console/Platform badge name"),
    ) -> Response:
        if state.reader is None or not state.metrics:
            state.load_or_create_demo()
        assert state.reader is not None
        state.platform_name = platform

        clamped = max(0, min(frame_index, len(state.metrics) - 1))
        with state._reader_lock:
            packet = state.reader.read_frame_at(clamped)
            prev_packet = state.reader.read_frame_at(clamped - 1) if (mode == "diff" and clamped > 0) else None
        bgr = packet.raw_bgr

        if mode == "overlay":
            hud_temp = HUDRenderer(platform_name=platform)
            start_idx = max(0, clamped - hud_temp.fps_history_len)
            for m in state.metrics[start_idx : clamped + 1]:
                hud_temp.update_history(m)
            bgr = hud_temp.composite_on_bgr(
                bgr,
                state.metrics[clamped],
                target_fps=state.reader.fps,
                update=False,
            )
        elif mode == "diff" and prev_packet is not None:
            diff_gray = cv2.absdiff(
                cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY),
                cv2.cvtColor(prev_packet.raw_bgr, cv2.COLOR_BGR2GRAY),
            )
            boosted = np.clip(diff_gray.astype(np.float32) * 6.0, 0, 255).astype(np.uint8)
            bgr = cv2.applyColorMap(boosted, cv2.COLORMAP_INFERNO)
            for ty in state.metrics[clamped].tear_line_y:
                if 0 <= ty < bgr.shape[0]:
                    cv2.line(bgr, (0, ty), (bgr.shape[1] - 1, ty), (80, 255, 80), 2)

        ok, encoded = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to encode frame")
        return Response(content=encoded.tobytes(), media_type="image/jpeg")

    @app.post("/api/pixel-count")
    def pixel_count_endpoint(req: PixelCountRequest) -> dict[str, Any]:
        if state.reader is None or not state.metrics:
            state.load_or_create_demo()
        assert state.reader is not None
        with state._reader_lock:
            packet = state.reader.read_frame_at(req.frame_index)
        sample = state.pipeline.resolution_analyzer.count_edge_stair_steps(
            packet.raw_bgr, req.x1, req.y1, req.x2, req.y2
        )
        return sample.to_dict()

    @app.get("/api/auto-edges/{frame_index}")
    def auto_edges_endpoint(frame_index: int) -> dict[str, Any]:
        if state.reader is None or not state.metrics:
            state.load_or_create_demo()
        assert state.reader is not None
        with state._reader_lock:
            packet = state.reader.read_frame_at(frame_index)
        candidates = state.pipeline.resolution_analyzer.auto_find_stair_step_candidates(
            packet.raw_bgr, max_candidates=6
        )
        return {
            "frame_index": frame_index,
            "candidates": [c.to_dict() for c in candidates],
        }

    @app.post("/api/export")
    def export_endpoint(req: ExportRequest) -> dict[str, Any]:
        if state.reader is None or not state.metrics or state.summary is None or state.video_path is None:
            state.load_or_create_demo()
        assert state.reader is not None and state.summary is not None and state.video_path is not None

        out_dir = Path(req.output_dir) if req.output_dir else Path(state.video_path).parent / "fta_exports"
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(state.video_path).stem
        outputs: dict[str, str] = {}

        if req.export_csv:
            csv_path = export_telemetry_csv(state.metrics, out_dir / f"{stem}_telemetry.csv")
            json_path = export_summary_json(state.summary, out_dir / f"{stem}_summary.json", state.metrics)
            outputs["csv"] = str(csv_path)
            outputs["json"] = str(json_path)

        if req.export_burned_mp4 or req.export_alpha_mov:
            read_stream = VideoFileReader(
                state.video_path, analysis_width=state.config.analysis_width, max_frames=len(state.metrics)
            )
            hud = HUDRenderer(platform_name=req.platform_name)
            burn_exp = (
                VideoExporter(
                    out_dir / f"{stem}_analyzed.mp4",
                    width=read_stream.width,
                    height=read_stream.height,
                    fps=read_stream.fps,
                    alpha_only=False,
                    source_audio_path=state.video_path,
                )
                if req.export_burned_mp4
                else None
            )
            alpha_exp = (
                VideoExporter(
                    out_dir / f"{stem}_overlay_alpha.mov",
                    width=read_stream.width,
                    height=read_stream.height,
                    fps=read_stream.fps,
                    alpha_only=True,
                )
                if req.export_alpha_mov
                else None
            )
            try:
                for pkt in read_stream:
                    idx = min(pkt.frame_index, len(state.metrics) - 1)
                    m = state.metrics[idx]
                    hud.update_history(m)
                    if burn_exp is not None:
                        comp = hud.composite_on_bgr(pkt.raw_bgr, m, target_fps=read_stream.fps, update=False)
                        burn_exp.write_frame(comp)
                    if alpha_exp is not None:
                        rgba = hud.render_rgba_overlay(
                            pkt.width, pkt.height, m, target_fps=read_stream.fps, update=False
                        )
                        alpha_exp.write_frame(rgba)
            finally:
                if burn_exp is not None:
                    burn_exp.close()
                    outputs["burned_mp4"] = str(out_dir / f"{stem}_analyzed.mp4")
                if alpha_exp is not None:
                    alpha_exp.close()
                    outputs["alpha_mov"] = str(out_dir / f"{stem}_overlay_alpha.mov")

        return {"status": "ok", "outputs": outputs}

    @app.websocket("/ws/live")
    async def websocket_live_telemetry(websocket: WebSocket) -> None:
        await websocket.accept()
        if not state.metrics:
            state.load_or_create_demo()
        idx = 0
        try:
            while True:
                if state.metrics:
                    m = state.metrics[idx % len(state.metrics)]
                    await websocket.send_json(m.to_dict())
                    idx += 1
                await asyncio.sleep(1.0 / 60.0)
        except WebSocketDisconnect:
            return

    return app
