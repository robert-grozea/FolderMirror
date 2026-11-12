"""Application paths, configuration persistence, and folder-pair validation.

This module contains no GUI code, so the daemon and command-line modes can
reuse the same configuration rules.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

APP_NAME = "Folder Mirror"
APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "FolderMirror"
CONFIG_FILE = APP_DIR / "config.json"
LOG_FILE = APP_DIR / "folder_mirror.log"
PID_FILE = APP_DIR / "daemon.pid"
LOCK_FILE = APP_DIR / "daemon.lock"
DEFAULT_INTERVAL = 60


def ensure_app_dir():
    APP_DIR.mkdir(parents=True, exist_ok=True)


def load_config():
    ensure_app_dir()
    if not CONFIG_FILE.exists():
        return {"pairs": [], "interval_seconds": DEFAULT_INTERVAL, "deletion_mode": "recycle_bin" if os.name == "nt" else "permanent"}
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Invalid configuration")
        data.setdefault("pairs", [])
        data.setdefault("interval_seconds", DEFAULT_INTERVAL)
        data.setdefault("deletion_mode", "recycle_bin" if os.name == "nt" else "permanent")
        return data
    except Exception as exc:
        raise RuntimeError(f"Could not read configuration {CONFIG_FILE}: {exc}") from exc


def save_config(data):
    ensure_app_dir()
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, CONFIG_FILE)


def canonical(path):
    # Normalize to an absolute path without following symlinks/junctions.
    # Resolving here would hide a destination that is itself a reparse point.
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def paths_overlap(a: Path, b: Path):
    """True if either lexical or resolved paths are equal/nested."""
    pairs = ((a, b), (a.resolve(strict=False), b.resolve(strict=False)))
    for left, right in pairs:
        try:
            left.relative_to(right)
            return True
        except ValueError:
            pass
        try:
            right.relative_to(left)
            return True
        except ValueError:
            pass
    return False

def validate_pairs(pairs):
    cleaned = []
    destinations = []
    for index, pair in enumerate(pairs, 1):
        src = canonical(pair["source"])
        dst = canonical(pair["destination"])
        if not src.exists() or not src.is_dir():
            raise ValueError(f"Pair {index}: source folder does not exist:\n{src}")
        if paths_overlap(src, dst):
            raise ValueError(
                f"Pair {index}: source and destination cannot be the same folder "
                f"or contain one another.\nSource: {src}\nDestination: {dst}"
            )
        for other in destinations:
            if paths_overlap(dst, other):
                raise ValueError(
                    "Two destination folders overlap. Each pair must have its own "
                    f"separate destination.\n{dst}\n{other}"
                )
        destinations.append(dst)
        cleaned.append({"source": str(src), "destination": str(dst)})
    # A destination must not overlap any configured source: otherwise one mirror
    # could modify another pair's input tree.
    sources = [canonical(item["source"]) for item in cleaned]
    for item in cleaned:
        dst = canonical(item["destination"])
        for src in sources:
            if paths_overlap(dst, src):
                raise ValueError(
                    "A destination folder overlaps a configured source folder. "
                    "This can cause one pair to modify another pair's input.\\n"
                    f"Destination: {dst}\\nSource: {src}"
                )
    return cleaned
