"""CLI entry point (`fta`) for Frametime, Tearing, and Resolution Analysis."""
from __future__ import annotations

from pathlib import Path
from typing import Optional
import cv2
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
import typer
import uvicorn

from frametime_analyzer.core.pipeline import AnalysisPipeline
from frametime_analyzer.demo_generator import generate_demo_capture_video
from frametime_analyzer.ingest.stream_reader import (
    LiveCaptureReader,
    VideoFileReader,
    list_capture_devices,
)
from frametime_analyzer.models import AnalysisSummary, AnalyzerConfig
from frametime_analyzer.render.hud_renderer import HUDRenderer
from frametime_analyzer.render.video_exporter import (
    VideoExporter,
    export_summary_json,
    export_telemetry_csv,
)
from frametime_analyzer.ui.server import create_app

app = typer.Typer(
    name="fta",
    help="Frametime, Tearing & Internal Render Resolution Analyzer for Elgato 4K S and capture footage.",
    add_completion=False,
)
console = Console()


def _print_summary_table(summary: AnalysisSummary) -> None:
    table = Table(title="Frametime & Resolution Analysis Summary", show_header=True, header_style="bold green")
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="bold white")

    table.add_row("Source", summary.source_path)
    table.add_row("Total Frames", f"{summary.total_frames} ({summary.duration_seconds:.2f}s @ {summary.container_fps:.2f} Hz)")
    table.add_row("Unique / Duplicate Frames", f"{summary.unique_frames} unique / {summary.duplicate_frames} duplicate")
    table.add_row("Screen Tearing", f"{summary.torn_frames} torn frames ({summary.torn_frames_percent:.2f}%)")
    table.add_row("Average / Min / Max FPS", f"{summary.avg_fps:.1f} / {summary.min_fps:.1f} / {summary.max_fps:.1f} FPS")
    table.add_row("1% Low / 0.1% Low FPS", f"{summary.fps_1_percent_low:.1f} / {summary.fps_0_1_percent_low:.1f} FPS")
    table.add_row(
        "Frametime (Avg / P99 / Max)",
        f"{summary.avg_frametime_ms:.2f} ms / {summary.p99_frametime_ms:.2f} ms / {summary.max_frametime_ms:.2f} ms",
    )
    cw, ch = summary.container_resolution
    tw, th = summary.target_resolution
    min_rw, min_rh = summary.min_render_resolution
    max_rw, max_rh = summary.max_render_resolution
    med_rw, med_rh = summary.median_render_resolution
    table.add_row("Container / Target Resolution", f"{cw}x{ch} / {tw}x{th} ({th}p)")
    table.add_row(
        "Estimated Internal Render Res",
        f"Median {med_rw}x{med_rh} (Range: {min_rw}x{min_rh} – {max_rw}x{max_rh})",
    )
    table.add_row(
        "Dynamic Resolution Scaling (DRS)",
        f"{'YES (Active DRS Detected)' if summary.is_dynamic_resolution else 'NO (Locked Resolution)'} "
        f"(Avg Confidence: {summary.avg_resolution_confidence * 100:.0f}%)",
    )
    console.print(table)


