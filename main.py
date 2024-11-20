# SPDX-License-Identifier: MIT
"""Main module for University Bot."""

import logging

from university_bot import UniversityBot


def main() -> None:
    """Run the bot."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%d.%m.%y %H:%M:%S",
    )
    bot = UniversityBot()
    bot.main()


if __name__ == "__main__":
    main()
