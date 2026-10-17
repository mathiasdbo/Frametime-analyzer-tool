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
- **Interactive Studio GUI & Live OBS Browser Source**:
  - Launch `fta studio` to scrub frames, inspect Luma Diff & Tear heatmaps, measure pixel stair-steps, or add `http://127.0.0.1:8000/obs-overlay` as a transparent OBS Browser Source over your live **Elgato 4K S** feed.

---

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
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

### 3. Launch the Interactive Analyzer Studio & OBS Overlay Server
```bash
fta studio --video capture.mp4
```
- Open **http://127.0.0.1:8000** for the interactive Frame & Pixel-Counting Studio.
- Add **http://127.0.0.1:8000/obs-overlay** (`1920x1080`) as a **Browser Source** in OBS Studio for a transparent live overlay.

### 4. Live Elgato 4K S / UVC Capture Analysis
```bash
fta devices
fta live --device 0 --width 1920 --height 1080 --fps 60
```
