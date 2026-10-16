"""Core detectors and pipeline exports."""
from __future__ import annotations

from .frametime_detector import FrametimeDetector
from .pipeline import AnalysisPipeline
from .resolution_analyzer import ResolutionAnalyzer, match_standard_resolution_tier
from .tearing_detector import TearingDetector

__all__ = [
    "FrametimeDetector",
    "TearingDetector",
    "ResolutionAnalyzer",
    "AnalysisPipeline",
    "match_standard_resolution_tier",
]
