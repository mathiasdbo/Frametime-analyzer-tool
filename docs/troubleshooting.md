# Troubleshooting & FAQ

## Installation

??? question "`fta: command not found` after installing with pipx"
    pipx installs commands into `~/.local/bin` (macOS / Linux) or `%USERPROFILE%\.local\bin` (Windows). Run `pipx ensurepath`, then open a new terminal.

??? question "The desktop app doesn't start on Linux (`could not load the Qt platform plugin \"xcb\"`)"
    Install Qt's system libraries: `sudo apt install libegl1 libxkbcommon0 libxcb-cursor0 libfontconfig1`. On Wayland you can also try `QT_QPA_PLATFORM=wayland fta gui`.

??? question "`fta gui` says the desktop GUI requires PySide6"
    You installed without the `gui` extra. Reinstall with it: `pipx install --force "frametime-analyzer[gui] @ git+https://github.com/mathiasdbo/Frametime-analyzer-tool.git"`.

??? question "Windows or macOS blocks the downloaded app"
    The app isn't code-signed yet. Windows: **More info → Run anyway**. macOS: right-click → **Open**, or run `xattr -dr com.apple.quarantine "/Applications/Frametime Analyzer.app"`.

## Results

??? question "The FPS is always the capture's refresh rate (e.g. 60), even though the game stutters"
    The analyzer can only see repeated frames that are really in the recording. Check that:

    - the capture isn't re-encoded at a low bitrate (noise can make repeats look different),
    - the game's frame-rate isn't higher than the capture's (a 120 FPS game needs a 120 Hz capture),
    - frame interpolation / motion smoothing is off on the capture path.

??? question "Repeats are detected in static scenes (menus, paused game)"
    When nothing moves, consecutive frames are identical, so the game's real frame-rate can't be measured. Analyze sections with camera or object motion.

??? question "An animated HUD element (minimap, spinner) hides real repeats"
    The tile-based detection ignores motion in a few isolated tiles, but large animated HUD areas can still count as motion. From Python, set `AnalyzerConfig(hud_exclusion_boxes=[(x1, y1, x2, y2)])` with normalized coordinates to ignore them (see [default parameters](how-it-works.md#default-parameters)).

??? question "The render resolution is clearly wrong"
    This is expected with temporal upscalers, sharpening or heavy post-processing. Set it manually: see [Resolution & DRS](resolution.md#manual-override).

??? question "The target resolution is smaller than my capture"
    The analyzer removed what it took for black bars. If the game really has dark edges, set `--target-res` (or *Target output: Manual* in the app).

??? question "Tearing is detected in a V-Sync locked game"
    Scene cuts and very fast flashes can look like tears. Check the frame in the [Studio](live-capture.md#studio-fta-studio) difference view. Use `--no-tearing` if the game can't tear.

## Export

??? question "`ffmpeg (...) failed to write ...`"
    The message includes FFmpeg's own error. Common causes:

    - **PCM audio into an `.mp4`**: write a `.mov` instead, see [Outputs](outputs.md#burned-in-video).
    - **No disk space** or no write permission to the output folder.
    - **A GPU encoder fails mid-way**: retry with `--no-hw` and report the error.

??? question "Export is slow"
    Every frame is analyzed and re-encoded. Make sure a GPU encoder is used (see [Platform notes](platforms.md#video-encoding)). Turn off tearing or resolution analysis if you don't need them, or set a fixed manual resolution, which skips the resolution analysis.

??? question "The overlay `.mov` won't import in my editor"
    ProRes 4444 is supported by DaVinci Resolve, Final Cut Pro, Premiere Pro and After Effects. For browsers, OBS, Kdenlive and Shotcut, export `.webm` instead.

## Capture devices

??? question "`Could not open capture device index 0`"
    - Close every other app using the capture card (OBS, Elgato 4K Capture Utility, Camera Hub, video calls).
    - Run `fta devices` and try another `--device` index.
    - Allow camera access (macOS / Windows privacy settings), or add your user to the `video` group on Linux.

??? question "Live FPS readings are lower than expected"
    Your computer may not keep up with live analysis at this resolution. Record the capture first, then analyze the file. See [Live analysis](live-capture.md#live-analysis-fta-live).

## Still stuck?

[Open an issue](https://github.com/mathiasdbo/Frametime-analyzer-tool/issues/new/choose) with your OS, the output of `fta --version`, the exact command, and the full error message. A short sample clip helps a lot.
