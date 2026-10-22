# Command line

The `fta` command has one subcommand per task. Every command has `--help`:

```bash
fta --help
fta analyze --help
fta --version
```

| Command | What it does |
|---|---|
| [`fta analyze`](#fta-analyze) | Analyze a recorded video and write the HUD video, overlay and telemetry |
| [`fta gui`](#fta-gui) | Open the desktop app |
| [`fta demo`](#fta-demo) | Generate a synthetic test clip and analyze it |
| [`fta devices`](#fta-devices) | List capture devices |
| [`fta live`](#fta-live) | Analyze a capture device in real time |
| [`fta studio`](#fta-studio) | Start the browser Studio and OBS overlay server |

!!! info "Running the downloaded app?"
    `fta` is inside the download: `.\fta.exe` in the Windows folder, `./FrametimeAnalyzer/fta` on Linux, and `"/Applications/Frametime Analyzer.app/Contents/MacOS/fta"` on macOS. See [Installation](installation.md).

## `fta analyze`

```bash
fta analyze VIDEO [OPTIONS]
```

### Outputs

At least one output is needed for the run to produce files; without any, only the summary table is printed.

| Option | Description |
|---|---|
| `-o`, `--output-video PATH` | Burned-in HUD video (`.mp4` / `.mov`) |
| `-a`, `--output-alpha PATH` | Transparent HUD overlay: `.mov` (ProRes 4444) or `.webm` (VP9) |
| `-c`, `--output-csv PATH` | Per-frame CSV telemetry |
| `-j`, `--output-json PATH` | JSON summary plus per-frame data |

### Analysis

| Option | Default | Description |
|---|---|---|
| `--max-frames N` | all | Only process the first N frames |
| `--tearing / --no-tearing` | on | Screen tearing detection |
| `--resolution / --no-resolution` | on | Target and render resolution estimation |
| `--target-res WxH` | auto | Manual target output resolution, e.g. `3840x2160` |
| `--render-res WxH` | auto | Fixed manual internal render resolution, e.g. `2560x1440` |
| `--render-range MIN-MAX` | none | Clamp the per-frame render estimate to a height window, e.g. `1440-2160` |
| `--hw / --no-hw` | on | GPU H.264 encoder when available; `--no-hw` forces `libx264` |

See [Resolution & DRS](resolution.md) for the resolution options.

### HUD

| Option | Description |
|---|---|
| `-l`, `--layout PATH` | HUD layout JSON saved from the desktop app (see [HUD customization](hud-layout.md)) |
| `-p`, `--platform NAME` | Platform badge: `PS5`, `PS5 Pro`, `PS4`, `PS3`, `PS2`, `PS1`, `Xbox Series X`, `Xbox Series S`, `Xbox One`, `Xbox 360`, `Xbox`, `Switch`, `Switch 2`, `Wii U`, `Wii`, `GameCube`, `N64`, `Steam Deck`, `PC`, `Elgato`, or any name. Defaults to the layout's platform (`PS5`) |
| `--logo PATH` | Image replacing the badge's console icon |
| `--info TEXT` | A line for the extra info panel; repeat for more lines |

### Examples

```bash
# Burned-in video only
fta analyze capture.mp4 -o capture_analyzed.mp4 -p "Xbox Series X"

# Everything, with a saved layout
fta analyze capture.mp4 -o out.mp4 -a overlay.mov -c telemetry.csv -j summary.json -l my_layout.json

# Quick test of the first 10 s of a 60 FPS capture
fta analyze capture.mp4 -o test.mp4 --max-frames 600

# Telemetry only, no video encoding
fta analyze capture.mp4 -c telemetry.csv -j summary.json

# Batch: every MP4 in a folder (macOS / Linux)
for f in captures/*.mp4; do fta analyze "$f" -o "${f%.mp4}_analyzed.mp4" -l my_layout.json; done
```

```powershell
# Batch on Windows (PowerShell)
Get-ChildItem captures\*.mp4 | ForEach-Object {
  fta analyze $_.FullName -o ($_.FullName -replace '\.mp4$', '_analyzed.mp4') -l my_layout.json
}
```

## `fta gui`

```bash
fta gui [--video PATH] [--layout PATH]
```

Opens the [desktop app](gui.md), optionally with a video and a HUD layout already loaded. `fta-gui [VIDEO] [--layout PATH]` does the same.

## `fta demo`

```bash
fta demo [--output-dir DIR] [--platform NAME]
```

Generates a 3-second 720p60 synthetic clip with 60 / 30 FPS sections, stutters, tearing and dynamic resolution, then analyzes it into `DIR` (default `demo_output`). See [Quick start](quick-start.md#1-try-the-built-in-demo).

## `fta devices`

Lists capture devices with their index, default resolution and frame-rate. See [Live capture](live-capture.md).

## `fta live`

```bash
fta live [--device N] [--width W] [--height H] [--fps F] [--platform NAME] [--record PATH]
```

Analyzes a capture device in real time in a preview window; press ++q++ to stop. See [Live analysis](live-capture.md#live-analysis-fta-live).

## `fta studio`

```bash
fta studio [--video PATH] [--host HOST] [--port PORT] [--max-frames N] [--open | --no-open]
```

Starts the browser Studio at `http://HOST:PORT` and the OBS overlay at `/obs-overlay`. See [Studio](live-capture.md#studio-fta-studio).

## Environment variables

| Variable | Effect |
|---|---|
| `FTA_VIDEO_ENCODER` | Force an H.264 encoder: `libx264`, `h264_nvenc`, `h264_qsv`, `h264_amf`, `h264_vaapi`, `h264_videotoolbox`, or another FFmpeg encoder name |
| `QT_QPA_PLATFORM=offscreen` | Run the desktop app without a display (testing) |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Processing error, e.g. a file that isn't a readable video, or an FFmpeg failure |
| `2` | Invalid usage: missing input file, malformed `--target-res`, `--render-res` together with `--render-range`, … |
