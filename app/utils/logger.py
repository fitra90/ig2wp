"""
Simple logging configuration for the IG -> WP Auto-Poster.
"""

import logging
import sys


def get_logger(name: str = "ig2wp") -> logging.Logger:
    """Return a pre-configured logger instance.

    Args:
        name: Logger namespace (default ``ig2wp``).
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(logging.INFO)

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)

        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
