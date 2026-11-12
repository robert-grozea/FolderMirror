#!/usr/bin/env python3
"""Folder Mirror application entry point.

The implementation is split into small modules:
- app_config.py: paths, settings, and validation
- sync.py: recursive mirror operations
- app_logging.py: shared log configuration
- daemon.py: independent background process
- gui.py: Tkinter interface
"""
from __future__ import annotations

import argparse

from app_config import APP_NAME
from daemon import daemon_loop
from sync import run_sync
from gui import FolderMirrorUI
from tkinter import Tk


def main():
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--daemon", action="store_true", help="Run the independent background daemon")
    parser.add_argument("--run-once", action="store_true", help="Run one synchronization cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying files (use with --run-once)")
    args = parser.parse_args()

    if args.daemon:
        raise SystemExit(daemon_loop())
    if args.run_once:
        result = run_sync(dry_run=args.dry_run)
        print(f"Finished. Copied: {result[0]}, updated: {result[1]}, deleted: {result[2]}")
        return

    if args.dry_run:
        parser.error("--dry-run requires --run-once")

    root = Tk()
    FolderMirrorUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
