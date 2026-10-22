"""Keep the documentation in sync with the code."""
from __future__ import annotations

import json
from pathlib import Path
import re

import pytest
import typer.main

from frametime_analyzer.cli.cli import app as cli_app
from frametime_analyzer.render.hud_layout import HUDLayout

DOCS = Path(__file__).resolve().parent.parent / "docs"


def test_layout_examples_in_docs_are_valid() -> None:
    text = (DOCS / "hud-layout.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)```", text, flags=re.S)
    assert len(blocks) >= 2
    for block in blocks:
        layout = HUDLayout.from_dict(json.loads(block))
        assert HUDLayout.from_dict(layout.to_dict()) == layout
    # The documented default layout is the real default
    assert HUDLayout.from_dict(json.loads(blocks[0])) == HUDLayout()


def _command_options() -> list[tuple[str, str]]:
    group = typer.main.get_command(cli_app)
    options = []
    for name, command in group.commands.items():  # type: ignore[attr-defined]
        for param in command.params:
            for opt in [*param.opts, *param.secondary_opts]:
                if opt.startswith("--") and opt != "--help":
                    options.append((name, opt))
    return options


@pytest.mark.parametrize(("command", "option"), _command_options())
def test_every_cli_option_is_documented(command: str, option: str) -> None:
    text = (DOCS / "cli.md").read_text(encoding="utf-8") + (DOCS / "live-capture.md").read_text(encoding="utf-8")
    assert option in text, f"`fta {command} {option}` is missing from docs/cli.md"
