"""Frozen-app entry point for the `fta` command-line tool."""
from frametime_analyzer.cli.cli import app

if __name__ == "__main__":
    app(prog_name="fta")
