"""File and directory synchronization logic for Folder Mirror."""
from __future__ import annotations

import ctypes
import os
import shutil
import tempfile
from ctypes import wintypes
from pathlib import Path

from fm_config import canonical, paths_overlap, load_config, validate_pairs
from fm_logging import setup_logging

FILE_ATTRIBUTE_REPARSE_POINT = 0x0400


def _is_reparse_point(path: Path) -> bool:
    """Detect symlinks, junctions and other Windows reparse points."""
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if is_junction is not None and is_junction():
            return True
        attributes = path.lstat().st_file_attributes
        return bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)
    except (AttributeError, OSError):
        return False


def assert_no_reparse_points(root: Path) -> None:
    """Fail closed if the destination contains a link/junction.

    This prevents writes and recursive deletes from escaping the selected
    destination through an existing symlink, junction, mount-point or other
    reparse point.
    """
    if not root.exists():
        return
    if _is_reparse_point(root):
        raise RuntimeError(f"Destination is a symbolic link or reparse point: {root}")
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in list(dirs) + list(files):
            candidate = current_path / name
            if _is_reparse_point(candidate):
                raise RuntimeError(
                    "Destination contains a symbolic link, junction, or other "
                    f"reparse point. Remove it before synchronizing: {candidate}"
                )


def _assert_safe_destination_path(destination: Path, target: Path) -> None:
    """Check existing components immediately before operating on a target."""
    try:
        relative = target.relative_to(destination)
    except ValueError as exc:
        raise RuntimeError(f"Target escapes destination: {target}") from exc
    current = destination
    if _is_reparse_point(current):
        raise RuntimeError(f"Destination is a reparse point: {current}")
    for part in relative.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            if _is_reparse_point(current):
                raise RuntimeError(f"Refusing to follow destination reparse point: {current}")


def iter_files(root: Path):
    """Yield relative paths for regular files; do not follow links."""
    if not root.exists():
        return
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirs[:] = [d for d in dirs if not _is_reparse_point(current_path / d)]
        for filename in files:
            full = current_path / filename
            if _is_reparse_point(full) or not full.is_file():
                continue
            yield full.relative_to(root)


def copy_file_atomic(source: Path, destination: Path, destination_root: Path):
    _assert_safe_destination_path(destination_root, destination.parent)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _assert_safe_destination_path(destination_root, destination)
    fd, temp_name = tempfile.mkstemp(prefix=".folder-mirror-", dir=str(destination.parent))
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        shutil.copy2(source, temp_path)
        _assert_safe_destination_path(destination_root, destination)
        os.replace(temp_path, destination)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _send_to_recycle_bin(path: Path) -> None:
    """Move a path to the Windows Recycle Bin using the native Shell API."""
    if os.name != "nt":
        raise RuntimeError("Recycle Bin deletion is supported only on Windows.")

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", wintypes.WORD),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", wintypes.LPVOID),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    # Double-NUL termination is required by SHFileOperationW.
    source_list = str(path) + "\\0\\0"
    operation = SHFILEOPSTRUCTW()
    operation.hwnd = None
    operation.wFunc = 3  # FO_DELETE
    operation.pFrom = source_list
    operation.pTo = None
    operation.fFlags = 0x0040 | 0x0010 | 0x0004 | 0x0400  # undo, quiet, no UI
    operation.fAnyOperationsAborted = False
    operation.hNameMappings = None
    operation.lpszProgressTitle = None
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0 or operation.fAnyOperationsAborted:
        raise OSError(result or "Recycle Bin operation was cancelled",
                      f"Could not move {path} to the Recycle Bin")


def _delete_path(path: Path, deletion_mode: str) -> None:
    if deletion_mode == "recycle_bin":
        _send_to_recycle_bin(path)
    elif deletion_mode == "permanent":
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    else:
        raise ValueError("deletion_mode must be 'recycle_bin' or 'permanent'")


