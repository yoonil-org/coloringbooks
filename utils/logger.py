import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
import config


def setup():
    logger = logging.getLogger("coloring_books")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)

    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    fh = RotatingFileHandler(
        config.LOGS_DIR / "coloring_books.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    logger.addHandler(sh)
    logger.addHandler(fh)
    return logger


def get():
    return logging.getLogger("coloring_books")
