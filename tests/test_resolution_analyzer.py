"""Unit tests for Target and Internal Render Resolution Analyzer."""
from __future__ import annotations

import cv2
import numpy as np

from frametime_analyzer.core.resolution_analyzer import ResolutionAnalyzer
from frametime_analyzer.demo_generator import render_synthetic_scene
from frametime_analyzer.models import AnalyzerConfig, FramePacket


def test_active_target_bounds_with_letterbox() -> None:
    analyzer = ResolutionAnalyzer()
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    # Active 21:9 viewport inside [0..1920, 130..950]
    frame[130:950, :] = render_synthetic_scene(1920, 820, step_index=1)
    x0, y0, x1, y1 = analyzer.detect_active_target_bounds(frame)
    assert x0 == 0
    assert x1 == 1920
    assert abs(y0 - 130) <= 2
    assert abs(y1 - 950) <= 2


def test_automated_render_resolution_estimation_across_scales() -> None:
    w, h = 1920, 1080

    # 1. Native 1080p frame
    analyzer_native = ResolutionAnalyzer(AnalyzerConfig(drs_smoothing_window=1))
    bgr_1080 = render_synthetic_scene(w, h, step_index=5, internal_render_scale=1.0)
    pkt_1080 = FramePacket(0, 0.0, 16.67, 60.0, bgr_1080, cv2.cvtColor(bgr_1080, cv2.COLOR_BGR2GRAY))
    res_1080 = analyzer_native.process_frame(pkt_1080, force=True)

    # 2. Upscaled 720p (66.7% scale) inside 1080p container
    analyzer_720 = ResolutionAnalyzer(AnalyzerConfig(drs_smoothing_window=1))
    bgr_720 = render_synthetic_scene(w, h, step_index=5, internal_render_scale=720 / 1080.0)
    pkt_720 = FramePacket(0, 0.0, 16.67, 60.0, bgr_720, cv2.cvtColor(bgr_720, cv2.COLOR_BGR2GRAY))
    res_720 = analyzer_720.process_frame(pkt_720, force=True)

    # 3. Upscaled 540p (50.0% scale) inside 1080p container
    analyzer_540 = ResolutionAnalyzer(AnalyzerConfig(drs_smoothing_window=1))
    bgr_540 = render_synthetic_scene(w, h, step_index=5, internal_render_scale=0.5)
    pkt_540 = FramePacket(0, 0.0, 16.67, 60.0, bgr_540, cv2.cvtColor(bgr_540, cv2.COLOR_BGR2GRAY))
    res_540 = analyzer_540.process_frame(pkt_540, force=True)

    h_1080 = res_1080["estimated_render_resolution"][1]
    h_720 = res_720["estimated_render_resolution"][1]
    h_540 = res_540["estimated_render_resolution"][1]

    assert h_1080 > h_720 > h_540
    assert abs(h_1080 - 1080) <= 108
    assert abs(h_720 - 720) <= 115
    assert abs(h_540 - 540) <= 108


def test_interactive_stair_step_pixel_counter() -> None:
    analyzer = ResolutionAnalyzer()
    w, h = 1280, 720
    bgr = render_synthetic_scene(w, h, step_index=2, internal_render_scale=0.667)

    sample = analyzer.count_edge_stair_steps(bgr, x1=320, y1=250, x2=420, y2=290)
    assert sample.span_pixels == 100
    assert 20 <= sample.counted_steps <= 100
    assert sample.target_width == 1280
    assert sample.target_height == 720
    assert 180 <= sample.estimated_render_height <= 720
