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
        intents = discord.Intents.default()
        # Both are privileged and must also be enabled in the Developer Portal.
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
        )

        self.db = Database(config.DATABASE_PATH)

    async def setup_hook(self) -> None:
        await self.db.connect()
        log.info("database ready at %s", config.DATABASE_PATH)

        await self._load_cogs()
        self._register_persistent_views()
        await self._sync_commands()

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
                # A broken cog shouldn't stop the rest of the bot booting.
                log.error("FAILED to load %s:\n%s", extension, traceback.format_exc())

    def _register_persistent_views(self) -> None:
        # Discord only stores a button's custom_id, not its callback. Without
        # re-registering here, every panel posted before a restart goes dead.
        from cogs.tickets import TicketPanelView, TicketCloseView
        from cogs.rolemenu import RoleButton

        self.add_view(TicketPanelView())
        self.add_view(TicketCloseView())
        self.add_dynamic_items(RoleButton)
        log.info("persistent views registered")

    async def _sync_commands(self) -> None:
        # Guild sync is instant; global sync can take up to an hour.
        if config.DEV_GUILD_ID:
            guild = discord.Object(id=config.DEV_GUILD_ID)
            try:
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                log.info(
                    "synced %d commands to dev guild %s",
                    len(synced), config.DEV_GUILD_ID,
                )
                return
            except discord.Forbidden:
                log.error(
                    "Can't sync to server %s - bot isn't in it, or was invited "
                    "without the 'applications.commands' scope.",
                    config.DEV_GUILD_ID,
                )
                log.error(
                    "Re-invite with:\nhttps://discord.com/api/oauth2/authorize"
                    "?client_id=%s&permissions=1099780156422"
                    "&scope=bot%%20applications.commands",
                    self.application_id,
                )
                log.warning("Falling back to global sync.")

        synced = await self.tree.sync()
        log.info("synced %d commands globally (up to 1h to appear)", len(synced))

    async def on_ready(self) -> None:
        log.info("logged in as %s (id %s)", self.user, self.user.id if self.user else "?")
        log.info("serving %d guild(s)", len(self.guilds))
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="/help")
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
