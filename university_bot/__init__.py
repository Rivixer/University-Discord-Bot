"""
University Discord Bot
--------------------

A Discord bot created to support students
in organizing their university lifes.

Features
--------
- role assigment based on reactions
- event management, including reminders
- bot messaging, including embeds
- registering users with the student's email address
- setting bot's status
- management of voice channels
- custom plugins
"""

__title__ = "University-Discord-Bot"
__author__ = "Wiktor Jaworski"
__license__ = "MIT"
__copyright__ = "Copyright 2023-2025 Wiktor Jaworski"
__version__ = "0.9.2"

from . import console, errors, utils
from .university_bot import UniversityBot
