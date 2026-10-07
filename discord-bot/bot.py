"""Entry point.

Run with:  python bot.py

The bot itself is deliberately thin. All it does is:
  1. open the database,
  2. load every file in `cogs/` as a feature module,
  3. register slash commands with Discord,
  4. log in.

Adding a feature means dropping a new file into `cogs/`. You never edit
this file to do it. That is the whole point of the structure — it's what
lets you sell the same base to twenty customers and bolt on whatever
each one asks for.
"""

from __future__ import annotations

import asyncio
import logging
import pathlib
import traceback

import discord
from discord.ext import commands

from core import config
from core.database import Database


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bot")


class Bot(commands.Bot):
    def __init__(self) -> None:
        # Intents are permissions for *events*. Discord makes you declare
        # which ones you want, and two of these are "privileged" — you
        # must also tick them on the Developer Portal under Bot ->
        # Privileged Gateway Intents, or login fails.
        intents = discord.Intents.default()
        intents.message_content = True   # privileged: needed to read messages for XP
        intents.members = True           # privileged: needed for join/leave events

        super().__init__(
            command_prefix=commands.when_mentioned,  # slash commands are the real UI
            intents=intents,
            help_command=None,
        )

        self.db = Database(config.DATABASE_PATH)

    async def setup_hook(self) -> None:
        """Runs once, after login but before the bot is ready."""
        await self.db.connect()
        log.info("database ready at %s", config.DATABASE_PATH)

        await self._load_cogs()

        # Syncing tells Discord which slash commands exist.
        # Guild-scoped sync is instant; global sync can take up to an hour.
        if config.DEV_GUILD_ID:
            guild = discord.Object(id=config.DEV_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("synced %d commands to dev guild %s", len(synced), config.DEV_GUILD_ID)
        else:
            synced = await self.tree.sync()
            log.info("synced %d commands globally (may take up to 1h to appear)", len(synced))

    async def _load_cogs(self) -> None:
        cogs_dir = pathlib.Path(__file__).parent / "cogs"
        for path in sorted(cogs_dir.glob("*.py")):
            if path.stem.startswith("_"):
                continue
            extension = f"cogs.{path.stem}"
            try:
                await self.load_extension(extension)
                log.info("loaded %s", extension)
            except Exception:
                # One broken cog should never stop the whole bot booting.
                log.error("FAILED to load %s:\n%s", extension, traceback.format_exc())

    async def on_ready(self) -> None:
        log.info("logged in as %s (id %s)", self.user, self.user.id if self.user else "?")
        log.info("serving %d guild(s)", len(self.guilds))
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching, name="/help"
            )
        )

    async def close(self) -> None:
        await self.db.close()
        await super().close()


async def main() -> None:
    token = config.require_token()
    async with Bot() as bot:
        await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("shutting down")
