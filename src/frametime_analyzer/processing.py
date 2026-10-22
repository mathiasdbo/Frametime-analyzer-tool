"""Reusable offline video processing job shared by the CLI (`fta analyze`) and the desktop GUI (`fta gui`)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Callable, Optional

from frametime_analyzer.core.pipeline import AnalysisPipeline
from frametime_analyzer.core.resolution_override import ResolutionOverride
from frametime_analyzer.ingest.stream_reader import VideoFileReader
from frametime_analyzer.models import AnalysisSummary, AnalyzerConfig, FrameMetrics
from frametime_analyzer.render.hud_layout import HUDLayout
from frametime_analyzer.render.hud_renderer import HUDRenderer
from frametime_analyzer.render.video_exporter import (
    VideoExporter,
    export_summary_json,
    export_telemetry_csv,
)

ProgressCallback = Callable[[int, int], None]


@dataclass
class ProcessingJob:
    """Inputs, outputs and HUD layout for one offline analysis run."""

    video_path: Path
    output_video: Optional[Path] = None
    output_alpha: Optional[Path] = None
    output_csv: Optional[Path] = None
    output_json: Optional[Path] = None
    max_frames: Optional[int] = None
    detect_tearing: bool = True
    detect_resolution: bool = True
    layout: HUDLayout = field(default_factory=HUDLayout)
    resolution_override: Optional[ResolutionOverride] = None


@dataclass
class ProcessingResult:
    summary: AnalysisSummary
    metrics: list[FrameMetrics]
    cancelled: bool = False
    written_files: list[Path] = field(default_factory=list)


def process_video(
    job: ProcessingJob,
    progress: Optional[ProgressCallback] = None,
    cancel_event: Optional[Event] = None,
) -> ProcessingResult:
    """Analyze ``job.video_path``, writing every requested output.

    Args:
        progress: Called as ``progress(frames_done, total_frames)`` after each frame.
        cancel_event: When set, processing stops after the current frame; outputs written so far are finalized.
    """
    override = job.resolution_override if job.resolution_override is not None and job.resolution_override.is_active else None
    # Fully manual resolutions make the (expensive) automatic estimator unnecessary
    fully_manual = override is not None and override.target is not None and override.render_mode == "fixed"
    config = AnalyzerConfig(detect_tearing=job.detect_tearing, detect_resolution=job.detect_resolution and not fully_manual)
    pipeline = AnalysisPipeline(config, resolution_override=override)
    reader = VideoFileReader(job.video_path, analysis_width=config.analysis_width, max_frames=job.max_frames)
    show_resolution = job.layout.show_resolution and (job.detect_resolution or override is not None)
    hud = HUDRenderer(layout=job.layout, show_resolution_badge=show_resolution)
    total = max(1, reader.total_frames)

    burn_exporter: Optional[VideoExporter] = None
    alpha_exporter: Optional[VideoExporter] = None
    cancelled = False
    try:
        if job.output_video is not None:
            burn_exporter = VideoExporter(
                job.output_video,
                width=reader.width,
                height=reader.height,
                fps=reader.fps,
                alpha_only=False,
                source_audio_path=job.video_path,
            )
        if job.output_alpha is not None:
            alpha_exporter = VideoExporter(
                job.output_alpha,
                width=reader.width,
                height=reader.height,
                fps=reader.fps,
                alpha_only=True,
            )

        done = 0
        for packet in reader:
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                break
            metrics = pipeline.process_packet(packet)
            hud.update_history(metrics)

            if burn_exporter is not None:
                burn_exporter.write_frame(hud.composite_on_bgr(packet.raw_bgr, metrics, target_fps=reader.fps, update=False))
            if alpha_exporter is not None:
                alpha_exporter.write_frame(
                    hud.render_rgba_overlay(packet.width, packet.height, metrics, target_fps=reader.fps, update=False)
                )

            done += 1
            if progress is not None:
                progress(done, total)
    finally:
        reader.stop()
        if burn_exporter is not None:
            burn_exporter.close()
        if alpha_exporter is not None:
            alpha_exporter.close()

    summary = pipeline.build_summary(source_path=str(job.video_path), container_fps=reader.fps)
    written: list[Path] = [p for p in (job.output_video, job.output_alpha) if p is not None]
    if job.output_csv is not None:
        written.append(export_telemetry_csv(pipeline.metrics_history, job.output_csv))
    if job.output_json is not None:
        written.append(export_summary_json(summary, job.output_json, pipeline.metrics_history))
    return ProcessingResult(summary=summary, metrics=pipeline.metrics_history, cancelled=cancelled, written_files=written)
