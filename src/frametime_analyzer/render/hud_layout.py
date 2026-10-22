"""Customizable HUD layout: labels, platform/brand logos, extra info text and element placement.

A ``HUDLayout`` is plain data (JSON round-trippable) shared by the CLI (``--layout``),
the desktop GUI (``fta gui``) and the ``HUDRenderer``.

Placement model
---------------
Every HUD element is positioned by an ``anchor`` (one of :data:`ANCHORS`) plus an
``offset_x`` / ``offset_y`` measured in 1080p reference pixels (scaled with the output
resolution). Offsets always point *inwards* from the anchored edge: for a ``*-right``
anchor ``offset_x`` is the distance from the right edge, for ``bottom-*`` anchors
``offset_y`` is the distance from the bottom edge. For ``center`` axes the offset shifts
the element right / down from the centered position.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import json
from pathlib import Path
from typing import Any, Optional, Union


ANCHORS: tuple[str, ...] = (
    "top-left",
    "top-center",
    "top-right",
    "middle-left",
    "center",
    "middle-right",
    "bottom-left",
    "bottom-center",
    "bottom-right",
)

ELEMENT_NAMES: tuple[str, ...] = (
    "platform_badge",
    "stats_card",
    "frametime_graph",
    "fps_graph",
    "extra_info",
    "brand_logo",
)

ELEMENT_TITLES: dict[str, str] = {
    "platform_badge": "Platform Badge",
    "stats_card": "FPS & Resolution Card",
    "frametime_graph": "Frametime Graph",
    "fps_graph": "Frame-Rate Graph",
    "extra_info": "Extra Info Panel",
    "brand_logo": "Brand / Channel Logo",
}


def anchor_axes(anchor: str) -> tuple[str, str]:
    """Split an anchor into its (vertical, horizontal) parts, e.g. ``"top-right"`` -> ``("top", "right")``."""
    if anchor == "center":
        return "middle", "center"
    vert, _, horiz = anchor.partition("-")
    return vert, horiz


@dataclass
class ElementPlacement:
    """Visibility and anchor-relative position of a single HUD element."""

    visible: bool = True
    anchor: str = "top-left"
    offset_x: int = 36
    offset_y: int = 36

    def __post_init__(self) -> None:
        if self.anchor not in ANCHORS:
            raise ValueError(f"Unknown anchor '{self.anchor}'. Expected one of: {', '.join(ANCHORS)}")

    def resolve(self, width: int, height: int, elem_w: int, elem_h: int, scale: float) -> tuple[int, int]:
        """Return the top-left pixel position of an ``elem_w x elem_h`` box on a ``width x height`` canvas."""
        vert, horiz = anchor_axes(self.anchor)
        ox = int(round(self.offset_x * scale))
        oy = int(round(self.offset_y * scale))

        if horiz == "left":
            x = ox
        elif horiz == "right":
            x = width - elem_w - ox
        else:
            x = (width - elem_w) // 2 + ox

        if vert == "top":
            y = oy
        elif vert == "bottom":
            y = height - elem_h - oy
        else:
            y = (height - elem_h) // 2 + oy
        return x, y

    def clamp_to_canvas(self, width: int, height: int, elem_w: int, elem_h: int, scale: float) -> None:
        """Limit offsets so an ``elem_w x elem_h`` element stays fully on a ``width x height`` canvas."""
        vert, horiz = anchor_axes(self.anchor)
        span_x = max(0.0, (width - elem_w) / scale)
        span_y = max(0.0, (height - elem_h) / scale)
        if horiz == "center":
            self.offset_x = int(max(-span_x / 2, min(span_x / 2, self.offset_x)))
        else:
            self.offset_x = int(max(0, min(span_x, self.offset_x)))
        if vert == "middle":
            self.offset_y = int(max(-span_y / 2, min(span_y / 2, self.offset_y)))
        else:
            self.offset_y = int(max(0, min(span_y, self.offset_y)))

    def nudge(self, dx_ref: float, dy_ref: float) -> None:
        """Move the element by a screen-space delta (in reference pixels), respecting the anchor direction."""
        vert, horiz = anchor_axes(self.anchor)
        self.offset_x = int(round(self.offset_x + (-dx_ref if horiz == "right" else dx_ref)))
        self.offset_y = int(round(self.offset_y + (-dy_ref if vert == "bottom" else dy_ref)))


@dataclass
class HUDLabels:
    """User-editable text labels rendered on the HUD."""

    fps_unit: str = "FPS"
    one_percent_low: str = "1% LOW"
    frametime_short: str = "FT"
    status_tearing: str = "TEARING DETECTED"
    status_duplicate: str = "FRAME REPEAT / DROP"
    status_clean: str = "UNIQUE FRAME - V-SYNC CLEAN"
    target_output: str = "TARGET OUTPUT"
    est_render: str = "EST. RENDER"
    frametime_graph_title: str = "FRAMETIME (MS)"
    fps_graph_title: str = "FRAME-RATE (FPS)"


LABEL_TITLES: dict[str, str] = {
    "fps_unit": "FPS unit",
    "one_percent_low": "1% low",
    "frametime_short": "Frametime (short)",
    "status_tearing": "Status: tearing",
    "status_duplicate": "Status: repeated frame",
    "status_clean": "Status: clean frame",
    "target_output": "Target output resolution",
    "est_render": "Estimated render resolution",
    "frametime_graph_title": "Frametime graph title",
    "fps_graph_title": "Frame-rate graph title",
}


def _default_placements() -> dict[str, ElementPlacement]:
    return {
        "platform_badge": ElementPlacement(True, "top-right", 36, 36),
        "stats_card": ElementPlacement(True, "top-right", 36, 78),
        "frametime_graph": ElementPlacement(True, "bottom-left", 36, 209),
        "fps_graph": ElementPlacement(True, "bottom-left", 36, 36),
        "extra_info": ElementPlacement(True, "top-left", 36, 36),
        "brand_logo": ElementPlacement(True, "bottom-right", 36, 36),
    }


@dataclass
class HUDLayout:
    """Complete, serializable description of the HUD appearance."""

    platform_name: str = "PS5"
    platform_label: str = ""  # Overrides the text shown on the platform badge when non-empty
    custom_logo_path: Optional[str] = None  # PNG replacing the vector platform icon
    brand_logo_path: Optional[str] = None  # Free-standing PNG logo (channel / watermark)
    brand_logo_height: int = 90  # Reference (1080p) pixel height of the brand logo
    brand_logo_opacity: float = 1.0
    extra_info_title: str = ""
    extra_info_lines: list[str] = field(default_factory=list)
    hud_scale: float = 1.0  # Multiplier on top of the automatic resolution scale
    panel_opacity: float = 0.73  # Opacity of the dark panel backgrounds (0..1)
    show_resolution: bool = True
    show_tear_lines: bool = True
    labels: HUDLabels = field(default_factory=HUDLabels)
    elements: dict[str, ElementPlacement] = field(default_factory=_default_placements)

    def __post_init__(self) -> None:
        defaults = _default_placements()
        for name in ELEMENT_NAMES:
            self.elements.setdefault(name, defaults[name])

    def element(self, name: str) -> ElementPlacement:
        return self.elements[name]

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HUDLayout:
        """Build a layout from a (possibly partial) dict; unknown keys are ignored."""
        known = {f.name for f in fields(cls)} - {"labels", "elements"}
        kwargs: dict[str, Any] = {k: v for k, v in data.items() if k in known}
        if "extra_info_lines" in kwargs:
            kwargs["extra_info_lines"] = [str(line) for line in kwargs["extra_info_lines"]]

        label_keys = {f.name for f in fields(HUDLabels)}
        labels_data = data.get("labels") or {}
        kwargs["labels"] = HUDLabels(**{k: str(v) for k, v in labels_data.items() if k in label_keys})

        placements = _default_placements()
        placement_keys = {f.name for f in fields(ElementPlacement)}
        for name, elem in (data.get("elements") or {}).items():
            if name in placements and isinstance(elem, dict):
                merged = {**asdict(placements[name]), **{k: v for k, v in elem.items() if k in placement_keys}}
                placements[name] = ElementPlacement(**merged)
        kwargs["elements"] = placements
        return cls(**kwargs)

    def copy(self) -> HUDLayout:
        return HUDLayout.from_dict(self.to_dict())

    def save(self, path: Union[str, Path]) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return out

    @classmethod
    def load(cls, path: Union[str, Path]) -> HUDLayout:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
