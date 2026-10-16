"""Video and telemetry exporters (Burned-in VideoToolbox MP4, Transparent ProRes 4444 / WebM Alpha, CSV & JSON)."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import platform
import shutil
import subprocess
from typing import Optional, Union
import cv2
import numpy as np

from frametime_analyzer.models import AnalysisSummary, FrameMetrics


def get_ffmpeg_binary() -> Optional[str]:
    """Locate system ffmpeg or bundled imageio-ffmpeg binary."""
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


class VideoExporter:
    """Streams BGR (burned-in) or BGRA (transparent alpha) frames to FFmpeg or OpenCV VideoWriter."""

    def __init__(
        self,
        output_path: Union[str, Path],
        width: int,
        height: int,
        fps: float = 60.0,
        alpha_only: bool = False,
        source_audio_path: Optional[Union[str, Path]] = None,
        use_hardware_accel: bool = True,
    ) -> None:
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.width = width
        self.height = height
        self.fps = fps
        self.alpha_only = alpha_only
        self.source_audio_path = str(source_audio_path) if source_audio_path else None
        self.use_hardware_accel = use_hardware_accel

        self._ffmpeg_proc: Optional[subprocess.Popen[bytes]] = None
        self._cv_writer: Optional[cv2.VideoWriter] = None
        self._open_encoder()

    def _open_encoder(self) -> None:
        ffmpeg_bin = get_ffmpeg_binary()
        suffix = self.output_path.suffix.lower()

        if ffmpeg_bin is not None:
            cmd = [
                ffmpeg_bin,
                "-y",
                "-f",
                "rawvideo",
                "-vcodec",
                "rawvideo",
                "-s",
                f"{self.width}x{self.height}",
                "-pix_fmt",
                "bgra" if self.alpha_only else "bgr24",
                "-r",
                f"{self.fps:.4f}",
                "-i",
                "-",
            ]

            if self.source_audio_path and not self.alpha_only:
                cmd.extend(["-i", self.source_audio_path, "-map", "0:v:0", "-map", "1:a:0?", "-shortest"])

            if self.alpha_only:
                if suffix == ".webm":
                    cmd.extend(
                        [
                            "-c:v",
                            "libvpx-vp9",
                            "-pix_fmt",
                            "yuva420p",
                            "-b:v",
                            "6M",
                            "-auto-alt-ref",
                            "0",
                        ]
                    )
                else:
                    # Default to Apple ProRes 4444 with 10-bit Alpha for DaVinci / FCP / Premiere
                    cmd.extend(
                        [
                            "-c:v",
                            "prores_ks",
                            "-profile:v",
                            "4444",
                            "-pix_fmt",
                            "yuva444p10le",
                        ]
                    )
            else:
                is_mac = platform.system() == "Darwin"
                if is_mac and self.use_hardware_accel:
                    cmd.extend(
                        [
                            "-c:v",
                            "h264_videotoolbox",
                            "-b:v",
                            "18M",
                            "-pix_fmt",
                            "yuv420p",
                        ]
                    )
                else:
                    cmd.extend(
                        [
                            "-c:v",
                            "libx264",
                            "-preset",
                            "fast",
                            "-crf",
                            "18",
                            "-pix_fmt",
                            "yuv420p",
                        ]
                    )
                if self.source_audio_path:
                    cmd.extend(["-c:a", "copy"])

            cmd.append(str(self.output_path))
            try:
                self._ffmpeg_proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                return
            except Exception:
                self._ffmpeg_proc = None

        # Fallback to OpenCV VideoWriter
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._cv_writer = cv2.VideoWriter(
            str(self.output_path),
            fourcc,
            self.fps,
            (self.width, self.height),
        )

    def write_frame(self, frame: np.ndarray) -> None:
        """Write a BGR (or BGRA if alpha_only=True) frame to the video encoder."""
        if self._ffmpeg_proc is not None and self._ffmpeg_proc.stdin is not None:
            try:
                self._ffmpeg_proc.stdin.write(frame.tobytes())
                return
            except BrokenPipeError:
                self._ffmpeg_proc = None

        if self._cv_writer is not None:
            bgr = frame[:, :, :3] if frame.shape[2] == 4 else frame
            self._cv_writer.write(bgr)

    def close(self) -> None:
        if self._ffmpeg_proc is not None:
            if self._ffmpeg_proc.stdin is not None:
                try:
                    self._ffmpeg_proc.stdin.close()
                except Exception:
                    pass
            self._ffmpeg_proc.wait(timeout=15.0)
            self._ffmpeg_proc = None
        if self._cv_writer is not None:
            self._cv_writer.release()
            self._cv_writer = None

    def __enter__(self) -> VideoExporter:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()


def export_telemetry_csv(metrics_list: list[FrameMetrics], csv_path: Union[str, Path]) -> Path:
    """Export frame-by-frame telemetry metrics to CSV."""
    out = Path(csv_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "frame_index",
        "timestamp_ms",
        "frame_duration_ms",
        "is_duplicate",
        "is_torn",
        "tear_line_y",
        "frametime_ms",
        "rolling_fps",
        "instant_fps",
        "fps_1_percent_low",
        "fps_0_1_percent_low",
        "mean_luma_diff",
        "p95_tile_diff",
        "adaptive_threshold",
        "container_width",
        "container_height",
        "target_width",
        "target_height",
        "render_width",
        "render_height",
        "render_scale_percent",
        "resolution_tier_label",
        "resolution_confidence",
        "esf_fwhm_px",
        "spectral_cutoff_ratio",
    ]
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for m in metrics_list:
            row = m.to_dict()
            row["tear_line_y"] = ";".join(str(y) for y in m.tear_line_y)
            filtered = {k: row[k] for k in fieldnames if k in row}
            writer.writerow(filtered)
    return out


def export_summary_json(
    summary: AnalysisSummary,
    json_path: Union[str, Path],
    metrics_list: Optional[list[FrameMetrics]] = None,
) -> Path:
    """Export aggregate summary and optional frame telemetry to JSON."""
    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {"summary": summary.to_dict()}
    if metrics_list is not None:
        payload["frames"] = [m.to_dict() for m in metrics_list]
    with out.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return out
