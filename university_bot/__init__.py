"""
University Discord Bot
~~~~~~~~~~~~~~~~~~~~~~

A Discord bot created to support students
in organizing their university lifes.

Features
--------
- role assigment based on reactions
- event management, including reminders
- bot messaging, including embeds
- registering users with the student's email address
- setting bot's presence
- management of voice channels
- custom plugins
"""

__title__ = "University-Discord-Bot"
__author__ = "Wiktor Jaworski"
__license__ = "MIT"
__copyright__ = "Copyright 2023-2025 Wiktor Jaworski"
__version__ = "1.0.0.alpha"

# pyright: reportUnusedImport=false

from .bot import *
from .console import *  # TODO: To be removed in the future.
from .errors import *  # TODO: To be removed in the future. Maybe.
from .exceptions.configuration import *
from .models import *
from .types import *
from .utils2 import *  # TODO: Temporary import for backwards compatibility with the old utils module.
from .utils.exceptions import *
from .utils.fetches import *
from .utils.interactions import *
from .utils.localization import Localization
from .utils.logger import PhraseFilter, get_logger

__path__ = __import__("pkgutil").extend_path(__path__, __name__)
