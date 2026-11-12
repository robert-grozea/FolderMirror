"""Independent background synchronization daemon and process locking."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from app_config import (
    DEFAULT_INTERVAL, LOCK_FILE, PID_FILE, ensure_app_dir, load_config,
)
from app_logging import setup_logging
from sync import run_sync


def pid_is_running(pid):
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False



def daemon_lock_is_held():
    """Return True when another process owns the daemon lock."""
    ensure_app_dir()
    handle = open(LOCK_FILE, "a+b")
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                return True
            else:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                return False
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return True
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                return False
    finally:
        handle.close()


def is_folder_mirror_daemon(pid):
    """Confirm PID belongs to this Python executable running our daemon entry point."""
    if not pid_is_running(pid):
        return False
    if os.name == "nt":
        # Query CIM using an environment variable, not interpolated user input.
        env = os.environ.copy()
        env["FM_CHECK_PID"] = str(int(pid))
        command = (
            '$p = Get-CimInstance Win32_Process -Filter "ProcessId=$env:FM_CHECK_PID"; '
            'if ($p) { $p | Select-Object ExecutablePath,CommandLine | ConvertTo-Json -Compress }'
        )
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True, text=True, timeout=5, env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0 or not result.stdout.strip():
                return False
            process = json.loads(result.stdout)
            expected_exe = os.path.normcase(os.path.realpath(sys.executable))
            actual_exe = os.path.normcase(os.path.realpath(process.get("ExecutablePath") or ""))
            expected_script = os.path.normcase(
                str(Path(__file__).resolve().with_name("folder_mirror.py"))
            )
            command_line = (process.get("CommandLine") or "").lower()
            return (
                actual_exe == expected_exe
                and expected_script.lower() in command_line
                and "--daemon" in command_line
            )
        except (OSError, ValueError, subprocess.SubprocessError, TypeError):
            return False

    # On POSIX, inspect the process command line rather than trusting a recycled PID.
    try:
        command_line = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\\0", b" ").decode(
            errors="replace"
        )
        expected_script = str(Path(__file__).resolve().with_name("folder_mirror.py"))
        return expected_script in command_line and "--daemon" in command_line
    except OSError:
        return False


def acquire_daemon_lock():
    """OS-level byte-range lock prevents two daemon instances."""
    ensure_app_dir()
    handle = open(LOCK_FILE, "a+b")
    handle.seek(0)
    if os.name == "nt":
        import msvcrt
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            handle.close()
            return None
    else:
        try:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return None
    return handle


def daemon_loop():
    logger = setup_logging()
    lock_handle = acquire_daemon_lock()
    if lock_handle is None:
        logger.warning("Daemon is already running; exiting.")
        return 2

    PID_FILE.write_text(str(os.getpid()), encoding="ascii")
    logger.info("Daemon started (PID %s).", os.getpid())
    try:
        while True:
            try:
                config = load_config()
                interval = max(10, int(config.get("interval_seconds", DEFAULT_INTERVAL)))
                run_sync(config)
            except Exception:
                logger.exception("Synchronization cycle failed.")
                interval = DEFAULT_INTERVAL
            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("Daemon interrupted.")
    finally:
        try:
            if PID_FILE.exists() and PID_FILE.read_text(encoding="ascii").strip() == str(os.getpid()):
                PID_FILE.unlink()
        except OSError:
            pass
        logger.info("Daemon stopped.")
        lock_handle.close()
    return 0
