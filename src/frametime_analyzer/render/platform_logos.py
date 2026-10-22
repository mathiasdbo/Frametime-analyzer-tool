"""Vector and image-based Console & Platform Logo renderer for the HUD overlay."""
from __future__ import annotations

from typing import Optional
import cv2
import numpy as np


PLATFORM_PRESETS: dict[str, dict[str, object]] = {
    "ps5": {
        "label": "PS5",
        "family": "playstation",
        "accent_bgra": (235, 110, 30, 255),  # PlayStation Blue in BGRA
        "badge_bg": (95, 35, 10, 220),
    },
    "ps5 pro": {
        "label": "PS5 PRO",
        "family": "playstation",
        "accent_bgra": (245, 130, 45, 255),
        "badge_bg": (105, 40, 12, 220),
    },
    "ps4": {
        "label": "PS4",
        "family": "playstation",
        "accent_bgra": (220, 100, 25, 255),
        "badge_bg": (85, 30, 10, 220),
    },
    "ps3": {
        "label": "PS3",
        "family": "playstation",
        "accent_bgra": (180, 60, 20, 255),
        "badge_bg": (55, 22, 12, 220),
    },
    "ps2": {
        "label": "PS2",
        "family": "playstation",
        "accent_bgra": (230, 140, 20, 255),
        "badge_bg": (70, 30, 10, 220),
    },
    "ps1": {
        "label": "PS1",
        "family": "playstation",
        "accent_bgra": (175, 175, 180, 255),
        "badge_bg": (55, 55, 62, 220),
    },
    "xbox series x": {
        "label": "XBOX SERIES X",
        "family": "xbox",
        "accent_bgra": (45, 195, 25, 255),  # Xbox Green in BGRA
        "badge_bg": (18, 70, 12, 220),
    },
    "xbox series s": {
        "label": "XBOX SERIES S",
        "family": "xbox",
        "accent_bgra": (75, 215, 55, 255),
        "badge_bg": (22, 75, 15, 220),
    },
    "xbox one": {
        "label": "XBOX ONE",
        "family": "xbox",
        "accent_bgra": (40, 175, 20, 255),
        "badge_bg": (16, 62, 10, 220),
    },
    "xbox 360": {
        "label": "XBOX 360",
        "family": "xbox",
        "accent_bgra": (35, 225, 125, 255),  # Xbox 360 Lime Green in BGRA
        "badge_bg": (15, 78, 35, 220),
    },
    "xbox": {
        "label": "XBOX",
        "family": "xbox",
        "accent_bgra": (25, 205, 85, 255),  # Original Xbox Jewel Green in BGRA
        "badge_bg": (12, 65, 22, 220),
    },
    "switch": {
        "label": "SWITCH",
        "family": "switch",
        "accent_bgra": (45, 35, 235, 255),  # Nintendo Red in BGRA
        "badge_bg": (20, 15, 115, 220),
    },
    "switch 2": {
        "label": "SWITCH 2",
        "family": "switch",
        "accent_bgra": (55, 45, 245, 255),
        "badge_bg": (25, 18, 125, 220),
    },
    "wii u": {
        "label": "WII U",
        "family": "wii_u",
        "accent_bgra": (235, 165, 0, 255),  # Wii U Cerulean Cyan in BGRA
        "badge_bg": (75, 48, 8, 220),
    },
    "wii": {
        "label": "WII",
        "family": "wii",
        "accent_bgra": (230, 185, 55, 255),  # Wii Sky Cyan/Silver in BGRA
        "badge_bg": (68, 52, 18, 220),
    },
    "gamecube": {
        "label": "GAMECUBE",
        "family": "gamecube",
        "accent_bgra": (205, 80, 105, 255),  # GameCube Indigo Purple in BGRA
        "badge_bg": (72, 26, 38, 220),
    },
    "n64": {
        "label": "N64",
        "family": "n64",
        "accent_bgra": (205, 75, 25, 255),  # N64 Cobalt Blue in BGRA
        "badge_bg": (62, 24, 12, 220),
    },
    "steam deck": {
        "label": "STEAM DECK",
        "family": "steam",
        "accent_bgra": (235, 175, 45, 255),  # Steam Cyan/Blue in BGRA
        "badge_bg": (65, 45, 15, 220),
    },
    "pc": {
        "label": "PC",
        "family": "pc",
        "accent_bgra": (240, 210, 80, 255),
        "badge_bg": (60, 50, 20, 220),
    },
    "elgato": {
        "label": "ELGATO 4K S",
        "family": "elgato",
        "accent_bgra": (250, 160, 60, 255),
        "badge_bg": (65, 35, 15, 220),
    },
}

