# SPDX-License-Identifier: MIT
"""A module for configuring and using the logger."""

import logging
from abc import ABC
from datetime import datetime
from pathlib import Path
from typing import Any, override

from colorama import Fore, Style

from ..models.configs.basic import LoggerConfig

__all__ = ("get_logger",)


class LoggerFormatter(logging.Formatter, ABC):
    """A custom formatter for the logger."""

    LOG_COLORS = {
        "DEBUG": Fore.LIGHTBLACK_EX,
        "INFO": Fore.GREEN,
        "WARNING": Fore.YELLOW + Style.BRIGHT,
        "ERROR": Fore.RED + Style.BRIGHT,
        "CRITICAL": Fore.MAGENTA + Style.BRIGHT,
    }

    SHORT_LEVEL_NAMES = {
        "DEBUG": "DBG",
        "INFO": "INF",
        "WARNING": "WRN",
        "ERROR": "ERR",
        "CRITICAL": "CRT",
    }

    def get_short_levelname(self, record: logging.LogRecord) -> str:
        """Returns the short level name of the log record."""
        return self.SHORT_LEVEL_NAMES.get(record.levelname, record.levelname)

    def get_record_name(self, record: logging.LogRecord) -> str:
        """Returns the module name of the log record."""
        parent_dir_name = Path(__file__).parent.name
        if record.name.startswith(parent_dir_name):
            module_name = record.name.split(".")[-1]
            return "".join(word.capitalize() for word in module_name.split("_"))
        return record.name


class ConsoleLoggerFormatter(LoggerFormatter):
    """A custom formatter for the console logger."""

    config: LoggerConfig

    def __init__(self, fmt: str, datefmt: str, config: LoggerConfig) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.config = config

    @override
    def format(self, record: logging.LogRecord) -> str:
        # pylint: disable=invalid-name
        original_msg = record.msg
        original_levelname = record.levelname
        original_name = record.name
        original_formatException = self.formatException

        try:
            short_levelname = self.get_short_levelname(record)
            log_color = self.LOG_COLORS.get(record.levelname, "")

            if record.levelname in ["ERROR", "CRITICAL", "WARNING"]:
                record.msg = f"{log_color}{record.msg}{Style.RESET_ALL}"

            record.levelname = f"{log_color}{short_levelname:>3}{Style.RESET_ALL}"

            name = self.get_record_name(record)
            record.name = f"{Fore.LIGHTBLACK_EX}{name}{Style.RESET_ALL}"

            self.formatException = self._formatException
            return super().format(record)
        finally:
            record.msg = original_msg
            record.levelname = original_levelname
            record.name = original_name
            self.formatException = original_formatException

    def _formatException(self, ei: Any) -> str:  # pylint: disable=invalid-name
        if not self.config.traceback_in_console:
            return ""
        return super().formatException(ei)


class FileLoggerFormatter(LoggerFormatter):
    """A custom formatter for the file logger."""

    @override
    def format(self, record: logging.LogRecord) -> str:
        original_levelname = record.levelname
        original_name = record.name

        try:
            record.levelname = self.get_short_levelname(record)
            record.name = self.get_record_name(record)
            return super().format(record)
        finally:
            record.levelname = original_levelname
            record.name = original_name


def configure_logger(config: LoggerConfig) -> logging.Logger:
    """Configures the basic logger.

    Parameters
    ----------
    config: :class:`.BasicLoggerConfig`
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
    root_logger.name = __name__.split(".", maxsplit=1)[0]

    console_formatter = ConsoleLoggerFormatter(log_format, date_format, config)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    log_filename = datetime.now().strftime(config.filename_format)
    log_file = config.directory / Path(log_filename)
    file_formatter = FileLoggerFormatter(log_format, date_format)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    return root_logger


def get_logger(name: str, level: int | None = None) -> logging.Logger:
    """Returns a logger with the specified name and level.

    Parameters
    ----------
    name: :class:`str`
        The name of the logger.
    level: :class:`int` | `None`
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
