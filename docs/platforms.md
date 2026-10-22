# Platform notes

Frametime Analyzer is tested on **Windows, macOS and Linux** (Python 3.9 and 3.12) for every change.

## Video encoding

The burned-in video is H.264. A GPU encoder is faster and frees the CPU for the analysis, so one is used when it actually works on your machine. Each candidate is tested with a short trial encode the first time an export starts:

| System | GPU encoders tried, in order | Fallback |
|---|---|---|
| macOS | VideoToolbox (`h264_videotoolbox`) | `libx264` |
| Windows | NVIDIA NVENC (`h264_nvenc`), Intel Quick Sync (`h264_qsv`), AMD AMF (`h264_amf`) | `libx264` |
| Linux | NVIDIA NVENC, VAAPI (`h264_vaapi`, Intel / AMD), Intel Quick Sync | `libx264` |

- Turn GPU encoding off with `--no-hw` or the *Use GPU video encoder* checkbox. `libx264` at CRF 18 gives the most consistent quality.
- Force a specific encoder with the `FTA_VIDEO_ENCODER` environment variable:

    === "macOS / Linux"

        ```bash
        FTA_VIDEO_ENCODER=libx264 fta analyze capture.mp4 -o out.mp4
        ```

    === "Windows (PowerShell)"

        ```powershell
        $env:FTA_VIDEO_ENCODER = "h264_nvenc"
        fta analyze capture.mp4 -o out.mp4
        ```

The transparent overlay always uses ProRes 4444 (`prores_ks`) or VP9 (`libvpx-vp9`), which have no GPU encoders.

### FFmpeg

An `ffmpeg` on your `PATH` is used when present; otherwise the copy bundled with the app (via `imageio-ffmpeg`) is used. If GPU encoding isn't picked up, check that your FFmpeg build includes the encoder: `ffmpeg -hide_banner -encoders | grep 264`.

## Capture devices

| System | Capture API | Notes |
|---|---|---|
| macOS | AVFoundation | Allow camera access for your terminal or the app in *System Settings ▸ Privacy & Security ▸ Camera* |
| Windows | DirectShow, then Media Foundation | Allow desktop apps to use the camera in *Settings ▸ Privacy & security ▸ Camera* |
| Linux | Video4Linux2 (V4L2) | Your user needs access to `/dev/video*`, usually via the `video` group: `sudo usermod -aG video $USER`, then log out and back in |

Only one program can use a capture device at a time.

## Windows

- **SmartScreen** warns about the downloaded app until it's code-signed: **More info → Run anyway**.
- Paths with accented or non-Latin characters (e.g. `C:\Users\José\...`) are supported for videos, layouts and logos.
- No console window appears when the desktop app runs FFmpeg.
- In PowerShell, continue long commands with a backtick `` ` `` instead of `\`.

## macOS

- The downloaded app is for **Apple Silicon**. On Intel Macs, [install with pipx](installation.md#option-2-pipx-or-uv).
- **Gatekeeper**: open the app the first time with right-click → **Open**. If it's reported as damaged: `xattr -dr com.apple.quarantine "/Applications/Frametime Analyzer.app"`.

## Linux

- The downloaded app needs **glibc 2.35+** (Ubuntu 22.04, Debian 12, Fedora 36 or newer).
- The desktop app uses Qt. Minimal systems may need: `sudo apt install libegl1 libxkbcommon0 libxcb-cursor0 libfontconfig1` (Debian / Ubuntu) or the equivalent packages for your distribution.
- Qt chooses Wayland or X11 automatically. If the window doesn't appear, force one with `QT_QPA_PLATFORM=xcb fta gui` (X11) or `QT_QPA_PLATFORM=wayland fta gui`.
- VAAPI encoding uses `/dev/dri/renderD128`.