PLATFORM_ALIASES: dict[str, str] = {
    "nintendo 64": "n64",
    "nintendo64": "n64",
    "gcn": "gamecube",
    "gc": "gamecube",
    "nintendo gamecube": "gamecube",
    "wiiu": "wii u",
    "nintendo wii u": "wii u",
    "nintendo wii": "wii",
    "nintendo switch": "switch",
    "nintendo switch 2": "switch 2",
    "original xbox": "xbox",
    "xbox og": "xbox",
}


def read_image_unchanged(path: Optional[str]) -> Optional[np.ndarray]:
    """Read an image (keeping alpha) from any path.

    ``cv2.imread`` cannot open non-ASCII paths on Windows (e.g. ``C:\\Users\\José\\logo.png``), so the bytes are
    read by Python and decoded by OpenCV instead.
    """
    if not path:
        return None
    try:
        data = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_UNCHANGED)


def get_platform_preset(platform_name: str) -> dict[str, object]:
    """Resolve platform preset from user string (case-insensitive)."""
    key = (platform_name or "elgato").strip().lower()
    if key in PLATFORM_ALIASES:
        key = PLATFORM_ALIASES[key]
    if key in PLATFORM_PRESETS:
        return PLATFORM_PRESETS[key]
    for k in sorted(PLATFORM_PRESETS.keys(), key=len, reverse=True):
        preset = PLATFORM_PRESETS[k]
        if k in key or key in str(preset["label"]).lower():
            return preset
    return {
        "label": platform_name.strip().upper() or "ELGATO 4K S",
        "family": "generic",
        "accent_bgra": (130, 232, 93, 255),
        "badge_bg": (25, 45, 30, 220),
    }


def measure_platform_badge(scale: float, platform_name: str = "PS5", label: Optional[str] = None) -> tuple[int, int]:
    """Return the (width, height) in pixels that :func:`draw_platform_badge` will occupy."""
    label = label or str(get_platform_preset(platform_name)["label"])
    icon_box = int(round(34 * scale))
    thickness = max(1, int(round(1.5 * scale)))
    (tw, _), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_DUPLEX, 0.50 * scale, thickness)
    pad_x = int(round(12 * scale))
    return icon_box + tw + pad_x * 2, int(round(34 * scale))


