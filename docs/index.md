# Frametime Analyzer

**Frametime Analyzer** measures the performance of gameplay captures from consoles and PCs, in the style of Digital Foundry's *FPSGui* and *TrDrop*. It works with recordings from an **Elgato 4K S** or any UVC capture device, and on recorded video files.

It analyzes every frame and draws a customizable HUD (frame-rate, frametime graph, tearing, render resolution) over the video, or exports it as a transparent overlay for your editor.

![Burned-in HUD on a capture](assets/screenshots/hud-example.jpg)

<div class="grid cards" markdown>

-   :material-download: **[Install](installation.md)**

    Download the app for Windows, macOS or Linux (no Python needed), or install it with `pipx`.

-   :material-rocket-launch: **[Quick start](quick-start.md)**

    Analyze your first capture in a couple of minutes.

-   :material-monitor-dashboard: **[Desktop app](gui.md)**

    Preview the HUD on your video, drag elements into place, and process with one click.

-   :material-console: **[Command line](cli.md)**

    Every `fta` command and option, ready for scripts and batch jobs.

</div>

## What it measures

| | |
|---|---|
| **Frame-rate & frametime** | Detects repeated (duplicate) frames to compute real frametimes, rolling FPS, and 1% / 0.1% lows. Works for 60, 120 and 240 Hz captures, including 59.94 / 119.88 Hz. |
| **Screen tearing** | Finds horizontal tear lines and their exact Y position, marks them on the HUD and in the frame-rate graph. |
| **Resolution** | Detects the target output resolution (ignoring letterbox/pillarbox bars) and estimates the internal render resolution per frame, including dynamic resolution scaling (DRS). You can [override it manually](resolution.md) when you know better. |

## What it produces

- **Burned-in video** (`.mp4` / `.mov`) with the HUD drawn on top, original audio kept, GPU-accelerated encoding where available.
- **Transparent overlay** (ProRes 4444 `.mov` or VP9 `.webm`) to place over your footage in DaVinci Resolve, Final Cut Pro or Premiere Pro.
- **Telemetry**: per-frame CSV and a JSON summary for your own charts.

## Ways to use it

- **[Desktop app](gui.md)** (`fta gui`): the easiest way. Live preview, drag-to-place HUD, editable labels, logos and extra info.
- **[Command line](cli.md)** (`fta analyze`): scripting and batch processing, with the same layouts saved from the desktop app.
- **[Studio & OBS overlay](live-capture.md)** (`fta studio`): a browser-based frame inspector with a Digital Foundry-style pixel counter, plus a transparent overlay for OBS.
- **[Live capture](live-capture.md#live-analysis-fta-live)** (`fta live`): real-time analysis of a capture card feed.

Works on **Windows 10/11, macOS and Linux**.