@app.command("analyze")
def analyze_video(
    video_path: Path = typer.Argument(..., exists=True, help="Input gameplay capture video (MP4/MKV/MOV)"),
    output_video: Optional[Path] = typer.Option(None, "--output-video", "-o", help="Output burned-in HUD video (.mp4/.mov)"),
    output_alpha: Optional[Path] = typer.Option(None, "--output-alpha", "-a", help="Output transparent alpha HUD overlay (.mov ProRes 4444 or .webm)"),
    output_csv: Optional[Path] = typer.Option(None, "--output-csv", "-c", help="Output per-frame CSV telemetry path"),
    output_json: Optional[Path] = typer.Option(None, "--output-json", "-j", help="Output JSON summary & frame telemetry path"),
    max_frames: Optional[int] = typer.Option(None, "--max-frames", help="Optional limit on number of frames to process"),
    detect_tearing: bool = typer.Option(True, "--tearing/--no-tearing", help="Enable screen tearing detection"),
    detect_resolution: bool = typer.Option(True, "--resolution/--no-resolution", help="Enable target & internal render resolution estimation"),
    platform_name: str = typer.Option("PS5", "--platform", "-p", help="Console/Platform badge (PS5, PS5 Pro, PS4, PS3, PS2, PS1, Xbox Series X, Xbox Series S, Xbox One, Xbox 360, Xbox, Switch, Switch 2, Wii U, Wii, GameCube, N64, Steam Deck, PC, Elgato)"),
    custom_logo: Optional[Path] = typer.Option(None, "--logo", help="Optional custom PNG logo path for the HUD badge"),
) -> None:
    """Analyze a recorded video file and generate HUD overlays and telemetry."""
    config = AnalyzerConfig(detect_tearing=detect_tearing, detect_resolution=detect_resolution)
    pipeline = AnalysisPipeline(config)
    reader = VideoFileReader(video_path, analysis_width=config.analysis_width, max_frames=max_frames)
    hud = HUDRenderer(
        show_resolution_badge=detect_resolution,
        platform_name=platform_name,
        custom_logo_path=str(custom_logo) if custom_logo else None,
    )

    burn_exporter: Optional[VideoExporter] = None
    alpha_exporter: Optional[VideoExporter] = None

    if output_video is not None:
        burn_exporter = VideoExporter(
            output_video,
            width=reader.width,
            height=reader.height,
            fps=reader.fps,
            alpha_only=False,
            source_audio_path=video_path,
        )
    if output_alpha is not None:
        alpha_exporter = VideoExporter(
            output_alpha,
            width=reader.width,
            height=reader.height,
            fps=reader.fps,
            alpha_only=True,
        )

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total} frames"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task(f"Analyzing {video_path.name}...", total=max(1, reader.total_frames))

            for packet in reader:
                metrics = pipeline.process_packet(packet)
                hud.update_history(metrics)

                if burn_exporter is not None:
                    composited = hud.composite_on_bgr(packet.raw_bgr, metrics, target_fps=reader.fps, update=False)
                    burn_exporter.write_frame(composited)

                if alpha_exporter is not None:
                    rgba = hud.render_rgba_overlay(
                        packet.width, packet.height, metrics, target_fps=reader.fps, update=False
                    )
                    alpha_exporter.write_frame(rgba)

                progress.advance(task_id, 1)
    finally:
        if burn_exporter is not None:
            burn_exporter.close()
        if alpha_exporter is not None:
            alpha_exporter.close()

    summary = pipeline.build_summary(source_path=str(video_path), container_fps=reader.fps)
    _print_summary_table(summary)

    if output_csv is not None:
        export_telemetry_csv(pipeline.metrics_history, output_csv)
        console.print(f"[green]✔ Saved CSV telemetry:[/green] {output_csv}")
    if output_json is not None:
        export_summary_json(summary, output_json, pipeline.metrics_history)
        console.print(f"[green]✔ Saved JSON summary:[/green] {output_json}")
    if output_video is not None:
        console.print(f"[green]✔ Saved burned-in overlay video:[/green] {output_video}")
    if output_alpha is not None:
        console.print(f"[green]✔ Saved transparent alpha overlay video:[/green] {output_alpha}")


@app.command("demo")
def run_demo(
    output_dir: Path = typer.Option(Path("demo_output"), "--output-dir", "-d", help="Directory for demo video and outputs"),
    platform_name: str = typer.Option("PS5", "--platform", "-p", help="Console/Platform logo badge"),
) -> None:
    """Generate a synthetic Elgato capture clip (60fps, 30fps, stutter, tearing & DRS) and analyze it."""
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_clip = output_dir / "synthetic_capture.mp4"
    console.print(f"[cyan]Generating synthetic capture clip at {raw_clip}...[/cyan]")
    generate_demo_capture_video(raw_clip, width=1280, height=720, fps=60.0, total_frames=180)

    analyze_video(
        video_path=raw_clip,
        output_video=output_dir / "synthetic_analyzed.mp4",
        output_alpha=output_dir / "synthetic_overlay_alpha.mov",
        output_csv=output_dir / "synthetic_telemetry.csv",
        output_json=output_dir / "synthetic_summary.json",
        max_frames=None,
        detect_tearing=True,
        detect_resolution=True,
        platform_name=platform_name,
        custom_logo=None,
    )