def draw_platform_badge(
    canvas: np.ndarray,
    x0: int,
    y0: int,
    scale: float,
    platform_name: str = "PS5",
    custom_logo_path: Optional[str] = None,
    label: Optional[str] = None,
) -> int:
    """Draw a vector console/platform logo emblem + label pill onto the BGRA canvas.

    Args:
        label: Optional text overriding the preset badge label (e.g. "PS5 PRO - 120HZ MODE").

    Returns:
        The width (in pixels) of the rendered platform badge.
    """
    preset = get_platform_preset(platform_name)
    label = label or str(preset["label"])
    family = str(preset["family"])
    accent: tuple[int, int, int, int] = preset["accent_bgra"]  # type: ignore[assignment]
    badge_bg: tuple[int, int, int, int] = preset["badge_bg"]  # type: ignore[assignment]

    badge_w, badge_h = measure_platform_badge(scale, platform_name, label)
    icon_box = int(round(34 * scale))
    text_scale = 0.50 * scale
    thickness = max(1, int(round(1.5 * scale)))
    (_, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_DUPLEX, text_scale, thickness)
    pad_x = int(round(12 * scale))

    h_can, w_can = canvas.shape[:2]
    x1 = min(w_can - 4, x0 + badge_w)
    y1 = min(h_can - 4, y0 + badge_h)
    if x1 <= x0 or y1 <= y0:
        return 0

    # Background pill & accent left strip
    canvas[y0:y1, x0:x1] = badge_bg
    canvas[y0:y1, x0 : min(x1, x0 + icon_box)] = accent
    cv2.rectangle(canvas, (x0, y0), (x1, y1), accent, max(1, int(round(1.5 * scale))), cv2.LINE_AA)

    cx = x0 + icon_box // 2
    cy = y0 + badge_h // 2
    r = max(4, int(round(10 * scale)))
    white = (255, 255, 255, 255)
    dark = (20, 22, 26, 255)

    # Optional custom PNG icon override
    drew_custom = False
    if custom_logo_path:
        logo_img = read_image_unchanged(custom_logo_path)
        if logo_img is not None and logo_img.ndim == 2:
            logo_img = cv2.cvtColor(logo_img, cv2.COLOR_GRAY2BGR)
        if logo_img is not None:
            target_sz = max(8, icon_box - int(round(6 * scale)))
            resized = cv2.resize(logo_img, (target_sz, target_sz), interpolation=cv2.INTER_AREA)
            lx0 = cx - target_sz // 2
            ly0 = cy - target_sz // 2
            if resized.shape[2] == 4:
                al = resized[:, :, 3:4].astype(np.float32) / 255.0
                dst = canvas[ly0 : ly0 + target_sz, lx0 : lx0 + target_sz, :3].astype(np.float32)
                canvas[ly0 : ly0 + target_sz, lx0 : lx0 + target_sz, :3] = np.clip(
                    resized[:, :, :3] * al + dst * (1.0 - al), 0, 255
                ).astype(np.uint8)
                canvas[ly0 : ly0 + target_sz, lx0 : lx0 + target_sz, 3] = 255
            else:
                canvas[ly0 : ly0 + target_sz, lx0 : lx0 + target_sz, :3] = resized[:, :, :3]
                canvas[ly0 : ly0 + target_sz, lx0 : lx0 + target_sz, 3] = 255
            drew_custom = True

    if not drew_custom:
        if family == "playstation":
            # Draw stylized PlayStation 'P' vertical mast + 'S' base wave & sacred symbols motif
            lw = max(1, int(round(2.0 * scale)))
            cv2.line(canvas, (cx - r // 3, cy - r), (cx - r // 3, cy + r), white, lw, cv2.LINE_AA)
            cv2.ellipse(
                canvas,
                (cx - r // 3, cy - r // 3),
                (int(r * 0.75), int(r * 0.55)),
                0,
                -90,
                90,
                white,
                lw,
                cv2.LINE_AA,
            )
            cv2.line(canvas, (cx - r, cy + r - 1), (cx + r, cy + r // 2), white, lw, cv2.LINE_AA)
        elif family == "xbox":
            # Draw Xbox sphere with carved X
            cv2.circle(canvas, (cx, cy), r, white, -1, cv2.LINE_AA)
            lw = max(1, int(round(2.2 * scale)))
            d = int(round(r * 0.65))
            cv2.line(canvas, (cx - d, cy - d), (cx + d, cy + d), accent, lw, cv2.LINE_AA)
            cv2.line(canvas, (cx + d, cy - d), (cx - d, cy + d), accent, lw, cv2.LINE_AA)
        elif family == "switch":
            # Draw Nintendo Switch asymmetric Joy-Con pair
            lw = max(1, int(round(1.8 * scale)))
            w_half = max(3, int(round(r * 0.72)))
            h_jc = max(4, int(round(r * 0.92)))
            # Left Joy-Con (outlined)
            cv2.rectangle(canvas, (cx - w_half - 1, cy - h_jc), (cx - 1, cy + h_jc), white, lw, cv2.LINE_AA)
            cv2.circle(canvas, (cx - w_half // 2 - 1, cy - h_jc // 3), max(1, int(round(2 * scale))), white, -1, cv2.LINE_AA)
            # Right Joy-Con (filled)
            cv2.rectangle(canvas, (cx + 1, cy - h_jc), (cx + w_half + 1, cy + h_jc), white, -1, cv2.LINE_AA)
            cv2.circle(canvas, (cx + w_half // 2 + 1, cy + h_jc // 4), max(1, int(round(2 * scale))), accent, -1, cv2.LINE_AA)
        elif family == "n64":
            # Draw N64 multicolored 3D 'N' emblem (Green pillars, Yellow accent, Red diagonal)
            lw_p = max(2, int(round(3.0 * scale)))
            dx = max(3, int(round(r * 0.68)))
            dy = max(4, int(round(r * 0.82)))
            n64_green = (55, 205, 45, 255)
            n64_yellow = (25, 220, 255, 255)
            n64_red = (45, 45, 240, 255)
            # Back depth pillars in yellow
            cv2.line(canvas, (cx - dx + 2, cy - dy - 1), (cx - dx + 2, cy + dy - 1), n64_yellow, max(1, lw_p - 1), cv2.LINE_AA)
            cv2.line(canvas, (cx + dx + 2, cy - dy - 1), (cx + dx + 2, cy + dy - 1), n64_yellow, max(1, lw_p - 1), cv2.LINE_AA)
            # Front left & right pillars in N64 green
            cv2.line(canvas, (cx - dx, cy - dy), (cx - dx, cy + dy), n64_green, lw_p, cv2.LINE_AA)
            cv2.line(canvas, (cx + dx, cy - dy), (cx + dx, cy + dy), n64_green, lw_p, cv2.LINE_AA)
            # Diagonal crossbar in N64 red + white highlight
            cv2.line(canvas, (cx - dx, cy - dy), (cx + dx, cy + dy), n64_red, lw_p, cv2.LINE_AA)
            cv2.line(canvas, (cx - dx, cy - dy), (cx + dx, cy + dy), white, 1, cv2.LINE_AA)
        elif family == "gamecube":
            # Draw GameCube isometric hexagonal 'G' cube
            lw = max(1, int(round(1.9 * scale)))
            angles_deg = [-90, -30, 30, 90, 150, 210]
            hex_pts = np.array(
                [
                    [
                        int(round(cx + r * np.cos(np.deg2rad(a)))),
                        int(round(cy + r * np.sin(np.deg2rad(a)))),
                    ]
                    for a in angles_deg
                ],
                dtype=np.int32,
            )
            # Draw outer hexagon in 5 segments (leaving 'G' opening on upper-right edge)
            for idx in [1, 2, 3, 4, 5]:
                p1 = tuple(hex_pts[idx])
                p2 = tuple(hex_pts[(idx + 1) % 6])
                cv2.line(canvas, p1, p2, white, lw, cv2.LINE_AA)
            # Inner isometric cube + horizontal 'G' crossbar
            r_in = max(2, int(round(r * 0.45)))
            inner_pts = np.array(
                [
                    [
                        int(round(cx + r_in * np.cos(np.deg2rad(a)))),
                        int(round(cy + r_in * np.sin(np.deg2rad(a)))),
                    ]
                    for a in angles_deg
                ],
                dtype=np.int32,
            )
            cv2.fillPoly(canvas, [inner_pts], white, cv2.LINE_AA)
            cv2.line(canvas, (cx, cy), tuple(hex_pts[2]), white, lw, cv2.LINE_AA)
        elif family == "wii":
            # Draw Wii Remote vertical controller silhouette + twin 'ii' indicator dots
            lw = max(1, int(round(1.6 * scale)))
            w_rm = max(3, int(round(r * 0.48)))
            h_rm = max(5, int(round(r * 0.92)))
            rx0 = cx - int(round(r * 0.30))
            cv2.rectangle(canvas, (rx0 - w_rm, cy - h_rm), (rx0 + w_rm, cy + h_rm), white, -1, cv2.LINE_AA)
            # Plus D-pad & A-button in accent color on the white Wiimote body
            d_sz = max(1, int(round(2.5 * scale)))
            d_cy = cy - h_rm // 2
            cv2.line(canvas, (rx0 - d_sz, d_cy), (rx0 + d_sz, d_cy), accent, lw, cv2.LINE_AA)
            cv2.line(canvas, (rx0, d_cy - d_sz), (rx0, d_cy + d_sz), accent, lw, cv2.LINE_AA)
            cv2.circle(canvas, (rx0, cy + int(round(2 * scale))), max(1, int(round(1.6 * scale))), accent, -1, cv2.LINE_AA)
            # Stylized 'i' pillar beside the Wiimote
            ix = cx + int(round(r * 0.55))
            cv2.line(canvas, (ix, cy - int(round(r * 0.2))), (ix, cy + h_rm - 1), white, max(2, int(round(2.4 * scale))), cv2.LINE_AA)
            cv2.circle(canvas, (ix, cy - int(round(r * 0.65))), max(1, int(round(1.8 * scale))), white, -1, cv2.LINE_AA)
        elif family == "wii_u":
            # Draw Wii U GamePad horizontal tablet + bold 'U' emblem
            lw = max(1, int(round(1.8 * scale)))
            w_gp = max(5, int(round(r * 0.95)))
            h_gp = max(4, int(round(r * 0.68)))
            cv2.rectangle(canvas, (cx - w_gp, cy - h_gp), (cx + w_gp, cy + h_gp), white, -1, cv2.LINE_AA)
            # Inner screen cutout in accent color with white 'U' curve
            w_sc = max(3, int(round(w_gp * 0.58)))
            h_sc = max(2, int(round(h_gp * 0.66)))
            cv2.rectangle(canvas, (cx - w_sc, cy - h_sc), (cx + w_sc, cy + h_sc), accent, -1, cv2.LINE_AA)
            # Twin analog sticks on the GamePad bezels
            stick_r = max(1, int(round(1.4 * scale)))
            cv2.circle(canvas, (cx - int(round(w_gp * 0.78)), cy - int(round(h_gp * 0.3))), stick_r, accent, -1, cv2.LINE_AA)
            cv2.circle(canvas, (cx + int(round(w_gp * 0.78)), cy - int(round(h_gp * 0.3))), stick_r, accent, -1, cv2.LINE_AA)
        elif family == "steam":
            # Draw Steam Deck ring + core dot
            lw = max(1, int(round(2.2 * scale)))
            cv2.ellipse(canvas, (cx, cy), (r, r), 0, -130, 130, white, lw, cv2.LINE_AA)
            cv2.circle(canvas, (cx, cy), max(2, int(round(r * 0.45))), white, -1, cv2.LINE_AA)
        elif family == "pc":
            # Draw monitor / GPU display icon
            w_m = int(round(r * 0.95))
            h_m = int(round(r * 0.68))
            lw = max(1, int(round(1.8 * scale)))
            cv2.rectangle(canvas, (cx - w_m, cy - h_m), (cx + w_m, cy + h_m // 2), dark, lw, cv2.LINE_AA)
            cv2.line(canvas, (cx - w_m // 2, cy + h_m), (cx + w_m // 2, cy + h_m), dark, lw, cv2.LINE_AA)
        else:
            # Elgato / capture play-circle icon
            cv2.circle(canvas, (cx, cy), r, white, max(1, int(round(1.8 * scale))), cv2.LINE_AA)
            pts = np.array(
                [
                    [cx - r // 3, cy - r // 2],
                    [cx - r // 3, cy + r // 2],
                    [cx + r // 2, cy],
                ],
                dtype=np.int32,
            )
            cv2.fillPoly(canvas, [pts], white, cv2.LINE_AA)

    # Render platform label text
    tx = x0 + icon_box + pad_x
    ty = y0 + (badge_h + th) // 2 - int(round(1 * scale))
    cv2.putText(
        canvas,
        label,
        (tx + 1, ty + 1),
        cv2.FONT_HERSHEY_DUPLEX,
        text_scale,
        (0, 0, 0, 220),
        thickness + 1,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        label,
        (tx, ty),
        cv2.FONT_HERSHEY_DUPLEX,
        text_scale,
        white,
        thickness,
        cv2.LINE_AA,
    )
    return badge_w
