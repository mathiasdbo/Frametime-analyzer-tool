"""Frozen-app entry point for the desktop GUI."""
import multiprocessing

from frametime_analyzer.gui.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
