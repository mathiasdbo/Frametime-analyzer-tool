"""Manual target / internal render resolution overrides.

The automatic DRS estimator can misidentify the render resolution (heavy post-processing, temporal
upscalers, film grain, sharpening...). A :class:`ResolutionOverride` lets the user state what they
know and is applied to every frame's metrics, so the HUD, CSV/JSON telemetry and summary agree.

Render modes:
    ``auto``   – keep the per-frame estimate (rescaled if the target resolution is overridden).
    ``range``  – keep the per-frame estimate but clamp its height to a known DRS window.
    ``fixed``  – ignore the estimate and report one fixed render resolution (no DRS).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Optional

from frametime_analyzer.models import FrameMetrics

RENDER_MODES: tuple[str, ...] = ("auto", "range", "fixed")


def parse_resolution(text: str) -> tuple[int, int]:
    """Parse ``"2560x1440"`` (also ``2560*1440`` / ``2560 1440``) into ``(width, height)``."""
    match = re.fullmatch(r"\s*(\d{2,5})\s*[xX*× ]\s*(\d{2,5})\s*", text)
    if not match:
        raise ValueError(f"Invalid resolution '{text}', expected WIDTHxHEIGHT such as 2560x1440")
    return int(match.group(1)), int(match.group(2))


def parse_height_range(text: str) -> tuple[int, int]:
    """Parse ``"1440-2160"`` (``p`` suffixes allowed) into ``(min_height, max_height)``."""
    match = re.fullmatch(r"\s*(\d{2,5})p?\s*[-:–]\s*(\d{2,5})p?\s*", text)
    if not match:
        raise ValueError(f"Invalid height range '{text}', expected MIN-MAX such as 1440-2160")
    lo, hi = int(match.group(1)), int(match.group(2))
    return min(lo, hi), max(lo, hi)


def _even(value: float) -> int:
    return max(2, int(round(value / 2.0)) * 2)


@dataclass
class ResolutionOverride:
    """User-supplied resolution information that takes precedence over the automatic analysis."""

    target: Optional[tuple[int, int]] = None  # Manual target output resolution; None = auto-detect
    render_mode: str = "auto"
    render: Optional[tuple[int, int]] = None  # Used by render_mode == "fixed"
    render_min_height: Optional[int] = None  # Used by render_mode == "range"
    render_max_height: Optional[int] = None

    def __post_init__(self) -> None:
        if self.render_mode not in RENDER_MODES:
            raise ValueError(f"Unknown render mode '{self.render_mode}'. Expected one of: {', '.join(RENDER_MODES)}")
        if self.render_mode == "fixed" and self.render is None:
            raise ValueError("render_mode 'fixed' requires a render resolution")
        if self.render_mode == "range" and self.render_min_height is None and self.render_max_height is None:
            raise ValueError("render_mode 'range' requires a minimum and/or maximum render height")
        for res in (self.target, self.render):
            if res is not None and (res[0] <= 0 or res[1] <= 0):
                raise ValueError(f"Invalid resolution {res[0]}x{res[1]}")

    @property
    def is_active(self) -> bool:
        return self.target is not None or self.render_mode != "auto"

    def apply(self, metrics: FrameMetrics) -> FrameMetrics:
        """Return ``metrics`` with the override applied (the input object is left untouched)."""
        if not self.is_active:
            return metrics

        auto_tw, auto_th = metrics.target_resolution
        tw, th = self.target if self.target is not None else (auto_tw, auto_th)
        confidence = metrics.resolution_confidence

        if self.render_mode == "fixed":
            assert self.render is not None
            rw, rh = self.render
            confidence = 1.0
        else:
            # Keep the estimated *scale* and re-express it against the (possibly manual) target
            scale = metrics.render_scale_percent / 100.0
            rh = _even(th * scale)
            if self.render_mode == "range":
                lo = self.render_min_height or 1
                hi = self.render_max_height or th
                rh = min(max(rh, lo), hi)
            rw = _even(rh * tw / float(max(1, th)))

        return replace(
            metrics,
            target_resolution=(tw, th),
            estimated_render_resolution=(rw, rh),
            render_scale_percent=round(rh / float(max(1, th)) * 100.0, 1),
            resolution_tier_label=f"{rh}p",
            resolution_confidence=confidence,
        )
