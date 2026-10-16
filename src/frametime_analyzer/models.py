"""Core data models for Frametime, Tearing, and Resolution Analysis."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional
import numpy as np


@dataclass
class FramePacket:
    """Represents a decoded video frame with presentation timing metadata."""

    frame_index: int
    timestamp_ms: float
    duration_ms: float
    container_fps: float
    raw_bgr: np.ndarray
    luma_small: Optional[np.ndarray] = None

    @property
    def height(self) -> int:
        return int(self.raw_bgr.shape[0])

    @property
    def width(self) -> int:
        return int(self.raw_bgr.shape[1])


@dataclass
class StairStepSample:
    """Result of an interactive or automatic stair-step edge pixel count."""

    x1: int
    y1: int
    x2: int
    y2: int
    dominant_axis: str  # "horizontal" or "vertical"
    span_pixels: int
    counted_steps: int
    step_positions: list[int]
    edge_profile: list[float]
    gradient_profile: list[float]
    container_width: int
    container_height: int
    target_width: int
    target_height: int
    estimated_render_width: int
    estimated_render_height: int
    scale_ratio: float
    confidence: float
    standard_Tier_match: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FrameMetrics:
    """Per-frame performance, tearing, and resolution telemetry."""

    frame_index: int
    timestamp_ms: float
    frame_duration_ms: float
    is_duplicate: bool
    is_torn: bool
    tear_line_y: list[int] = field(default_factory=list)
    frametime_ms: float = 16.67
    rolling_fps: float = 60.0
    instant_fps: float = 60.0
    fps_1_percent_low: float = 60.0
    fps_0_1_percent_low: float = 60.0
    mean_luma_diff: float = 0.0
    p95_tile_diff: float = 0.0
    adaptive_threshold: float = 0.0
    container_resolution: tuple[int, int] = (1920, 1080)
    target_resolution: tuple[int, int] = (1920, 1080)
    estimated_render_resolution: tuple[int, int] = (1920, 1080)
    render_scale_percent: float = 100.0
    resolution_tier_label: str = "1080p"
    resolution_confidence: float = 1.0
    esf_fwhm_px: float = 1.0
    spectral_cutoff_ratio: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["container_width"] = self.container_resolution[0]
        data["container_height"] = self.container_resolution[1]
        data["target_width"] = self.target_resolution[0]
        data["target_height"] = self.target_resolution[1]
        data["render_width"] = self.estimated_render_resolution[0]
        data["render_height"] = self.estimated_render_resolution[1]
        return data


@dataclass
class AnalysisSummary:
    """Aggregate statistics across an entire analyzed video clip."""

    source_path: str
    total_frames: int
    unique_frames: int
    duplicate_frames: int
    torn_frames: int
    torn_frames_percent: float
    duration_seconds: float
    container_fps: float
    avg_fps: float
    min_fps: float
    max_fps: float
    fps_1_percent_low: float
    fps_0_1_percent_low: float
    avg_frametime_ms: float
    max_frametime_ms: float
    p99_frametime_ms: float
    frametime_std_ms: float
    container_resolution: tuple[int, int]
    target_resolution: tuple[int, int]
    min_render_resolution: tuple[int, int]
    max_render_resolution: tuple[int, int]
    median_render_resolution: tuple[int, int]
    is_dynamic_resolution: bool
    avg_resolution_confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnalyzerConfig:
    """Configuration parameters for the analysis pipeline."""

    # Duplicate detection parameters
    analysis_width: int = 640
    grid_cols: int = 16
    grid_rows: int = 9
    noise_floor_luma: float = 0.32
    ema_alpha: float = 0.20
    relative_drop_ratio: float = 0.25
    # Optional list of normalized (x1, y1, x2, y2) in [0..1] to mask out static/animated HUD elements
    hud_exclusion_boxes: list[tuple[float, float, float, float]] = field(default_factory=list)
    auto_mask_corner_hud: bool = False

    # Tearing detection parameters
    detect_tearing: bool = True
    tear_gradient_zscore: float = 4.5
    tear_min_region_diff: float = 1.5

    # Resolution detection parameters
    detect_resolution: bool = True
    resolution_sample_interval: int = 3  # Run full spectral/ESF resolution estimation every N frames
    drs_smoothing_window: int = 12
    # Optional normalized (x1, y1, x2, y2) in [0..1] for native-resolution HUD reference
    hud_reference_box: Optional[tuple[float, float, float, float]] = None
