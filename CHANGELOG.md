# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [semantic versioning](https://semver.org/).

## [Unreleased]

First public release (0.1.0).

### Analysis
- Frametime, frame-pacing and 1% / 0.1% low analysis based on tile-based repeated-frame detection, for 60, 120 and 240 Hz captures (including 59.94 / 119.88 Hz).
- Screen tearing detection with tear line positions.
- Letterbox-aware target resolution and per-frame internal render resolution / DRS estimation.
- Manual resolution override: manual target resolution, fixed render resolution, or a DRS range that clamps the estimate (`--target-res`, `--render-res`, `--render-range`, and in the desktop app).

### Output
- Burned-in H.264 video with audio passthrough, ProRes 4444 / VP9 transparent overlay, CSV and JSON telemetry.
- GPU H.264 encoding: VideoToolbox (macOS), NVENC / Quick Sync / AMF (Windows), NVENC / VAAPI / Quick Sync (Linux), with automatic fallback to `libx264`. Controlled with `--no-hw` and `FTA_VIDEO_ENCODER`.
- Customizable HUD layouts saved as JSON: editable labels, platform badge text and custom icon, brand / channel logo, extra info panel, per-element visibility, anchor and offset, HUD size and panel opacity. Platform badges for PlayStation, Xbox, Nintendo, Steam Deck, PC and Elgato.

### Apps
- Desktop app (`fta gui` / `fta-gui`) with a live HUD preview on your video, drag-to-place HUD elements, and background processing with progress and cancel.
- `fta` command line: `analyze` (with `--layout` and `--info`), `demo`, `devices`, `live`, `studio`, `gui`, `--version`.
- Browser Studio with frame inspection and a stair-step pixel counter, plus an OBS overlay page.
- Live analysis of UVC capture devices (AVFoundation, DirectShow / Media Foundation, V4L2).

### Distribution
- Standalone downloads for Windows, macOS (Apple Silicon) and Linux, and Python packages for `pipx` / `uv`.
- Documentation site, contributing guide, and issue / pull request templates.

[Unreleased]: https://github.com/mathiasdbo/Frametime-analyzer-tool/commits/main
