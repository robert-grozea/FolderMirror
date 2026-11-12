"""File and directory synchronization logic for Folder Mirror."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from fm_config import canonical, paths_overlap, load_config, validate_pairs
from fm_logging import setup_logging

def iter_files(root: Path):
    """Yield relative paths for regular files; do not follow directory symlinks."""
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirs[:] = [d for d in dirs if not (current_path / d).is_symlink()]
        for filename in files:
            full = current_path / filename
            if full.is_symlink() or not full.is_file():
                continue
            yield full.relative_to(root)


def copy_file_atomic(source: Path, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Copy to a temporary file in the destination directory, then replace.
    fd, temp_name = tempfile.mkstemp(prefix=".folder-mirror-", dir=str(destination.parent))
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        shutil.copy2(source, temp_path)
        os.replace(temp_path, destination)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def sync_pair(source_text, destination_text, logger):
    source = canonical(source_text)
    destination = canonical(destination_text)

    if not source.is_dir():
        raise RuntimeError(f"Source folder is unavailable: {source}")
    if paths_overlap(source, destination):
        raise RuntimeError(f"Unsafe source/destination overlap: {source} -> {destination}")

    destination.mkdir(parents=True, exist_ok=True)
    source_files = set(iter_files(source))
    copied = updated = deleted = 0

    # Collect every source directory, including empty directories.
    source_dirs = set()
    for current, dirs, files in os.walk(source, topdown=True, followlinks=False):
        current_path = Path(current)
        dirs[:] = [d for d in dirs if not (current_path / d).is_symlink()]
        for dirname in dirs:
            source_dirs.add((current_path / dirname).relative_to(source))

    # Remove destination files absent from source.
    destination_files = set(iter_files(destination))
    for relative in sorted(destination_files - source_files, key=lambda p: str(p).lower()):
        target = destination / relative
        try:
            target.unlink()
            deleted += 1
            logger.info("Deleted destination-only file: %s", target)
        except OSError as exc:
            logger.exception("Could not delete %s: %s", target, exc)
            raise

    # Remove destination-only directories, including their contents.
    for current, dirs, files in os.walk(destination, topdown=False, followlinks=False):
        folder = Path(current)
        if folder == destination:
            continue
        relative_dir = folder.relative_to(destination)
        if relative_dir not in source_dirs:
            try:
                shutil.rmtree(folder)
                logger.info("Deleted destination-only directory: %s", folder)
            except OSError as exc:
                logger.exception("Could not remove directory %s: %s", folder, exc)
                raise

    # Create every source directory, including newly-created empty folders.
    for relative_dir in sorted(source_dirs, key=lambda p: (len(p.parts), str(p).lower())):
        target_dir = destination / relative_dir
        if target_dir.exists() and not target_dir.is_dir():
            target_dir.unlink()
        target_dir.mkdir(parents=True, exist_ok=True)

    # Copy new files and update changed files.
    for relative in sorted(source_files, key=lambda p: str(p).lower()):
        src = source / relative
        dst = destination / relative
        try:
            if dst.is_dir():
                shutil.rmtree(dst)
            if not dst.exists() or not dst.is_file():
                copy_file_atomic(src, dst)
                copied += 1
            else:
                s_stat = src.stat()
                d_stat = dst.stat()
                if s_stat.st_size != d_stat.st_size or s_stat.st_mtime_ns != d_stat.st_mtime_ns:
                    copy_file_atomic(src, dst)
                    updated += 1
        except OSError as exc:
            logger.exception("Could not copy %s -> %s: %s", src, dst, exc)
            raise

    logger.info(
        "Synchronized %s -> %s | copied=%d updated=%d deleted=%d",
        source, destination, copied, updated, deleted
    )
    return copied, updated, deleted
def run_sync(config=None):
    logger = setup_logging()
    if config is None:
        config = load_config()
    pairs = validate_pairs(config.get("pairs", []))
    if not pairs:
        logger.info("No folder pairs configured.")
        return 0, 0, 0
    totals = [0, 0, 0]
    for pair in pairs:
        result = sync_pair(pair["source"], pair["destination"], logger)
        totals = [a + b for a, b in zip(totals, result)]
    logger.info("Run complete | copied=%d updated=%d deleted=%d", *totals)
    return tuple(totals)
