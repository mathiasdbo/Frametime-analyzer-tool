# Live capture, Studio & OBS

Besides processing recorded files, Frametime Analyzer can analyze a capture card feed in real time, and includes a browser-based **Studio** for frame-by-frame inspection plus a transparent **OBS overlay**.

## Find your capture device

```bash
fta devices
```

This lists connected video devices (Elgato 4K S, other UVC capture cards, webcams) with their index, default resolution and frame-rate:

```text
       Detected Capture Devices
┏━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Index ┃ Default Resolution ┃ Default FPS ┃
┡━━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ 0     │ 1920x1080          │ 60.0        │
└───────┴────────────────────┴─────────────┘
```

!!! warning "Only one app can use a capture device at a time"
    Close OBS, the Elgato 4K Capture Utility, Camera Hub or any video-call app before starting live analysis.

## Live analysis (`fta live`)

```bash
fta live --device 0 --width 1920 --height 1080 --fps 60 --platform "PS5"
```

A preview window shows the feed with the HUD. Press ++q++ in the window to stop.

Add `--record analyzed_live.mp4` to save the analyzed feed to a file.

| Option | Default | Meaning |
|---|---|---|
| `--device`, `-d` | `0` | Device index from `fta devices` |
| `--width`, `--height` | `1920`, `1080` | Requested capture size |
| `--fps` | `60` | Requested capture frame-rate |
| `--platform`, `-p` | `PS5` | Platform badge |
| `--record`, `-r` | none | Optional file to record the analyzed video |

The device may not support the size or frame-rate you ask for; the actual values are printed when capture starts.

!!! note "Live vs. recorded analysis"
    Live analysis is limited by your computer's speed. If it can't keep up, frames are skipped, which shows up as lower measured FPS. For accurate numbers, record the capture first (Elgato 4K Capture Utility, OBS) and analyze the file with `fta analyze` or the desktop app.

## Studio (`fta studio`)

The Studio is a local web app for inspecting captures frame by frame:

```bash
fta studio --video capture.mp4
```

It opens <http://127.0.0.1:8000> in your browser, loads the video, and continues analyzing the rest of the frames in the background. In the Studio you can:

- **Scrub** through the video and view each frame raw, with the HUD overlay, or as a **difference map** against the previous frame (useful for spotting repeated and torn frames).
- See the frame-rate, frametime and resolution **timeline** for the clip.
- **Count pixels**: drag across a clean diagonal edge to count its aliasing stair-steps and compute the internal render resolution, or click **Auto-Detect Edges** for suggested edges. See [Resolution & DRS](resolution.md#interactive-pixel-counting).
- **Load** another video, or **Load Synthetic Demo** to try it out.
- **Export** the burned-in MP4, alpha overlay and CSV into an `fta_exports/` folder next to the video.

| Option | Default | Meaning |
|---|---|---|
| `--video`, `-v` | none | Video to open at startup |
| `--host` | `127.0.0.1` | Address to listen on |
| `--port`, `-p` | `8000` | Port |
| `--max-frames` | all | Limit the number of frames analyzed |
| `--open / --no-open` | open | Open the browser automatically |

!!! danger "Keep the Studio local"
    The Studio server can read video files from your disk and has no login. Keep the default `--host 127.0.0.1` unless you're on a trusted network.

## OBS overlay

While `fta studio` is running, it also serves a transparent HUD page for OBS Studio:

1. In OBS, add a **Browser** source.
2. URL: `http://127.0.0.1:8000/obs-overlay`
3. Width `1920`, height `1080`.
4. Place it above your video source.

!!! info "What the overlay shows"
    The overlay **plays back the analysis of the video loaded in the Studio**, in a loop at 60 frames per second (or demo data if nothing is loaded). It doesn't measure what OBS is currently showing. To show measurements of a recording in OBS, load that recording in the Studio and play the same recording in OBS.

    For a live measurement of a capture card, use [`fta live`](#live-analysis-fta-live). For a finished video, the [burned-in video or transparent overlay](outputs.md) is frame-accurate.
