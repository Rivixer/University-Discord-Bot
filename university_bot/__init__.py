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
from .console import *
from .errors import *
from .models import configs  # type: ignore
from .utils import *

# TODO: Temporary import for backwards compatibility with the old utils module.
from .utils2 import *

__path__ = __import__("pkgutil").extend_path(__path__, __name__)
