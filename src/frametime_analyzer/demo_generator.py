"""Synthetic gameplay capture generator for testing frametime, tearing, and DRS resolution detection."""
from __future__ import annotations

from pathlib import Path
from typing import Union
import cv2
import numpy as np


def render_synthetic_scene(
    width: int,
    height: int,
    step_index: int,
    internal_render_scale: float = 1.0,
    upscale_mode: int = cv2.INTER_LINEAR,
    add_native_hud: bool = False,
) -> np.ndarray:
    """Render a 3D-like geometric scene at (width * scale, height * scale) and upscale to (width, height)."""
    rw = max(64, int(round(width * internal_render_scale)))
    rh = max(36, int(round(height * internal_render_scale)))

    canvas = np.full((rh, rw, 3), (28, 32, 40), dtype=np.uint8)

    # Scrolling high-contrast grid & diagonal architecture beams (ideal for ESF & stair-step counting)
    shift_x = (step_index * 11) % max(1, rw)
    shift_y = (step_index * 7) % max(1, rh)

    grid_step = max(8, rw // 16)
    for gx in range(0, rw, grid_step):
        x_pos = (gx + shift_x) % rw
        cv2.line(canvas, (x_pos, 0), (x_pos, rh - 1), (75, 85, 100), 1)
    for gy in range(0, rh, grid_step):
        y_pos = (gy + shift_y) % rh
        cv2.line(canvas, (0, y_pos), (rw - 1, y_pos), (75, 85, 100), 1)

    # Sharp high-contrast tilted polygon / architectural roof (shallow diagonal ~22 degrees)
    cx = int(rw * 0.25 + ((step_index * 9) % int(rw * 0.4)))
    cy = int(rh * 0.35 + ((step_index * 5) % int(rh * 0.3)))
    dx = max(20, int(rw * 0.28))
    dy = max(8, int(dx * 0.40))
    pts = np.array(
        [
            [cx, cy],
            [cx + dx, cy + dy],
            [cx + dx - dy, cy + dy + int(rh * 0.22)],
            [cx - dy, cy + int(rh * 0.22)],
        ],
        dtype=np.int32,
    )
    cv2.fillPoly(canvas, [pts], (235, 240, 245))

    # High-contrast circles and pillars
    for i in range(4):
        px = int((rw * (0.15 + i * 0.22) + step_index * (13 + i * 3)) % rw)
        py = int((rh * (0.2 + i * 0.18) + step_index * (9 + i * 2)) % rh)
        cv2.rectangle(
            canvas,
            (px, py),
            (min(rw - 1, px + max(10, rw // 18)), min(rh - 1, py + max(20, rh // 6))),
            (40, 195, 245),
            -1,
        )

    if (rw, rh) != (width, height):
        upscaled = cv2.resize(canvas, (width, height), interpolation=upscale_mode)
    else:
        upscaled = canvas

    if add_native_hud:
        # Draw a static native-resolution HUD box in the top-left corner [0.02..0.22, 0.03..0.12]
        hx0, hy0 = int(width * 0.02), int(height * 0.03)
        hx1, hy1 = int(width * 0.22), int(height * 0.12)
        cv2.rectangle(upscaled, (hx0, hy0), (hx1, hy1), (20, 20, 20), -1)
        cv2.rectangle(upscaled, (hx0, hy0), (hx1, hy1), (255, 255, 255), 2)
        cv2.putText(
            upscaled,
            "HUD 4K NATIVE",
            (hx0 + 10, hy0 + int((hy1 - hy0) * 0.65)),
            cv2.FONT_HERSHEY_SIMPLEX,
            max(0.5, height / 1080.0 * 0.7),
            (255, 255, 255),
            2,
        )

    return upscaled


def generate_demo_capture_video(
    output_path: Union[str, Path],
    width: int = 1280,
    height: int = 720,
    fps: float = 60.0,
    total_frames: int = 180,
) -> Path:
    """Create a synthetic gameplay capture video with 60fps, 30fps, stutter, tearing, and DRS scaling."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out), fourcc, fps, (width, height))

    scene_step = 0
    prev_frame = render_synthetic_scene(width, height, scene_step, internal_render_scale=1.0)

    for idx in range(total_frames):
        # Segment 1 (frames 0..59): Locked 60 FPS @ 100% native resolution
        # Segment 2 (frames 60..119): Locked 30 FPS (every odd frame is duplicate) @ 66.7% DRS scale
        # Segment 3 (frames 120..179): 60 FPS with periodic stutters & simulated screen tearing @ 50% DRS scale
        if idx < 60:
            scale = 1.0
            is_dup = False
            is_tear = False
        elif idx < 120:
            scale = 0.667
            is_dup = (idx % 2 == 1)
            is_tear = False
        else:
            scale = 0.50
            is_dup = (idx in (130, 131, 132, 155, 156))
            is_tear = (idx in (140, 165))

        if is_dup:
            frame = prev_frame.copy()
        else:
            scene_step += 1
            new_frame = render_synthetic_scene(width, height, scene_step, internal_render_scale=scale)
            if is_tear:
                tear_y = height // 2
                frame = prev_frame.copy()
                frame[tear_y:, :] = new_frame[tear_y:, :]
            else:
                frame = new_frame
            prev_frame = frame.copy()

        writer.write(frame)

    writer.release()
    return out