@app.command("devices")
def list_devices() -> None:
    """List connected UVC / AVFoundation video capture devices (e.g., Elgato 4K S)."""
    devices = list_capture_devices(max_devices=5)
    if not devices:
        console.print("[yellow]No UVC capture devices detected.[/yellow]")
        return
    table = Table(title="Detected Capture Devices")
    table.add_column("Index", style="cyan")
    table.add_column("Default Resolution", style="white")
    table.add_column("Default FPS", style="green")
    for d in devices:
        table.add_row(str(d["index"]), str(d["resolution"]), f"{d['fps']}")
    console.print(table)


@app.command("live")
def live_capture(
    device_index: int = typer.Option(0, "--device", "-d", help="UVC / Elgato 4K S capture device index"),
    width: int = typer.Option(1920, "--width", help="Capture width"),
    height: int = typer.Option(1080, "--height", help="Capture height"),
    fps: float = typer.Option(60.0, "--fps", help="Target capture framerate"),
    platform_name: str = typer.Option("PS5", "--platform", "-p", help="Console/Platform logo badge"),
    record_output: Optional[Path] = typer.Option(None, "--record", "-r", help="Optional path to record analyzed video"),
) -> None:
    """Run real-time live analysis on an Elgato 4K S or UVC capture device."""
    config = AnalyzerConfig()
    pipeline = AnalysisPipeline(config)
    hud = HUDRenderer(platform_name=platform_name)
    reader = LiveCaptureReader(device_index=device_index, width=width, height=height, fps=fps)
    exporter = (
        VideoExporter(record_output, width=reader.width, height=reader.height, fps=reader.fps)
        if record_output
        else None
    )

    console.print(
        f"[bold green]Live capture started on device {device_index} ({reader.width}x{reader.height} @ {reader.fps} FPS). Press 'q' in preview window to stop.[/bold green]"
    )
    try:
        for packet in reader:
            metrics = pipeline.process_packet(packet)
            composited = hud.composite_on_bgr(packet.raw_bgr, metrics, target_fps=reader.fps)
            if exporter is not None:
                exporter.write_frame(composited)
            cv2.imshow("Frametime & Resolution Analyzer (Live Elgato Feed)", composited)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        reader.stop()
        if exporter is not None:
            exporter.close()
        cv2.destroyAllWindows()


@app.command("studio")
def launch_studio(
    video_path: Optional[Path] = typer.Option(None, "--video", "-v", help="Optional initial video file to load"),
    host: str = typer.Option("127.0.0.1", "--host", help="Server host"),
    port: int = typer.Option(8000, "--port", "-p", help="Server port"),
    max_frames: Optional[int] = typer.Option(None, "--max-frames", help="Optional limit on frames to analyze"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Automatically open Studio in default web browser"),
) -> None:
    """Launch the Interactive Web/Desktop Analyzer Studio and OBS Live Overlay server."""
    import threading
    import webbrowser

    url = f"http://{host}:{port}"
    console.print(f"[bold green]Launching Frametime & Resolution Studio at {url}[/bold green]")
    console.print(f"[cyan]OBS Transparent Browser Source URL: {url}/obs-overlay[/cyan]")
    if video_path:
        console.print(
            f"[dim]Preloading initial 60 frames of {video_path.name} (remaining frames will stream in background)...[/dim]"
        )
    fastapi_app = create_app(initial_video=str(video_path) if video_path else None, max_frames=max_frames)
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(fastapi_app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    app()
