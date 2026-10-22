# HUD customization

Everything about how the HUD looks is stored in a **HUD layout**: labels, logos, extra info text and the position of each element. You can edit a layout in the [desktop app](gui.md), save it as JSON, and use it with `fta analyze --layout`.

## HUD elements

| Element | Layout key | Default position |
|---|---|---|
| Platform badge (console logo + name) | `platform_badge` | top-right |
| FPS & resolution card | `stats_card` | top-right, under the badge |
| Frametime graph | `frametime_graph` | bottom-left, above the frame-rate graph |
| Frame-rate graph (with tear markers) | `fps_graph` | bottom-left |
| Extra info panel | `extra_info` | top-left (only when it has text) |
| Brand / channel logo | `brand_logo` | bottom-right (only when an image is set) |

Torn frames also get short red **tear-line markers** at the left and right screen edges, at the tear's height. These follow the tear, not the layout, and can be turned off with `show_tear_lines`.

## Anchors and offsets

Each element is positioned by an **anchor** and an **offset**:

```text
top-left        top-center        top-right
middle-left       center          middle-right
bottom-left     bottom-center     bottom-right
```

- The **anchor** chooses which corner, edge or center of the screen the element attaches to.
- The **offset** (`offset_x`, `offset_y`) is a distance **inwards from that edge**:
    - `top-right` with `offset_x: 36, offset_y: 78` means 36 px from the right edge and 78 px from the top.
    - For `bottom-*` anchors, `offset_y` is measured up from the bottom.
    - On a centered axis (`*-center`, `middle-*`, `center`) the offset moves the element right / down from the centered position; negative values move it left / up.

Offsets are in **1080p reference pixels**: they scale with the video's height, so the same layout looks the same at 720p, 1080p, 1440p and 4K. `hud_scale` multiplies everything on top of that.

Elements are always kept fully on screen, even when an offset is too large.

## Layout file format

A layout is a JSON file. This is the default layout:

```json
{
  "platform_name": "PS5",
  "platform_label": "",
  "custom_logo_path": null,
  "brand_logo_path": null,
  "brand_logo_height": 90,
  "brand_logo_opacity": 1.0,
  "extra_info_title": "",
  "extra_info_lines": [],
  "hud_scale": 1.0,
  "panel_opacity": 0.73,
  "show_resolution": true,
  "show_tear_lines": true,
  "labels": {
    "fps_unit": "FPS",
    "one_percent_low": "1% LOW",
    "frametime_short": "FT",
    "status_tearing": "TEARING DETECTED",
    "status_duplicate": "FRAME REPEAT / DROP",
    "status_clean": "UNIQUE FRAME - V-SYNC CLEAN",
    "target_output": "TARGET OUTPUT",
    "est_render": "EST. RENDER",
    "frametime_graph_title": "FRAMETIME (MS)",
    "fps_graph_title": "FRAME-RATE (FPS)"
  },
  "elements": {
    "platform_badge":  { "visible": true, "anchor": "top-right",   "offset_x": 36, "offset_y": 36 },
    "stats_card":      { "visible": true, "anchor": "top-right",   "offset_x": 36, "offset_y": 78 },
    "frametime_graph": { "visible": true, "anchor": "bottom-left", "offset_x": 36, "offset_y": 209 },
    "fps_graph":       { "visible": true, "anchor": "bottom-left", "offset_x": 36, "offset_y": 36 },
    "extra_info":      { "visible": true, "anchor": "top-left",    "offset_x": 36, "offset_y": 36 },
    "brand_logo":      { "visible": true, "anchor": "bottom-right", "offset_x": 36, "offset_y": 36 }
  }
}
```

### Settings

| Key | Type | Meaning |
|---|---|---|
| `platform_name` | text | Console preset for the badge (see [Platform & Logos](gui.md#platform-logos)), or any name for a generic badge |
| `platform_label` | text | Replaces the badge text when not empty |
| `custom_logo_path` | path or `null` | Image replacing the badge's console icon |
| `brand_logo_path` | path or `null` | Free-standing logo image; transparent PNG recommended |
| `brand_logo_height` | number | Logo height in 1080p pixels (width follows the image's aspect ratio) |
| `brand_logo_opacity` | 0 – 1 | Logo opacity |
| `extra_info_title` | text | Highlighted first line of the info panel |
| `extra_info_lines` | list of text | Info panel lines |
| `hud_scale` | 0.25 – 3 | Overall HUD size multiplier |
| `panel_opacity` | 0 – 1 | Opacity of the dark panel backgrounds |
| `show_resolution` | true / false | Show the resolution section of the FPS card |
| `show_tear_lines` | true / false | Show tear-line markers at the screen edges |
| `labels.*` | text | HUD text; see the defaults above |
| `elements.<key>` | object | `visible`, `anchor`, `offset_x`, `offset_y` per element |

### Partial layouts

Any key you leave out keeps its default, so a small file is enough. For example, a Spanish HUD for Switch 2 with the graphs in the bottom-right corner:

```json
{
  "platform_name": "Switch 2",
  "extra_info_title": "Mario Kart World",
  "extra_info_lines": ["Modo portátil", "Capturado con Elgato 4K S"],
  "labels": {
    "one_percent_low": "1% MIN",
    "status_clean": "FRAME UNICO",
    "status_duplicate": "FRAME REPETIDO",
    "status_tearing": "TEARING DETECTADO",
    "fps_graph_title": "FPS"
  },
  "elements": {
    "fps_graph":       { "anchor": "bottom-right" },
    "frametime_graph": { "anchor": "bottom-right" }
  }
}
```

The `ó` in *portátil* isn't ASCII, so it will be drawn as `?`. Write `portatil` instead (see the [note on characters](gui.md#labels)).

!!! tip "Image paths"
    Logo paths are stored as written. Use absolute paths, or paths relative to the folder you run `fta` from, if you share a layout with someone else.

## Command-line overrides

`fta analyze` options take precedence over the layout file:

| Option | Overrides |
|---|---|
| `--platform` | `platform_name` |
| `--logo` | `custom_logo_path` |
| `--info` (repeatable) | `extra_info_lines` |
| `--no-resolution` | hides the resolution section (no estimate) |

## Using layouts from Python

```python
from frametime_analyzer.render import HUDLayout, HUDRenderer

layout = HUDLayout.load("my_layout.json")
layout.labels.fps_unit = "IPS"
layout.elements["stats_card"].anchor = "bottom-right"
layout.save("my_layout_fr.json")

hud = HUDRenderer(layout=layout)
```
