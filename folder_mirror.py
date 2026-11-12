#!/usr/bin/env python3
"""Folder Mirror application entry point.

The implementation is split into small modules:
- fm_config.py: paths, settings, and validation
- fm_sync.py: recursive mirror operations
- fm_logging.py: shared log configuration
- fm_daemon.py: independent background process
- fm_gui.py: Tkinter interface
"""
from __future__ import annotations

import argparse

from fm_config import APP_NAME
from fm_daemon import daemon_loop
from fm_sync import run_sync
from fm_gui import FolderMirrorUI
from tkinter import Tk


def main():
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--daemon", action="store_true", help="Run the independent background daemon")
    parser.add_argument("--run-once", action="store_true", help="Run one synchronization cycle and exit")
    args = parser.parse_args()

    if args.daemon:
        raise SystemExit(daemon_loop())
    if args.run_once:
        result = run_sync()
        print(f"Finished. Copied: {result[0]}, updated: {result[1]}, deleted: {result[2]}")
        return

    root = Tk()
    FolderMirrorUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
