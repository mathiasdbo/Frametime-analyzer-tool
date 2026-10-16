"""Unit tests for TearingDetector."""
from __future__ import annotations

import cv2

from frametime_analyzer.core.tearing_detector import TearingDetector
from frametime_analyzer.demo_generator import render_synthetic_scene
from frametime_analyzer.models import AnalyzerConfig, FramePacket


def test_screen_tearing_detection_and_scanline_localization() -> None:
    detector = TearingDetector(AnalyzerConfig(detect_tearing=True))
    w, h = 640, 360

    frame_a = render_synthetic_scene(w, h, step_index=10)
    frame_b = render_synthetic_scene(w, h, step_index=14)

    pkt_0 = FramePacket(
        frame_index=0,
        timestamp_ms=0.0,
        duration_ms=16.67,
        container_fps=60.0,
        raw_bgr=frame_a,
        luma_small=cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY),
    )
    is_torn_0, lines_0 = detector.process_frame(pkt_0)
    assert not is_torn_0
    assert lines_0 == []

    # Synthesize a torn frame at Y = 180 (top half is frame_a, bottom half is frame_b)
    torn_bgr = frame_a.copy()
    tear_y = 180
    torn_bgr[tear_y:, :] = frame_b[tear_y:, :]

    pkt_1 = FramePacket(
        frame_index=1,
        timestamp_ms=16.67,
        duration_ms=16.67,
        container_fps=60.0,
        raw_bgr=torn_bgr,
        luma_small=cv2.cvtColor(torn_bgr, cv2.COLOR_BGR2GRAY),
    )
    is_torn_1, lines_1 = detector.process_frame(pkt_1)
    assert is_torn_1 is True
    assert len(lines_1) >= 1
    assert any(abs(y - tear_y) <= 4 for y in lines_1)
