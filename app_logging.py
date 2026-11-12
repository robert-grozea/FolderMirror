"""Centralized file logging shared by the GUI and background daemon."""
import logging

from app_config import LOG_FILE, ensure_app_dir

def setup_logging():
    ensure_app_dir()
    logger = logging.getLogger("folder_mirror")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger
