# Releasing Frametime Analyzer

Releases are built by [`.github/workflows/release.yml`](../.github/workflows/release.yml). A version tag (`v*`) produces:

| Artifact | Built on | For |
|---|---|---|
| `FrametimeAnalyzer-<ver>-windows-x64.zip` | `windows-latest` | Windows 10/11, no Python needed |
| `FrametimeAnalyzer-<ver>-macos-arm64.zip` | `macos-latest` | Apple Silicon Macs, no Python needed |
| `FrametimeAnalyzer-<ver>-linux-x86_64.tar.gz` | `ubuntu-22.04` | Linux with glibc 2.35 or newer, no Python needed |
| `frametime_analyzer-<ver>.tar.gz` / `-py3-none-any.whl` | `ubuntu-latest` | `pipx` / `uv` / `pip` |

Every standalone build is smoke-tested before upload: `fta --version`, a full `fta demo` encode, and a headless start of the GUI.

## Cutting a release

1. Bump `__version__` in `src/frametime_analyzer/__init__.py` (the only place the version lives) and merge to `main`.
2. Tag the merge commit and push the tag:
   ```bash
   git checkout main && git pull
   git tag v0.2.0
   git push origin v0.2.0
   ```
3. Watch the **Release** workflow in the *Actions* tab. When it is green, the GitHub Release with all files and auto-generated notes is live at
   `https://github.com/mathiasdbo/Frametime-analyzer-tool/releases`.

The workflow fails early if the tag does not match `__version__`.

To try the builds without publishing anything, open *Actions → Release → Run workflow*: the files appear as downloadable artifacts on the run page.

## One-time setup: publishing to PyPI (optional)

The `pypi` job stays off until you enable it. It uses PyPI *trusted publishing*, so no API token is stored in GitHub.

1. On <https://pypi.org/manage/account/publishing/>, add a **pending publisher**:
   - PyPI project name: `frametime-analyzer`
   - Owner: `mathiasdbo`, repository: `Frametime-analyzer-tool`
   - Workflow name: `release.yml`, environment name: `pypi`
2. In the GitHub repository: *Settings → Environments → New environment* named `pypi`.
3. *Settings → Secrets and variables → Actions → Variables*: add `PUBLISH_TO_PYPI` = `true`.

The next tag then also uploads the sdist and wheel, and users can run `pipx install "frametime-analyzer[gui]"`.

## Building the standalone app locally

```bash
pip install -e ".[gui]" pyinstaller
pyinstaller packaging/frametime_analyzer.spec --noconfirm
# Output: dist/FrametimeAnalyzer/ (Windows, Linux) or "dist/Frametime Analyzer.app" (macOS)
```

PyInstaller does not cross-compile: build each OS on that OS (which is what the workflow does).

## Possible next steps

- **Code signing**: an Apple Developer ID plus notarization, and a Windows code-signing certificate. This removes the Gatekeeper / SmartScreen warnings.
- **Intel Mac build**: add an Intel macOS runner to the `standalone` matrix if Intel Macs need a download (they can already use `pipx`).
- **Package managers**: a Homebrew tap, a `winget` / Scoop manifest, or Flathub / AUR, all pointing at the release files.
