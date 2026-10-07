"""Message filtering: invites, URLs, mass mentions, blocked words.

All filters are off by default. Manage Messages bypasses everything.
"""

from __future__ import annotations

import re

import discord
from discord import app_commands
from discord.ext import commands

from core import config


INVITE_RE = re.compile(
    r"(?:discord\.(?:gg|io|me|li)|discord(?:app)?\.com/invite)/[a-zA-Z0-9\-]+",
    re.IGNORECASE,
)
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)

MASS_MENTION_THRESHOLD = 5


class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    group = app_commands.Group(
        name="automod",
        description="Automatic message filtering",
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
    )

    # The filter itself

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        if message.author.guild_permissions.manage_messages:
            return

        reason = await self._violation(message)
        if reason is None:
            return

        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            return

        try:
            await message.channel.send(
                f"{message.author.mention} {reason}", delete_after=6
            )
        except discord.Forbidden:
            pass

        await self._log(message, reason)

    async def _violation(self, message: discord.Message) -> str | None:
        """Return a reason string, or None if the message is clean."""
        guild_id = message.guild.id
        db = self.bot.db
        content = message.content

        if await db.get_setting(guild_id, "automod_invites", "0") == "1":
            if INVITE_RE.search(content):
                return " - server invites aren't allowed here."

        if await db.get_setting(guild_id, "automod_links", "0") == "1":
            if URL_RE.search(content):
                return " - links aren't allowed here."

        if await db.get_setting(guild_id, "automod_mentions", "0") == "1":
            total = len(message.mentions) + len(message.role_mentions)
            if total >= MASS_MENTION_THRESHOLD:
                return f" - don't mention {MASS_MENTION_THRESHOLD}+ people at once."

        blocked = await db.get_blocked_words(guild_id)
        if blocked:
            lowered = content.lower()
            # Word boundaries, so blocking "ass" doesn't match "assistant".
            for word in blocked:
                if re.search(rf"\b{re.escape(word)}\b", lowered):
                    return " - that word isn't allowed here."

        return None

    async def _log(self, message: discord.Message, reason: str) -> None:
        channel_id = await self.bot.db.get_int_setting(message.guild.id, "log_channel")
        if channel_id is None:
            return
        channel = message.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        embed = discord.Embed(
            title="Automod - message deleted",
            description=reason.lstrip(" - ").capitalize(),
            color=config.COLOR_WARNING,
        )
        embed.add_field(name="Author", value=message.author.mention)
        embed.add_field(name="Channel", value=message.channel.mention)
        snippet = message.content[:500] or "*no text*"
        embed.add_field(name="Content", value=f"```{snippet}```", inline=False)

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

    # Configuration

    @group.command(name="invites", description="Delete messages containing Discord invites")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def invites(self, interaction: discord.Interaction, enabled: bool) -> None:
        await self._toggle(interaction, "automod_invites", enabled, "Invite blocking")

    @group.command(name="links", description="Delete messages containing any link")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def links(self, interaction: discord.Interaction, enabled: bool) -> None:
        await self._toggle(interaction, "automod_links", enabled, "Link blocking")

    @group.command(name="mentions", description="Delete messages with 5+ mentions")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def mentions(self, interaction: discord.Interaction, enabled: bool) -> None:
        await self._toggle(interaction, "automod_mentions", enabled, "Mass-mention blocking")

    @group.command(name="block-word", description="Add a word to the blocklist")
    @app_commands.describe(word="The word to block")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def block_word(self, interaction: discord.Interaction, word: str) -> None:
        word = word.strip().lower()
        if not word or len(word) > 100:
            await interaction.response.send_message(
                "That isn't a usable word.", ephemeral=True
            )
            return
        await self.bot.db.add_blocked_word(interaction.guild_id, word)
        await interaction.response.send_message(
            f"Added `{word}` to the blocklist.", ephemeral=True
        )

    @group.command(name="unblock-word", description="Remove a word from the blocklist")
    @app_commands.describe(word="The word to unblock")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def unblock_word(self, interaction: discord.Interaction, word: str) -> None:
        removed = await self.bot.db.remove_blocked_word(interaction.guild_id, word)
        if removed:
            await interaction.response.send_message(
                f"Removed `{word.lower()}` from the blocklist.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"`{word.lower()}` wasn't on the blocklist.", ephemeral=True
            )

    @group.command(name="words", description="Show the current blocklist")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def words(self, interaction: discord.Interaction) -> None:
        blocked = await self.bot.db.get_blocked_words(interaction.guild_id)
        if not blocked:
            await interaction.response.send_message(
                "The blocklist is empty.", ephemeral=True
            )
            return
        listing = ", ".join(f"`{w}`" for w in sorted(blocked))
        await interaction.response.send_message(
            f"**{len(blocked)} blocked word(s):**\n{listing}"[:2000], ephemeral=True
        )

    @group.command(name="status", description="Show which filters are on")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def status(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild_id
        rows = {
            "Invite blocking": "automod_invites",
            "Link blocking": "automod_links",
            "Mass-mention blocking": "automod_mentions",
        }

        embed = discord.Embed(title="Automod", color=config.COLOR_PRIMARY)
        for label, key in rows.items():
            on = await self.bot.db.get_setting(guild_id, key, "0") == "1"
            embed.add_field(name=label, value="on" if on else "off", inline=True)

        blocked = await self.bot.db.get_blocked_words(guild_id)
        embed.add_field(
            name="Blocked words", value=str(len(blocked)), inline=True
        )
        embed.set_footer(text="Staff with Manage Messages bypass all filters")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _toggle(
        self, interaction: discord.Interaction, key: str, enabled: bool, label: str
    ) -> None:
        await self.bot.db.set_setting(
            interaction.guild_id, key, "1" if enabled else "0"
        )
        await interaction.response.send_message(
            f"{label} is now **{'on' if enabled else 'off'}**.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoMod(bot))
