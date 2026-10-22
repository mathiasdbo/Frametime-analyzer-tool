# Installation

Frametime Analyzer runs on **Windows 10/11, macOS and Linux**. Choose one of three ways to install it:

| | Best for | Needs Python |
|---|---|---|
| [Download the app](#option-1-download-the-app) | Most people | No |
| [pipx / uv](#option-2-pipx-or-uv) | Python users, command-line work | Yes (3.9+) |
| [From source](#option-3-from-source) | Development | Yes (3.9+) |

You don't need to install FFmpeg separately: every option includes one, and an FFmpeg already on your `PATH` is used if you have it.

## Option 1: Download the app

Get the file for your system from the [**Releases page**](https://github.com/mathiasdbo/Frametime-analyzer-tool/releases/latest).

=== "Windows"

    1. Download `FrametimeAnalyzer-<version>-windows-x64.zip`.
    2. Right-click it → **Extract All…**
    3. Open the extracted `FrametimeAnalyzer` folder and double-click **`FrametimeAnalyzer.exe`**.

    The first time, SmartScreen may say *"Windows protected your PC"* because the app isn't code-signed yet. Click **More info → Run anyway**.

    The command-line tool is in the same folder:
    ```powershell
    cd $HOME\Downloads\FrametimeAnalyzer
    .\fta.exe --version
    .\fta.exe analyze capture.mp4 -o capture_analyzed.mp4
    ```

=== "macOS"

    1. Download `FrametimeAnalyzer-<version>-macos-arm64.zip` (Apple Silicon: M1 or newer).
    2. Double-click the zip, then drag **Frametime Analyzer.app** into *Applications*.
    3. The first time, **right-click the app → Open → Open** (the app isn't notarized yet).

    If macOS reports the app as *damaged*, remove the download quarantine once:
    ```bash
    xattr -dr com.apple.quarantine "/Applications/Frametime Analyzer.app"
    ```

    The command-line tool is inside the app:
    ```bash
    "/Applications/Frametime Analyzer.app/Contents/MacOS/fta" --version
    # Optional: make `fta` available everywhere
    sudo ln -s "/Applications/Frametime Analyzer.app/Contents/MacOS/fta" /usr/local/bin/fta
    ```

    !!! note "Intel Macs"
        There's no Intel download yet. Use [Option 2](#option-2-pipx-or-uv) instead.

=== "Linux"

    1. Download `FrametimeAnalyzer-<version>-linux-x86_64.tar.gz` (glibc 2.35+: Ubuntu 22.04, Debian 12, Fedora 36 or newer).
    2. Extract and run:
    ```bash
    tar -xzf FrametimeAnalyzer-*-linux-x86_64.tar.gz
    ./FrametimeAnalyzer/FrametimeAnalyzer        # desktop app
    ./FrametimeAnalyzer/fta --version            # command line
    ```

    On minimal installs, Qt may need a few system libraries:
    ```bash
    sudo apt install libegl1 libxkbcommon0 libxcb-cursor0 libfontconfig1
    ```

## Option 2: pipx or uv

This installs the `fta` and `fta-gui` commands into their own isolated environment, so they don't affect your other Python packages.

1. Install [pipx](https://pipx.pypa.io/stable/installation/) or [uv](https://docs.astral.sh/uv/getting-started/installation/).
2. Install Frametime Analyzer:

    === "pipx"

        ```bash
        # Latest version from GitHub
        pipx install "frametime-analyzer[gui] @ git+https://github.com/mathiasdbo/Frametime-analyzer-tool.git"

        # Once it's published on PyPI
        pipx install "frametime-analyzer[gui]"
        ```

    === "uv"

        ```bash
        uv tool install "frametime-analyzer[gui] @ git+https://github.com/mathiasdbo/Frametime-analyzer-tool.git"
        ```

3. Check it works:
    ```bash
    fta --version
    fta-gui            # opens the desktop app
    ```

Leave out `[gui]` for a command-line-only install (no Qt). To update later, run `pipx upgrade frametime-analyzer` or `uv tool upgrade frametime-analyzer`.

## Option 3: From source

=== "macOS / Linux"

    ```bash
    git clone https://github.com/mathiasdbo/Frametime-analyzer-tool.git
    cd Frametime-analyzer-tool
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev,gui]"
    ```

=== "Windows (PowerShell)"

    ```powershell
    git clone https://github.com/mathiasdbo/Frametime-analyzer-tool.git
    cd Frametime-analyzer-tool
    py -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -e ".[dev,gui]"
    ```

Run the tests with `python -m pytest`. See [Contributing](contributing.md) for more.

## Uninstall

- **Downloaded app**: delete the `FrametimeAnalyzer` folder (Windows, Linux) or the app from *Applications* (macOS).
- **pipx / uv**: `pipx uninstall frametime-analyzer` or `uv tool uninstall frametime-analyzer`.

The desktop app also remembers your last HUD layout in the standard per-user settings location (the registry on Windows, `~/Library/Preferences` on macOS, `~/.config` on Linux) under *FrametimeAnalyzer / Studio*.
