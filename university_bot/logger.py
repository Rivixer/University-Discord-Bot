# SPDX-License-Identifier: MIT
"""A module for configuring and using the logger."""

import logging
from datetime import datetime
from pathlib import Path

from colorama import Fore, Style
from pydantic import BaseModel, Field


class BasicLoggerConfig(BaseModel):
    """A class for the basic configuration of the logger."""

    level: str = Field(
        pattern=r"(?i)^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        default="INFO",
    )
    directory: Path = Field(default=Path("logs"))
    filename_format: str = Field(default="%Y-%m-%d_%H-%M-%S.log")


class LoggerFormatter(logging.Formatter):
    """A custom formatter for the logger."""

    LOG_COLORS = {
        "DEBUG": Fore.LIGHTBLACK_EX,
        "INFO": Fore.GREEN,
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.RED,
        "CRITICAL": Fore.MAGENTA + Style.BRIGHT,
    }

    SHORT_LEVEL_NAMES = {
        "DEBUG": "DBG",
        "INFO": "INF",
        "WARNING": "WRN",
        "ERROR": "ERR",
        "CRITICAL": "CRT",
    }

    def format(self, record: logging.LogRecord) -> str:
        original_levelname = record.levelname
        original_msg = record.msg
        original_name = record.name

        try:
            short_levelname = self.SHORT_LEVEL_NAMES.get(
                record.levelname, record.levelname
            )

            log_color = self.LOG_COLORS.get(record.levelname, "")
            reset_color = Style.RESET_ALL

            if record.levelname in ["ERROR", "CRITICAL", "WARNING"]:
                record.msg = f"{log_color}{record.msg}{reset_color}"

            record.levelname = f"{log_color}{short_levelname:>3}{reset_color}"

            parent_dir_name = Path(__file__).parent.name
            is_cog = record.name.startswith(parent_dir_name)

            if is_cog:
                module_name = record.name.split(".")[-1]
                record.name = "".join(
                    word.capitalize() for word in module_name.split("_")
                )

            record.name = f"{Fore.LIGHTBLACK_EX}{record.name}{reset_color}"

            return super().format(record)

        finally:
            record.levelname = original_levelname
            record.msg = original_msg
            record.name = original_name


def configure_logger(config: BasicLoggerConfig) -> logging.Logger:
    """Configures the basic logger.

    Parameters
    ----------
    config: :class:`BasicLoggerConfig`
        The configuration for the logger.

    Returns
    -------
    :class:`logging.Logger`
        The root logger.
    """
    log_format = "[%(asctime)s | %(levelname)s | %(name)s] %(message)s"
    date_format = "%d.%m.%y %H:%M:%S"

    root_logger = logging.getLogger()
    root_logger.setLevel(config.level.upper())
    root_logger.handlers.clear()

    console_formatter = LoggerFormatter(fmt=log_format, datefmt=date_format)
    file_formatter = logging.Formatter(fmt=log_format, datefmt=date_format)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    log_filename = datetime.now().strftime(config.filename_format)
    log_file = config.directory / Path(log_filename)
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    return root_logger


def get_logger(name: str, level: int | None = None) -> logging.Logger:
    """Returns a logger with the specified name and level.

    Parameters
    ----------
    name: :class:`str`
        The name of the logger.
    level: :class:`int` | :class:`None`
        The level of the logger.
        If `None`, the level is set to default, configured in the root logger.

    Returns
    -------
    :class:`logging.Logger`
        The logger with the specified name and level.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level or logging.getLogger().level)

    if not logger.handlers:
        logger.propagate = True

    return logger
