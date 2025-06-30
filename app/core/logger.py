__all__ = [
    "logger",
]

import sys

from loguru import logger

from .config import config

# Logger setup
logger.remove()

# Console logging
logger.add(
    sys.stderr,
    level=config.LOG_STDOUT_LEVEL,
    format="<white>{time: %d.%m %H:%M:%S}</white>|<level>{level}</level>|<bold>{message}</bold>",
)

# File logging
logger.add(
    sink=config.LOG_FOLDER_PATH / "app.log",  # Path for log file
    format=(
        "<white>{time: %d.%m %H:%M:%S.%f}</white> | "
        "<level>{level}</level>| "
        "{name} {function} line:{line}| "
        "<bold>{message}</bold>"
    ),
    retention="1 week",
    rotation="10 MB",
    compression="zip",
    encoding="utf-8",
    enqueue=False,
)
