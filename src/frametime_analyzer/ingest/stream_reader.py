"""High-performance video file and live UVC capture stream readers."""
from __future__ import annotations

from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Thread
import os
import platform
import time
from typing import Iterator, Optional, Union

os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")
import cv2
import numpy as np

from frametime_analyzer.models import FramePacket


def _make_luma_small(bgr: np.ndarray, target_width: int = 640) -> np.ndarray:
    """Convert BGR frame to downscaled grayscale luma for fast motion/tear analysis."""
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    if w > target_width:
        scale = target_width / float(w)
        target_height = max(16, int(round(h * scale)))
        gray = cv2.resize(gray, (target_width, target_height), interpolation=cv2.INTER_AREA)
    return gray


def _snap_nominal_fps(raw_fps: float) -> float:
    """Snap VFR average framerate (e.g. 58.53 from Elgato Studio MOV) to nominal capture clock."""
    if raw_fps <= 1.0:
        return 60.0
    for nominal, tol in [(30.0, 2.0), (60.0, 3.5), (120.0, 6.0), (144.0, 6.0), (240.0, 10.0)]:
        if abs(raw_fps - nominal) <= tol:
            return nominal
    return raw_fps


class VideoFileReader:
    """Reads video files at native resolution with accurate container timestamps."""

    def __init__(
        self,
        path: Union[str, Path],
        analysis_width: int = 640,
        queue_size: int = 64,
        max_frames: Optional[int] = None,
    ) -> None:
        self.path = str(path)
        self.analysis_width = analysis_width
        self.queue_size = queue_size
        self.max_frames = max_frames

        cap = cv2.VideoCapture(self.path)
        if not cap.isOpened():
            raise FileNotFoundError(f"Could not open video file: {self.path}")

        self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        raw_fps = float(cap.get(cv2.CAP_PROP_FPS))
        self.fps = _snap_nominal_fps(raw_fps)
        self.total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if self.max_frames is not None and self.total_frames > 0:
            self.total_frames = min(self.total_frames, self.max_frames)
        cap.release()

        self._queue: Queue[Optional[FramePacket]] = Queue(maxsize=self.queue_size)
        self._stop_event = Event()
        self._thread: Optional[Thread] = None

    def start(self) -> VideoFileReader:
        """Start background decoding thread."""
        self._stop_event.clear()
        self._thread = Thread(target=self._decode_worker, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        """Stop background decoding thread."""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except Empty:
                    break
            self._thread.join(timeout=2.0)

    def _decode_worker(self) -> None:
        cap = cv2.VideoCapture(self.path)
        frame_idx = 0
        default_dt_ms = 1000.0 / self.fps
        prev_ts_ms = 0.0

        try:
            while not self._stop_event.is_set():
                if self.max_frames is not None and frame_idx >= self.max_frames:
                    break

                grabbed, frame_bgr = cap.read()
                if not grabbed or frame_bgr is None:
                    break

                pos_msec = float(cap.get(cv2.CAP_PROP_POS_MSEC))
                if frame_idx == 0:
                    ts_ms = 0.0
                    dt_ms = default_dt_ms
                elif pos_msec > prev_ts_ms:
                    ts_ms = pos_msec
                    dt_ms = ts_ms - prev_ts_ms
                else:
                    ts_ms = frame_idx * default_dt_ms
                    dt_ms = default_dt_ms

                prev_ts_ms = ts_ms
                luma_small = _make_luma_small(frame_bgr, self.analysis_width)

                packet = FramePacket(
                    frame_index=frame_idx,
                    timestamp_ms=ts_ms,
                    duration_ms=dt_ms,
                    container_fps=self.fps,
                    raw_bgr=frame_bgr,
                    luma_small=luma_small,
                )

                while not self._stop_event.is_set():
                    try:
                        self._queue.put(packet, timeout=0.1)
                        break
                    except Full:
                        continue

                frame_idx += 1
        finally:
            cap.release()
            while not self._stop_event.is_set():
                try:
                    self._queue.put(None, timeout=0.1)
                    break
                except Full:
                    continue

    def __iter__(self) -> Iterator[FramePacket]:
        if self._thread is None:
            self.start()
        try:
            while not self._stop_event.is_set():
                try:
                    packet = self._queue.get(timeout=0.5)
                except Empty:
                    if self._thread is not None and not self._thread.is_alive():
                        break
                    continue
                if packet is None:
                    break
                yield packet
        finally:
            self.stop()

    def close(self) -> None:
        self.stop()

    def read_frame_at(self, frame_index: int) -> FramePacket:
        """Random-access read of a single frame for the interactive Studio UI."""
        cap = cv2.VideoCapture(self.path)
        try:
            clamped_idx = max(0, min(frame_index, max(0, self.total_frames - 1)))
            cap.set(cv2.CAP_PROP_POS_FRAMES, clamped_idx)
            grabbed, frame_bgr = cap.read()
            if not grabbed or frame_bgr is None:
                raise IndexError(f"Could not read frame {frame_index} from {self.path}")
            default_dt_ms = 1000.0 / self.fps
            ts_ms = clamped_idx * default_dt_ms
            return FramePacket(
                frame_index=clamped_idx,
                timestamp_ms=ts_ms,
                duration_ms=default_dt_ms,
                container_fps=self.fps,
                raw_bgr=frame_bgr,
                luma_small=_make_luma_small(frame_bgr, self.analysis_width),
            )
        finally:
            cap.release()


class LiveCaptureReader:
    """Real-time UVC / AVFoundation stream reader for Elgato 4K S and capture devices."""

    def __init__(
        self,
        device_index: int = 0,
        width: int = 1920,
        height: int = 1080,
        fps: float = 60.0,
        analysis_width: int = 640,
    ) -> None:
        self.device_index = device_index
        self.requested_width = width
        self.requested_height = height
        self.requested_fps = fps
        self.analysis_width = analysis_width

        backend = cv2.CAP_AVFOUNDATION if platform.system() == "Darwin" else cv2.CAP_ANY
        self._cap = cv2.VideoCapture(self.device_index, backend)
        if not self._cap.isOpened():
            self._cap = cv2.VideoCapture(self.device_index)
        if not self._cap.isOpened():
            raise RuntimeError(
                f"Could not open capture device index {self.device_index}. "
                "Verify Elgato 4K S or UVC capture card is connected and camera permissions are granted."
            )

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(width))
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(height))
        self._cap.set(cv2.CAP_PROP_FPS, float(fps))

        self.width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH) or width)
        self.height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or height)
        actual_fps = float(self._cap.get(cv2.CAP_PROP_FPS) or fps)
        self.fps = actual_fps if actual_fps > 1.0 else fps

        self._stop_event = Event()
        self._queue: Queue[FramePacket] = Queue(maxsize=8)
        self._thread: Optional[Thread] = None

    def start(self) -> LiveCaptureReader:
        self._stop_event.clear()
        self._thread = Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._cap.isOpened():
            self._cap.release()

    def _capture_loop(self) -> None:
        frame_idx = 0
        start_perf = time.perf_counter()
        prev_ms = 0.0
        default_dt = 1000.0 / self.fps

        while not self._stop_event.is_set():
            grabbed, frame_bgr = self._cap.read()
            if not grabbed or frame_bgr is None:
                time.sleep(0.002)
                continue

            now_ms = (time.perf_counter() - start_perf) * 1000.0
            dt_ms = (now_ms - prev_ms) if frame_idx > 0 else default_dt
            prev_ms = now_ms

            packet = FramePacket(
                frame_index=frame_idx,
                timestamp_ms=now_ms,
                duration_ms=dt_ms,
                container_fps=self.fps,
                raw_bgr=frame_bgr,
                luma_small=_make_luma_small(frame_bgr, self.analysis_width),
            )

            if self._queue.full():
                try:
                    self._queue.get_nowait()
                except Empty:
                    pass
            try:
                self._queue.put_nowait(packet)
            except Full:
                pass
            frame_idx += 1

    def __iter__(self) -> Iterator[FramePacket]:
        if self._thread is None:
            self.start()
        try:
            while not self._stop_event.is_set():
                try:
                    yield self._queue.get(timeout=0.5)
                except Empty:
                    continue
        finally:
            self.stop()


def list_capture_devices(max_devices: int = 5) -> list[dict[str, Union[int, str, float]]]:
    """Probe connected UVC / AVFoundation capture devices (such as Elgato 4K S)."""
    devices: list[dict[str, Union[int, str, float]]] = []
    backend = cv2.CAP_AVFOUNDATION if platform.system() == "Darwin" else cv2.CAP_ANY
    for idx in range(max_devices):
        cap = cv2.VideoCapture(idx, backend)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            devices.append(
                {
                    "index": idx,
                    "resolution": f"{w}x{h}",
                    "width": w,
                    "height": h,
                    "fps": fps if fps > 0 else 60.0,
                }
            )
            cap.release()
    return devices
