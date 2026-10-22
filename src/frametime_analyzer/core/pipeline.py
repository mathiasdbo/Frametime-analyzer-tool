"""Core analysis pipeline orchestrating frametime, tearing, and resolution detectors."""
from __future__ import annotations

from typing import Callable, Iterable, Optional
import numpy as np

from frametime_analyzer.core.frametime_detector import FrametimeDetector
from frametime_analyzer.core.resolution_analyzer import ResolutionAnalyzer
from frametime_analyzer.core.resolution_override import ResolutionOverride
from frametime_analyzer.core.tearing_detector import TearingDetector
from frametime_analyzer.models import (
    AnalysisSummary,
    AnalyzerConfig,
    FrameMetrics,
    FramePacket,
)


class AnalysisPipeline:
    """Orchestrates frame-by-frame analysis and produces FrameMetrics and AnalysisSummary."""

    def __init__(
        self,
        config: Optional[AnalyzerConfig] = None,
        resolution_override: Optional[ResolutionOverride] = None,
    ) -> None:
        self.config = config or AnalyzerConfig()
        self.resolution_override = resolution_override
        self.frametime_detector = FrametimeDetector(self.config)
        self.tearing_detector = TearingDetector(self.config)
        self.resolution_analyzer = ResolutionAnalyzer(self.config)
        self.metrics_history: list[FrameMetrics] = []

    def reset(self) -> None:
        self.frametime_detector.reset()
        self.tearing_detector.reset()
        self.resolution_analyzer.reset()
        self.metrics_history.clear()

    def process_packet(self, packet: FramePacket) -> FrameMetrics:
        """Analyze a single FramePacket and return its FrameMetrics."""
        ft_res = self.frametime_detector.process_frame(packet)
        is_torn, tear_lines = self.tearing_detector.process_frame(packet)
        res_info = self.resolution_analyzer.process_frame(
            packet, force=(packet.frame_index == 0 or not bool(ft_res["is_duplicate"]))
        )

        metrics = FrameMetrics(
            frame_index=packet.frame_index,
            timestamp_ms=round(packet.timestamp_ms, 3),
            frame_duration_ms=round(packet.duration_ms, 3),
            is_duplicate=bool(ft_res["is_duplicate"]),
            is_torn=is_torn,
            tear_line_y=tear_lines,
            frametime_ms=round(float(ft_res["frametime_ms"]), 2),
            rolling_fps=round(float(ft_res["rolling_fps"]), 1),
            instant_fps=round(float(ft_res["instant_fps"]), 1),
            fps_1_percent_low=round(float(ft_res["fps_1_percent_low"]), 1),
            fps_0_1_percent_low=round(float(ft_res["fps_0_1_percent_low"]), 1),
            mean_luma_diff=round(float(ft_res["mean_luma_diff"]), 3),
            p95_tile_diff=round(float(ft_res["p95_tile_diff"]), 3),
            adaptive_threshold=round(float(ft_res["adaptive_threshold"]), 3),
            container_resolution=res_info["container_resolution"],
            target_resolution=res_info["target_resolution"],
            estimated_render_resolution=res_info["estimated_render_resolution"],
            render_scale_percent=float(res_info["render_scale_percent"]),
            resolution_tier_label=str(res_info["resolution_tier_label"]),
            resolution_confidence=float(res_info["resolution_confidence"]),
            esf_fwhm_px=float(res_info["esf_fwhm_px"]),
            spectral_cutoff_ratio=float(res_info["spectral_cutoff_ratio"]),
        )
        if self.resolution_override is not None:
            metrics = self.resolution_override.apply(metrics)
        self.metrics_history.append(metrics)
        return metrics

    def run_stream(
        self,
        packets: Iterable[FramePacket],
        on_frame: Optional[Callable[[FramePacket, FrameMetrics], None]] = None,
    ) -> list[FrameMetrics]:
        """Process an iterable stream of FramePackets with an optional callback."""
        self.reset()
        for packet in packets:
            metrics = self.process_packet(packet)
            if on_frame is not None:
                on_frame(packet, metrics)
        return self.metrics_history

    def build_summary(self, source_path: str = "stream", container_fps: float = 60.0) -> AnalysisSummary:
        """Compute aggregate summary statistics from all processed frames."""
        if not self.metrics_history:
            return AnalysisSummary(
                source_path=source_path,
                total_frames=0,
                unique_frames=0,
                duplicate_frames=0,
                torn_frames=0,
                torn_frames_percent=0.0,
                duration_seconds=0.0,
                container_fps=container_fps,
                avg_fps=0.0,
                min_fps=0.0,
                max_fps=0.0,
                fps_1_percent_low=0.0,
                fps_0_1_percent_low=0.0,
                avg_frametime_ms=0.0,
                max_frametime_ms=0.0,
                p99_frametime_ms=0.0,
                frametime_std_ms=0.0,
                container_resolution=(0, 0),
                target_resolution=(0, 0),
                min_render_resolution=(0, 0),
                max_render_resolution=(0, 0),
                median_render_resolution=(0, 0),
                is_dynamic_resolution=False,
                avg_resolution_confidence=0.0,
            )

        total = len(self.metrics_history)
        dup_count = sum(1 for m in self.metrics_history if m.is_duplicate)
        unique_count = total - dup_count
        torn_count = sum(1 for m in self.metrics_history if m.is_torn)

        last_ts_ms = self.metrics_history[-1].timestamp_ms + self.metrics_history[-1].frame_duration_ms
        duration_s = max(0.001, last_ts_ms / 1000.0)

        fps_vals = np.array([m.rolling_fps for m in self.metrics_history], dtype=np.float32)
        ft_vals = np.array([m.frametime_ms for m in self.metrics_history], dtype=np.float32)

        render_heights = [m.estimated_render_resolution[1] for m in self.metrics_history]
        render_widths = [m.estimated_render_resolution[0] for m in self.metrics_history]
        min_idx = int(np.argmin(render_heights))
        max_idx = int(np.argmax(render_heights))
        med_h = int(round(float(np.median(render_heights))))
        target_res = self.metrics_history[-1].target_resolution
        aspect = target_res[0] / float(max(1, target_res[1]))
        med_w = int(round((med_h * aspect) / 2.0) * 2)

        is_drs = (max(render_heights) - min(render_heights)) >= 36
        avg_conf = float(np.mean([m.resolution_confidence for m in self.metrics_history]))

        return AnalysisSummary(
            source_path=source_path,
            total_frames=total,
            unique_frames=unique_count,
            duplicate_frames=dup_count,
            torn_frames=torn_count,
            torn_frames_percent=round((torn_count / float(total)) * 100.0, 2),
            duration_seconds=round(duration_s, 3),
            container_fps=round(container_fps, 2),
            avg_fps=round(float(unique_count / duration_s), 2),
            min_fps=round(float(np.min(fps_vals)), 1),
            max_fps=round(float(np.max(fps_vals)), 1),
            fps_1_percent_low=self.metrics_history[-1].fps_1_percent_low,
            fps_0_1_percent_low=self.metrics_history[-1].fps_0_1_percent_low,
            avg_frametime_ms=round(float(np.mean(ft_vals)), 2),
            max_frametime_ms=round(float(np.max(ft_vals)), 2),
            p99_frametime_ms=round(float(np.percentile(ft_vals, 99)), 2),
            frametime_std_ms=round(float(np.std(ft_vals)), 2),
            container_resolution=self.metrics_history[-1].container_resolution,
            target_resolution=target_res,
            min_render_resolution=(render_widths[min_idx], render_heights[min_idx]),
            max_render_resolution=(render_widths[max_idx], render_heights[max_idx]),
            median_render_resolution=(med_w, med_h),
            is_dynamic_resolution=is_drs,
            avg_resolution_confidence=round(avg_conf, 2),
        )
