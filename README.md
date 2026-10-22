# Frametime & Resolution Analyzer (`fta`)

A studio-grade **Video Performance, Frametime, Screen Tearing, and Internal Render Resolution Analyzer** inspired by Digital Foundry's *FPSGui* and *TrDrop*, built for **Elgato 4K S** and UVC capture workflows.

## Key Features

- **Accurate Frametime & Frame-Pacing Engine**:
  - Supports **60, 120, and 240 FPS** (including fractional 59.94 / 119.88 Hz) capture files and live streams.
  - **Tile-Based Luma Differenz ($16 \times 9$ grid)** + **HUD Exclusion Masking** + **Adaptive EMA & Noise-Floor Calibration** prevent false positives during static scenes, 30 FPS cadences, or animated HUD elements.
  - Computes rolling FPS, instantaneous frametime (ms), and **1% / 0.1% Low FPS**.
- **Screen Tearing Detection**:
  - Detects horizontal tear scanlines via temporal row-difference step transitions and horizontal seam anomalies, plotting exact tear Y-coordinates on the HUD and timeline.
- **Hybrid Target vs. Internal Render Resolution Analyzer**:
  - **Active Target Resolution Detector**: Automatically strips letterbox/pillarbox bars to determine the true target output viewport.
  - **Automated Per-Frame DRS Estimator**: Combines normalized 1-pixel **Edge-Spread Function (ESF) Slope** ($\frac{|\nabla_{1\text{px}} I|}{\text{Contrast}_{7\times 7}(I)} \approx \frac{H_{\text{render}}}{H_{\text{target}}}$) with **Scale-Space Re-Upscaling Gradient Retention** to track Dynamic Resolution Scaling (DRS) frame-by-frame.
  - **Interactive Digital Foundry-Style Stair-Step Pixel Counter**: Drag across any diagonal edge in the Studio UI (or click **Auto-Detect Edges**) to count discrete aliasing stair-steps and compute the exact internal render resolution.
- **Studio-Grade Video & Telemetry Exports**:
  - **Burned-In Video (`.mp4`/`.mov`)**: Hardware-accelerated on macOS via Apple Silicon `h264_videotoolbox` with audio passthrough.
  - **Transparent Alpha Overlay (`.mov` ProRes 4444 / `.webm` VP9)**: Drop directly onto an upper timeline track in DaVinci Resolve, Final Cut Pro, or Premiere Pro.
  - **CSV & JSON Telemetry**: Full per-frame metrics and aggregate clip summary.
- **Desktop GUI (Windows / macOS / Linux)**:
  - `fta gui` opens a native Qt (PySide6) app as an alternative to the terminal: live HUD preview, drag-to-place elements, editable labels, platform badge & brand logo, extra info panel, and one-click processing with progress and cancel.
- **Interactive Studio GUI & Live OBS Browser Source**:
  - Launch `fta studio` to scrub frames, inspect Luma Diff & Tear heatmaps, measure pixel stair-steps, or add `http://127.0.0.1:8000/obs-overlay` as a transparent OBS Browser Source over your live **Elgato 4K S** feed.

---

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

For the desktop GUI, install the optional `gui` extra (PySide6, works on Windows, macOS and Linux):
```bash
pip install -e ".[gui]"
```

### 1. Run the Built-In Synthetic Elgato Demo
Generates a synthetic capture clip containing 60 FPS, 30 FPS, frame stutters, screen tearing, and dynamic resolution scaling (100% -> 66.7% -> 50%), and exports the analyzed video, ProRes 4444 alpha overlay, CSV, and JSON:
```bash
fta demo
```

### 2. Analyze an Elgato 4K S Recording
```bash
fta analyze capture.mp4 \
  --platform "PS5" \
  --output-video capture_analyzed.mp4 \
  --output-alpha capture_overlay_alpha.mov \
  --output-csv capture_telemetry.csv \
  --output-json capture_summary.json
```
Supported `--platform` badges: `PS5`, `PS5 Pro`, `PS4`, `PS3`, `PS2`, `PS1`, `Xbox Series X`, `Xbox Series S`, `Xbox One`, `Xbox 360`, `Xbox`, `Switch`, `Switch 2`, `Wii U`, `Wii`, `GameCube`, `N64`, `Steam Deck`, `PC`, `Elgato` (or custom PNG via `--logo`).

### 3. Desktop GUI: Customize the HUD & Process Videos
```bash
fta gui                          # or: fta-gui
fta gui --video capture.mp4 --layout my_layout.json
```
- **Input & Output**: pick the capture video (or drag & drop it onto the window); output names are filled in automatically. Choose any of burned-in video, ProRes/WebM alpha overlay, CSV and JSON.
- **Platform & Logos**: console badge preset (or any custom name), custom badge text, custom badge icon PNG, and a free-standing brand / channel logo with size and opacity.
- **Labels**: rename every HUD label (`FPS`, `1% LOW`, `FT`, status texts, graph titles, resolution captions…), e.g. to translate the HUD.
- **Extra Info**: a titled multi-line info panel (game, patch, graphics mode, capture setup…).
- **Placement**: per element visibility, anchor (9 positions) and X/Y offset, plus global HUD size, panel opacity and section toggles. You can also simply **drag elements in the preview**.
- **Resolution (manual override)**: if the DRS estimate is wrong, set the target output resolution manually and choose the internal render mode: *Auto* (per-frame estimate), *Auto clamped to a known DRS range* (e.g. 1440p–2160p), or *Fixed* (one resolution, no DRS). The manual values are used for the HUD, CSV/JSON and the summary.
- **Process Video** runs the analysis in the background with a progress bar and cancel button.

Layouts are saved as JSON (*File ▸ Save HUD Layout*) and are reusable from the terminal:
```bash
fta analyze capture.mp4 -o capture_analyzed.mp4 --layout my_layout.json --info "Performance Mode" --info "Patch 1.04"
```
Manual resolutions are available from the terminal too:
```bash
fta analyze capture.mp4 -o out.mp4 --target-res 3840x2160 --render-res 2560x1440    # fixed, no DRS
fta analyze capture.mp4 -o out.mp4 --target-res 3840x2160 --render-range 1440-2160  # clamp the DRS estimate
```
Offsets are in 1080p reference pixels and scale with the video resolution, so one layout works for 720p, 1080p and 4K captures.

### 4. Launch the Interactive Analyzer Studio & OBS Overlay Server
```bash
fta studio --video capture.mp4
```
- Open **http://127.0.0.1:8000** for the interactive Frame & Pixel-Counting Studio.
- Add **http://127.0.0.1:8000/obs-overlay** (`1920x1080`) as a **Browser Source** in OBS Studio for a transparent live overlay.

### 5. Live Elgato 4K S / UVC Capture Analysis
```bash
fta devices
fta live --device 0 --width 1920 --height 1080 --fps 60
```
