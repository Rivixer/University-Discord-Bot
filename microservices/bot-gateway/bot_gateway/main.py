"""
Main entry point for the bot gateway microservice.
"""

import logging
import sys

import nextcord
from nextcord.ext import commands

from shared.redis_client import RedisManager, RedisSubscriber

from .infrastructure.grpc_server import serve
from .settings import settings

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


logger = logging.getLogger(__name__)

intents = nextcord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    logger.info("Logged in as '%s' (ID: %d)", bot.user.name, bot.user.id)  # type: ignore

    environment = settings.environment.lower()
    if environment not in ["development", "production"]:
        logger.critical(
            "Invalid environment '%s'. Expected 'development' or 'production'. Exiting.",
            environment,
        )
        sys.exit(1)

    if not settings.discord_bot_token:
        logger.critical("DISCORD_BOT_TOKEN is not set. Exiting.")
        sys.exit(1)

    if environment == "development":
        if not settings.test_guild_id:
            logger.warning("No TEST_GUILD_ID set, syncing commands globally instead.")
        else:
            await bot.sync_application_commands(guild_id=settings.test_guild_id)
            logger.info("Synced commands for test guild: %s", settings.test_guild_id)
            return

    await bot.sync_all_application_commands()
    logger.info("Commands synced globally")


def main():
    RedisManager.initialize(settings.redis_url)

    bot.load_extension("bot_gateway.features.guild.cog")
    bot.load_extension("bot_gateway.features.voice_channel.cog")

    bot.loop.create_task(RedisSubscriber.listen(), name="redis-subscriber")
    bot.loop.create_task(serve(bot), name="grpc-server")

    bot.run(settings.discord_bot_token)


if __name__ == "__main__":
    main()
