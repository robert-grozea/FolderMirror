"""Independent background synchronization daemon and process locking."""
from __future__ import annotations

import os
import time

from fm_config import (
    DEFAULT_INTERVAL, LOCK_FILE, PID_FILE, ensure_app_dir, load_config,
)
from fm_logging import setup_logging
from fm_sync import run_sync

def pid_is_running(pid):
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_daemon_lock():
    """Windows byte-range lock prevents two daemon instances."""
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
