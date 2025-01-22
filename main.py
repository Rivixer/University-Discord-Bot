# SPDX-License-Identifier: MIT
"""Main module for University Bot."""

from university_bot.bot import UniversityBot


def main() -> None:
    """Runs the bot."""
    bot = UniversityBot()
    bot.main()


if __name__ == "__main__":
    main()
