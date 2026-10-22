# Contributing

Thanks for helping improve Frametime Analyzer! Bug reports, sample captures that trip up the analysis, documentation fixes and code are all welcome.

## Reporting bugs and requesting features

Use the [issue forms](https://github.com/mathiasdbo/Frametime-analyzer-tool/issues/new/choose). For analysis problems (wrong FPS, missed tearing, wrong resolution), a short sample clip and the expected result help the most.

## Development setup

```bash
git clone https://github.com/mathiasdbo/Frametime-analyzer-tool.git
cd Frametime-analyzer-tool
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev,gui]"
```

Python 3.9 is the minimum supported version, so avoid newer-only syntax (e.g. `match`, or `X | Y` types outside annotations).

## Running the checks

```bash
python -m pytest -q                      # all tests, including a headless GUI test
fta demo                                 # end-to-end smoke test
ruff check --select F,E9,B --ignore B008 src tests
```

On a machine without a display, run the GUI test with `QT_QPA_PLATFORM=offscreen`. CI runs the tests on Windows, macOS and Linux with Python 3.9 and 3.12 for every push.

## Project layout

| Path | Contents |
|---|---|
| `src/frametime_analyzer/core/` | Detectors (frametime, tearing, resolution), resolution override, pipeline |
| `src/frametime_analyzer/ingest/` | Video file and live capture readers |
| `src/frametime_analyzer/render/` | HUD layout model, HUD renderer, platform badges, video / telemetry exporters |
| `src/frametime_analyzer/processing.py` | The offline processing job shared by the CLI and the GUI |
| `src/frametime_analyzer/gui/` | PySide6 desktop app |
| `src/frametime_analyzer/cli/` | `fta` command line (Typer) |
| `src/frametime_analyzer/ui/` | Browser Studio and OBS overlay (FastAPI) |
| `packaging/` | PyInstaller spec for the standalone apps |
| `docs/` | Documentation site (MkDocs Material) |
| `tests/` | pytest suite |

## Documentation

The documentation site is built from `docs/` with [MkDocs Material](https://squidfunk.github.io/mkdocs-material/) and published to GitHub Pages from `main`.

```bash
pip install -r docs/requirements.txt
mkdocs serve          # live preview at http://127.0.0.1:8000
mkdocs build --strict # what CI runs
```

When you change a command-line option, a HUD layout field or an output column, update the matching page (`docs/cli.md`, `docs/hud-layout.md`, `docs/outputs.md`).

## Pull requests

1. Create a branch from `main`.
2. Keep changes focused, and add or update tests for behaviour changes.
3. Update the docs and add a line under **Unreleased** in `CHANGELOG.md`.
4. Make sure `pytest` passes and open the pull request. The template has a short checklist.

## Releases

Maintainers: see the [release guide](https://mathiasdbo.github.io/Frametime-analyzer-tool/releasing/) ([`docs/releasing.md`](https://github.com/mathiasdbo/Frametime-analyzer-tool/blob/main/docs/releasing.md)).