def sync_pair(source_text, destination_text, logger, deletion_mode="recycle_bin", dry_run=False):
    source = canonical(source_text)
    destination = canonical(destination_text)

    if not source.is_dir():
        raise RuntimeError(f"Source folder is unavailable: {source}")
    if paths_overlap(source, destination):
        raise RuntimeError(f"Unsafe source/destination overlap: {source} -> {destination}")
    if deletion_mode not in ("recycle_bin", "permanent"):
        raise ValueError("Invalid deletion mode.")

    # Validate the entire existing destination before making any changes.
    assert_no_reparse_points(destination)
    if destination.exists() and not destination.is_dir():
        raise RuntimeError(f"Destination is not a directory: {destination}")

    source_files = set(iter_files(source))
    destination_files = set(iter_files(destination)) if destination.exists() else set()
    copied = updated = deleted = 0

    source_dirs = set()
    for current, dirs, files in os.walk(source, topdown=True, followlinks=False):
        current_path = Path(current)
        dirs[:] = [d for d in dirs if not _is_reparse_point(current_path / d)]
        for dirname in dirs:
            source_dirs.add((current_path / dirname).relative_to(source))

    files_to_delete = destination_files - source_files
    dirs_to_delete = []
    if destination.exists():
        for current, dirs, files in os.walk(destination, topdown=False, followlinks=False):
            folder = Path(current)
            if folder != destination:
                relative_dir = folder.relative_to(destination)
                if relative_dir not in source_dirs:
                    dirs_to_delete.append(folder)

    # Remove nested directories only once; deleting a parent also removes its
    # children. Files below a directory scheduled for deletion are not separate.
    dirs_to_delete.sort(key=lambda p: len(p.parts))
    top_level_dirs = []
    for folder in dirs_to_delete:
        if not any(parent == folder or parent in folder.parents for parent in top_level_dirs):
            top_level_dirs.append(folder)

    for relative in sorted(files_to_delete, key=lambda p: str(p).lower()):
        target = destination / relative
        if any(parent == target or parent in target.parents for parent in top_level_dirs):
            continue
        _assert_safe_destination_path(destination, target)
        if not dry_run:
            _delete_path(target, deletion_mode)
        deleted += 1
        logger.info("%s destination-only file: %s",
                    "Would delete" if dry_run else "Deleted", target)

    for folder in top_level_dirs:
        _assert_safe_destination_path(destination, folder)
        if not dry_run:
            _delete_path(folder, deletion_mode)
        deleted += 1
        logger.info("%s destination-only directory: %s",
                    "Would delete" if dry_run else "Deleted", folder)

    for relative_dir in sorted(source_dirs, key=lambda p: (len(p.parts), str(p).lower())):
        target_dir = destination / relative_dir
        _assert_safe_destination_path(destination, target_dir)
        if not dry_run:
            if target_dir.exists() and not target_dir.is_dir():
                _delete_path(target_dir, deletion_mode)
            target_dir.mkdir(parents=True, exist_ok=True)

    for relative in sorted(source_files, key=lambda p: str(p).lower()):
        src = source / relative
        dst = destination / relative
        _assert_safe_destination_path(destination, dst)
        if dst.is_dir():
            if not dry_run:
                _delete_path(dst, deletion_mode)
            copied += 1
            if not dry_run:
                copy_file_atomic(src, dst, destination)
        elif not dst.exists():
            copied += 1
            if not dry_run:
                copy_file_atomic(src, dst, destination)
        else:
            s_stat = src.stat()
            d_stat = dst.stat()
            if s_stat.st_size != d_stat.st_size or s_stat.st_mtime_ns != d_stat.st_mtime_ns:
                updated += 1
                if not dry_run:
                    copy_file_atomic(src, dst, destination)

    if not dry_run and not destination.exists():
        destination.mkdir(parents=True, exist_ok=True)

    logger.info(
        "%s synchronized %s -> %s | copied=%d updated=%d deleted=%d%s",
        "Preview:" if dry_run else "Synchronized",
        source, destination, copied, updated, deleted,
        " (dry run; no changes made)" if dry_run else ""
    )
    return copied, updated, deleted


def run_sync(config=None, dry_run=False):
    logger = setup_logging()
    if config is None:
        config = load_config()
    pairs = validate_pairs(config.get("pairs", []))
    deletion_mode = config.get("deletion_mode", "recycle_bin")
    if deletion_mode not in ("recycle_bin", "permanent"):
        raise ValueError("Invalid deletion mode in configuration.")
    if not pairs:
        logger.info("No folder pairs configured.")
        return 0, 0, 0
    totals = [0, 0, 0]
    for pair in pairs:
        result = sync_pair(
            pair["source"], pair["destination"], logger,
            deletion_mode=deletion_mode, dry_run=dry_run
        )
        totals = [a + b for a, b in zip(totals, result)]
    logger.info(
        "%s complete | copied=%d updated=%d deleted=%d",
        "Preview" if dry_run else "Run", *totals
    )
    return tuple(totals)
