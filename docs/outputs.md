# Outputs & telemetry

## Burned-in video

The original video with the HUD drawn on top.

- **Format**: H.264 in `.mp4` (or `.mov`), 8-bit 4:2:0, at the source's resolution and frame-rate.
- **Audio**: copied unchanged from the source (no re-encoding).
- **Encoder**: a GPU encoder when one works on your machine, otherwise `libx264` at CRF 18 (visually lossless for most content). See [Platform notes](platforms.md#video-encoding).

!!! warning "Audio formats"
    Because audio is copied, the output container must support the source's audio codec. AAC, the usual format from Elgato, OBS and consoles, works everywhere. If your source has PCM audio (common in `.mov`), write a `.mov` output instead of `.mp4`.

## Transparent overlay

The HUD alone on a transparent background, frame-accurate with the source. Place it on a track above your footage in a video editor.

| Extension | Codec | Works with |
|---|---|---|
| `.mov` (default) | Apple ProRes 4444, 10-bit with alpha | DaVinci Resolve, Final Cut Pro, Premiere Pro, After Effects |
| `.webm` | VP9 with alpha | Browsers, OBS media source, Kdenlive, Shotcut |

ProRes 4444 files are large: often 10 to 30 times the size of the burned-in MP4.

## CSV telemetry

One row per frame of the source video.

| Column | Unit | Meaning |
|---|---|---|
| `frame_index` | | 0-based frame number in the source |
| `timestamp_ms` | ms | Presentation time of the frame |
| `frame_duration_ms` | ms | Time until the next captured frame (e.g. 16.667 at 60 Hz) |
| `is_duplicate` | True/False | The frame repeats the previous one (no new game frame) |
| `is_torn` | True/False | A tear line was detected in this frame |
| `tear_line_y` | px | Tear line positions in source pixels, separated by `;` |
| `frametime_ms` | ms | How long the current game frame has been on screen |
| `rolling_fps` | FPS | Unique frames during the last second |
| `instant_fps` | FPS | `1000 / frametime_ms` |
| `fps_1_percent_low` | FPS | Based on the 99th-percentile frametime so far |
| `fps_0_1_percent_low` | FPS | Based on the 99.9th-percentile frametime so far |
| `mean_luma_diff` | 0–255 | Average brightness change from the previous unique frame |
| `p95_tile_diff` | 0–255 | 95th percentile of the per-tile brightness changes |
| `adaptive_threshold` | 0–255 | Current repeat-detection threshold |
| `container_width`, `container_height` | px | Video file resolution |
| `target_width`, `target_height` | px | Target output resolution (bars removed) |
| `render_width`, `render_height` | px | Estimated (or manual) internal render resolution |
| `render_scale_percent` | % | Render height ÷ target height |
| `resolution_tier_label` | | e.g. `1440p`, or `~1386p` when not near a standard tier |
| `resolution_confidence` | 0–1 | Reliability of the estimate (1.0 for a fixed manual render resolution) |
| `esf_fwhm_px` | px | Measured edge-transition width |
| `spectral_cutoff_ratio` | 0–1 | Detail retained in the scale-space check |

The last three groups are explained in [How the analysis works](how-it-works.md).

## JSON summary

```json
{
  "summary": {
    "source_path": "capture.mp4",
    "total_frames": 180,
    "unique_frames": 145,
    "duplicate_frames": 35,
    "torn_frames": 2,
    "torn_frames_percent": 1.11,
    "duration_seconds": 3.0,
    "container_fps": 60.0,
    "avg_fps": 48.33,
    "min_fps": 30.0,
    "max_fps": 60.0,
    "fps_1_percent_low": 23.4,
    "fps_0_1_percent_low": 15.6,
    "avg_frametime_ms": 23.52,
    "max_frametime_ms": 66.67,
    "p99_frametime_ms": 53.5,
    "frametime_std_ms": 9.75,
    "container_resolution": [1280, 720],
    "target_resolution": [1280, 720],
    "min_render_resolution": [606, 341],
    "max_render_resolution": [1242, 699],
    "median_render_resolution": [740, 416],
    "is_dynamic_resolution": true,
    "avg_resolution_confidence": 0.98
  },
  "frames": [ { "frame_index": 0, "...": "same fields as the CSV" } ]
}
```

- `avg_fps` is unique frames ÷ duration: the true average frame-rate.
- `is_dynamic_resolution` is `true` when the render height varies by 36 px or more over the clip.
- In `frames`, resolutions appear both as pairs (`target_resolution`, `estimated_render_resolution`, `container_resolution`: `[w, h]`) and as the separate `*_width` / `*_height` fields of the CSV, and `tear_line_y` is a list.

## Reading the telemetry

=== "Python (pandas)"

    ```python
    import pandas as pd

    df = pd.read_csv("capture_telemetry.csv")
    print(df["rolling_fps"].describe())
    stutters = df[df["frametime_ms"] > 2 * df["frame_duration_ms"].median()]
    print(f"{len(stutters)} frames above double the refresh interval")
    ```

=== "Spreadsheet"

    Open the CSV in Excel, Numbers, LibreOffice or Google Sheets and chart `timestamp_ms` against `rolling_fps` or `frametime_ms`.
