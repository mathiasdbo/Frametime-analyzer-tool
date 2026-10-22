"""Video and telemetry exporters (burned-in H.264 MP4, transparent ProRes 4444 / WebM alpha, CSV & JSON).

Burned-in video uses a GPU encoder when one works on this machine (VideoToolbox on macOS; NVENC, Quick Sync
or AMF on Windows; NVENC, VAAPI or Quick Sync on Linux) and falls back to libx264 otherwise.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from typing import IO, Optional, Union
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


# Keeps ffmpeg from flashing a console window when launched from the GUI on Windows.
_SUBPROCESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


@dataclass(frozen=True)
class H264Encoder:
    """An ffmpeg H.264 encoder configuration."""

    name: str
    codec_args: tuple[str, ...]
    global_args: tuple[str, ...] = ()  # Placed before the inputs (e.g. VAAPI device selection)
    filter_args: tuple[str, ...] = ()
    hardware: bool = True


SOFTWARE_H264 = H264Encoder(
    "libx264", ("-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p"), hardware=False
)
_NVENC = H264Encoder("h264_nvenc", ("-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19", "-b:v", "0", "-pix_fmt", "yuv420p"))
_QSV = H264Encoder("h264_qsv", ("-c:v", "h264_qsv", "-global_quality", "20", "-pix_fmt", "nv12"))
_AMF = H264Encoder("h264_amf", ("-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "19", "-qp_p", "21", "-pix_fmt", "nv12"))
_VAAPI = H264Encoder(
    "h264_vaapi",
    ("-c:v", "h264_vaapi", "-qp", "20"),
    global_args=("-vaapi_device", "/dev/dri/renderD128"),
    filter_args=("-vf", "format=nv12,hwupload"),
)
_VIDEOTOOLBOX = H264Encoder("h264_videotoolbox", ("-c:v", "h264_videotoolbox", "-b:v", "18M", "-pix_fmt", "yuv420p"))


def hardware_encoder_candidates(system: Optional[str] = None) -> list[H264Encoder]:
    """GPU H.264 encoders worth trying on this OS, most preferred first."""
    system = system or platform.system()
    if system == "Darwin":
        return [_VIDEOTOOLBOX]
    if system == "Windows":
        return [_NVENC, _QSV, _AMF]
    return [_NVENC, _VAAPI, _QSV]


@lru_cache(maxsize=8)
def _encoder_works(ffmpeg_bin: str, encoder: H264Encoder) -> bool:
    """Encode a tiny test clip: ffmpeg may list encoders whose GPU / driver is missing."""
    cmd = [
        ffmpeg_bin, "-hide_banner", "-loglevel", "error", *encoder.global_args,
        "-f", "lavfi", "-i", "color=c=black:s=640x360:r=30:d=0.2",
        *encoder.filter_args, *encoder.codec_args, "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, creationflags=_SUBPROCESS_FLAGS
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def select_h264_encoder(ffmpeg_bin: str, use_hardware_accel: bool = True) -> H264Encoder:
    """Pick the best working H.264 encoder (GPU when available, else libx264).

    Set the ``FTA_VIDEO_ENCODER`` environment variable (e.g. ``libx264`` or ``h264_nvenc``) to force one.
    """
    forced = os.environ.get("FTA_VIDEO_ENCODER", "").strip().lower()
    all_encoders = {e.name: e for e in (SOFTWARE_H264, _NVENC, _QSV, _AMF, _VAAPI, _VIDEOTOOLBOX)}
    if forced:
        if forced in all_encoders:
            return all_encoders[forced]
        return H264Encoder(forced, ("-c:v", forced, "-pix_fmt", "yuv420p"))
    if use_hardware_accel:
        for encoder in hardware_encoder_candidates():
            if _encoder_works(ffmpeg_bin, encoder):
                return encoder
    return SOFTWARE_H264


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
        self.encoder_name = "opencv-mp4v"

        self._ffmpeg_proc: Optional[subprocess.Popen[bytes]] = None
        self._ffmpeg_log: Optional[IO[bytes]] = None
        self._cv_writer: Optional[cv2.VideoWriter] = None
        self._open_encoder()

    def _open_encoder(self) -> None:
        ffmpeg_bin = get_ffmpeg_binary()
        suffix = self.output_path.suffix.lower()

        if ffmpeg_bin is not None:
            encoder: Optional[H264Encoder] = None
            if not self.alpha_only:
                encoder = select_h264_encoder(ffmpeg_bin, self.use_hardware_accel)
            cmd = [ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-nostats", "-y"]
            if encoder is not None:
                cmd.extend(encoder.global_args)
            cmd.extend(
                [
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
            )

            if self.source_audio_path and not self.alpha_only:
                cmd.extend(["-i", self.source_audio_path, "-map", "0:v:0", "-map", "1:a:0?", "-shortest"])

            if self.alpha_only:
                if suffix == ".webm":
                    cmd.extend(["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "6M", "-auto-alt-ref", "0"])
                else:
                    # Default to Apple ProRes 4444 with 10-bit Alpha for DaVinci / FCP / Premiere (all platforms)
                    cmd.extend(["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"])
                self.encoder_name = "libvpx-vp9" if suffix == ".webm" else "prores_ks"
            else:
                assert encoder is not None
                cmd.extend([*encoder.filter_args, *encoder.codec_args])
                self.encoder_name = encoder.name
                if self.source_audio_path:
                    cmd.extend(["-c:a", "copy"])

            cmd.append(str(self.output_path))
            try:
                # stderr goes to a temp file: an unread pipe can fill up and stall ffmpeg on long encodes
                self._ffmpeg_log = tempfile.TemporaryFile()
                self._ffmpeg_proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=self._ffmpeg_log,
                    creationflags=_SUBPROCESS_FLAGS,
                )
                return
            except OSError:
                self._ffmpeg_proc = None

        # Fallback to OpenCV VideoWriter
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._cv_writer = cv2.VideoWriter(
            str(self.output_path),
            fourcc,
            self.fps,
            (self.width, self.height),
        )

    def _ffmpeg_error(self) -> str:
        if self._ffmpeg_log is None:
            return ""
        self._ffmpeg_log.seek(0)
        return self._ffmpeg_log.read().decode("utf-8", "replace").strip()[-2000:]

    def write_frame(self, frame: np.ndarray) -> None:
        """Write a BGR (or BGRA if alpha_only=True) frame to the video encoder."""
        if self._ffmpeg_proc is not None and self._ffmpeg_proc.stdin is not None:
            try:
                self._ffmpeg_proc.stdin.write(frame.tobytes())
            except (BrokenPipeError, OSError) as exc:
                self._ffmpeg_proc.wait(timeout=10)
                raise RuntimeError(
                    f"ffmpeg ({self.encoder_name}) stopped while writing {self.output_path.name}: {self._ffmpeg_error()}"
                ) from exc
            return

        if self._cv_writer is not None:
            bgr = frame[:, :, :3] if frame.shape[2] == 4 else frame
            self._cv_writer.write(bgr)

    def close(self) -> None:
        if self._ffmpeg_proc is not None:
            proc, self._ffmpeg_proc = self._ffmpeg_proc, None
            if proc.stdin is not None:
                try:
                    proc.stdin.close()
                except OSError:
                    pass
            try:
                returncode = proc.wait(timeout=300.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                returncode = proc.wait()
            error = self._ffmpeg_error()
            if self._ffmpeg_log is not None:
                self._ffmpeg_log.close()
                self._ffmpeg_log = None
            if returncode != 0:
                raise RuntimeError(f"ffmpeg ({self.encoder_name}) failed to write {self.output_path.name}: {error}")
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
