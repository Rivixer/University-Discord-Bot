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

from .bot import *
from .config import *
from .console import *  # TODO: To be removed in the future.
from .errors import *  # TODO: To be removed in the future. Maybe.
from .models import *
from .types import *
from .utils import *
from .utils2 import *  # TODO: Temporary import for backwards compatibility with the old utils module.

__path__ = __import__("pkgutil").extend_path(__path__, __name__)
