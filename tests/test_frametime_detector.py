"""Unit tests for FrametimeDetector (60fps, 30fps, stutter, and HUD masking)."""
from __future__ import annotations

import cv2
import numpy as np

from frametime_analyzer.core.frametime_detector import FrametimeDetector
from frametime_analyzer.demo_generator import render_synthetic_scene
from frametime_analyzer.models import AnalyzerConfig, FramePacket


def _make_packet(idx: int, bgr: np.ndarray, fps: float = 60.0) -> FramePacket:
    dt_ms = 1000.0 / fps
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return FramePacket(
        frame_index=idx,
        timestamp_ms=idx * dt_ms,
        duration_ms=dt_ms,
        container_fps=fps,
        raw_bgr=bgr,
        luma_small=gray,
    )


def test_locked_60fps_and_30fps_detection() -> None:
    detector = FrametimeDetector(AnalyzerConfig(analysis_width=320))
    step = 0
    prev_bgr = render_synthetic_scene(320, 180, step)

    # First 60 frames: unique every frame (60 FPS, ~16.67ms)
    fps_60_results = []
    for idx in range(60):
        step += 1
        bgr = render_synthetic_scene(320, 180, step)
        res = detector.process_frame(_make_packet(idx, bgr, fps=60.0))
        fps_60_results.append(res)
        prev_bgr = bgr

    assert all(not r["is_duplicate"] for r in fps_60_results)
    assert abs(float(fps_60_results[-1]["rolling_fps"]) - 60.0) <= 1.0
    assert abs(float(fps_60_results[-1]["frametime_ms"]) - 16.67) <= 0.5

    # Next 60 frames: every odd frame is a duplicate (30 FPS, ~33.33ms)
    fps_30_results = []
    for idx in range(60, 120):
        if idx % 2 == 1:
            bgr = prev_bgr.copy()
        else:
            step += 1
            bgr = render_synthetic_scene(320, 180, step)
            prev_bgr = bgr
        res = detector.process_frame(_make_packet(idx, bgr, fps=60.0))
        fps_30_results.append(res)

    # Verify odd frames are detected as duplicates and even frames as unique
    for offset, r in enumerate(fps_30_results[2:], start=2):
        expected_dup = ((60 + offset) % 2 == 1)
        assert bool(r["is_duplicate"]) is expected_dup

    assert abs(float(fps_30_results[-1]["rolling_fps"]) - 30.0) <= 1.0
    assert abs(float(fps_30_results[-1]["frametime_ms"]) - 33.33) <= 1.0


def test_hud_exclusion_mask_prevents_false_unique_frames() -> None:
    # Configure HUD exclusion box over top-left [0.0..0.25, 0.0..0.25]
    cfg = AnalyzerConfig(hud_exclusion_boxes=[(0.0, 0.0, 0.25, 0.25)])
    detector = FrametimeDetector(cfg)

    base_scene = render_synthetic_scene(320, 180, 1)
    detector.process_frame(_make_packet(0, base_scene))
    moving_scene = render_synthetic_scene(320, 180, 2)
    detector.process_frame(_make_packet(1, moving_scene))

    # Frame 2: 3D scene is completely frozen (duplicate of frame 1), but top-left HUD flickers brightly
    hud_animated = moving_scene.copy()
    hud_animated[5:35, 5:65] = 255 - hud_animated[5:35, 5:65]
    res = detector.process_frame(_make_packet(2, hud_animated))

    assert res["is_duplicate"] is True
