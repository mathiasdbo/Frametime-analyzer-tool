"""Tests for manual target / render resolution overrides."""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from typer.testing import CliRunner

from frametime_analyzer.cli.cli import app as cli_app
from frametime_analyzer.core.resolution_override import (
    ResolutionOverride,
    parse_height_range,
    parse_resolution,
)
from frametime_analyzer.demo_generator import generate_demo_capture_video
from frametime_analyzer.models import FrameMetrics
from frametime_analyzer.processing import ProcessingJob, process_video


def _metrics(scale_pct: float = 75.0) -> FrameMetrics:
    return FrameMetrics(
        frame_index=0,
        timestamp_ms=0.0,
        frame_duration_ms=16.67,
        is_duplicate=False,
        is_torn=False,
        target_resolution=(1920, 1080),
        estimated_render_resolution=(1440, 810),
        render_scale_percent=scale_pct,
        resolution_tier_label="810p",
        resolution_confidence=0.4,
    )


def test_parsers() -> None:
    assert parse_resolution("2560x1440") == (2560, 1440)
    assert parse_resolution(" 3840 X 2160 ") == (3840, 2160)
    assert parse_height_range("2160p-1440p") == (1440, 2160)
    with pytest.raises(ValueError):
        parse_resolution("1440p")
    with pytest.raises(ValueError):
        parse_height_range("1440")


def test_fixed_render_resolution() -> None:
    out = ResolutionOverride(target=(3840, 2160), render_mode="fixed", render=(2560, 1440)).apply(_metrics())
    assert out.target_resolution == (3840, 2160)
    assert out.estimated_render_resolution == (2560, 1440)
    assert out.render_scale_percent == pytest.approx(66.7)
    assert out.resolution_tier_label == "1440p"
    assert out.resolution_confidence == 1.0


def test_manual_target_rescales_auto_estimate() -> None:
    out = ResolutionOverride(target=(3840, 2160)).apply(_metrics(scale_pct=50.0))
    assert out.estimated_render_resolution == (1920, 1080)
    assert out.resolution_confidence == 0.4  # Still an estimate


def test_range_clamps_estimate() -> None:
    override = ResolutionOverride(render_mode="range", render_min_height=900, render_max_height=1080)
    assert override.apply(_metrics(scale_pct=50.0)).estimated_render_resolution == (1600, 900)
    assert override.apply(_metrics(scale_pct=90.0)).estimated_render_resolution[1] == 972
    assert override.apply(_metrics(scale_pct=120.0)).estimated_render_resolution == (1920, 1080)


def test_inactive_and_invalid_overrides() -> None:
    m = _metrics()
    assert ResolutionOverride().apply(m) is m
    with pytest.raises(ValueError):
        ResolutionOverride(render_mode="fixed")
    with pytest.raises(ValueError):
        ResolutionOverride(render_mode="range")
    with pytest.raises(ValueError):
        ResolutionOverride(render_mode="bogus")


def test_override_reaches_telemetry_and_summary(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    generate_demo_capture_video(clip, width=640, height=360, fps=60.0, total_frames=30)
    result = process_video(
        ProcessingJob(
            video_path=clip,
            resolution_override=ResolutionOverride(target=(1920, 1080), render_mode="fixed", render=(1600, 900)),
        )
    )
    assert {m.estimated_render_resolution for m in result.metrics} == {(1600, 900)}
    assert result.summary.target_resolution == (1920, 1080)
    assert result.summary.median_render_resolution == (1600, 900)
    assert result.summary.is_dynamic_resolution is False

    out_json = tmp_path / "s.json"
    cli = CliRunner().invoke(
        cli_app,
        ["analyze", str(clip), "--target-res", "1280x720", "--render-range", "540-720", "-j", str(out_json), "--max-frames", "15"],
    )
    assert cli.exit_code == 0, cli.output
    frames = json.loads(out_json.read_text())["frames"]
    assert all(f["target_width"] == 1280 and 540 <= f["render_height"] <= 720 for f in frames)

    bad = CliRunner().invoke(cli_app, ["analyze", str(clip), "--render-res", "1600x900", "--render-range", "540-720"])
    assert bad.exit_code != 0
