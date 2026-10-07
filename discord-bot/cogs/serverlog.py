"""Server event logging: deletes, edits, joins, leaves, role changes.

Separate from the moderation log (which records *actions staff took*).
This records *things that happened*, which is what admins actually want
when someone says "they deleted the message before I saw it".

Named `serverlog` rather than `logging` on purpose — a module called
`logging.py` invites confusion with Python's standard library one.

Each event type is individually toggleable, because a busy server with
every log on will flood a channel and the owner will turn the whole
feature off instead of just the noisy part.
"""

from __future__ import annotations

import datetime

import discord
from discord import app_commands
from discord.ext import commands

from core import config


class ServerLog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    group = app_commands.Group(
        name="logging",
        description="Configure server event logging",
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
    )

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    async def _channel(self, guild: discord.Guild, key: str) -> discord.TextChannel | None:
        """Return the log channel if this event type is enabled."""
        if await self.bot.db.get_setting(guild.id, key, "0") != "1":
            return None
        channel_id = await self.bot.db.get_int_setting(guild.id, "log_channel")
        if channel_id is None:
            return None
        channel = guild.get_channel(channel_id)
        return channel if isinstance(channel, discord.TextChannel) else None

    @staticmethod
    async def _post(channel: discord.TextChannel, embed: discord.Embed) -> None:
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

    # -----------------------------------------------------------------
    # Events
    # -----------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        channel = await self._channel(message.guild, "log_deletes")
        if channel is None or channel.id == message.channel.id:
            return

        embed = discord.Embed(
            title="Message deleted",
            color=config.COLOR_DANGER,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Author", value=message.author.mention, inline=True)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        content = message.content[:1000] if message.content else "*no text*"
        embed.add_field(name="Content", value=f"```{content}```", inline=False)
        if message.attachments:
            embed.add_field(
                name="Attachments",
                value="\n".join(a.filename for a in message.attachments[:5]),
                inline=False,
            )
        await self._post(channel, embed)

    @commands.Cog.listener()
    async def on_message_edit(
        self, before: discord.Message, after: discord.Message
    ) -> None:
        if before.guild is None or before.author.bot:
            return
        # Embed loading fires an edit with identical content — ignore those.
        if before.content == after.content:
            return
        channel = await self._channel(before.guild, "log_edits")
        if channel is None:
            return

        embed = discord.Embed(
            title="Message edited",
            url=after.jump_url,
            color=config.COLOR_WARNING,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Author", value=before.author.mention, inline=True)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(
            name="Before", value=f"```{(before.content or '*empty*')[:500]}```", inline=False
        )
        embed.add_field(
            name="After", value=f"```{(after.content or '*empty*')[:500]}```", inline=False
        )
        await self._post(channel, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        channel = await self._channel(member.guild, "log_joins")
        if channel is None:
            return

        age = datetime.datetime.now(datetime.timezone.utc) - member.created_at

        embed = discord.Embed(
            title="Member joined",
            color=config.COLOR_SUCCESS,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Member", value=f"{member.mention}\n`{member.id}`")
        embed.add_field(
            name="Account created",
            value=discord.utils.format_dt(member.created_at, style="R"),
        )
        embed.add_field(name="Member count", value=str(member.guild.member_count))
        # A brand-new account joining is the classic raid/alt signal.
        if age.days < 7:
            embed.add_field(
                name="⚠️ New account",
                value=f"This account is only {age.days} day(s) old.",
                inline=False,
            )
        embed.set_thumbnail(url=member.display_avatar.url)
        await self._post(channel, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        channel = await self._channel(member.guild, "log_leaves")
        if channel is None:
            return

        roles = [r.mention for r in member.roles if r.name != "@everyone"]

        embed = discord.Embed(
            title="Member left",
            color=config.COLOR_DANGER,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Member", value=f"{member}\n`{member.id}`")
        embed.add_field(
            name="Joined",
            value=discord.utils.format_dt(member.joined_at, style="R")
            if member.joined_at else "unknown",
        )
        if roles:
            value = " ".join(roles)
            embed.add_field(
                name="Roles",
                value=value if len(value) <= 1024 else f"{len(roles)} roles",
                inline=False,
            )
        embed.set_thumbnail(url=member.display_avatar.url)
        await self._post(channel, embed)

    @commands.Cog.listener()
    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        if before.roles == after.roles:
            return
        channel = await self._channel(after.guild, "log_roles")
        if channel is None:
            return

        gained = set(after.roles) - set(before.roles)
        lost = set(before.roles) - set(after.roles)

        embed = discord.Embed(
            title="Roles changed",
            color=config.COLOR_PRIMARY,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Member", value=after.mention, inline=False)
        if gained:
            embed.add_field(
                name="Added", value=" ".join(r.mention for r in gained), inline=False
            )
        if lost:
            embed.add_field(
                name="Removed", value=" ".join(r.mention for r in lost), inline=False
            )
        await self._post(channel, embed)

    # -----------------------------------------------------------------
    # Configuration
    # -----------------------------------------------------------------

    EVENTS = {
        "deletes": ("log_deletes", "Deleted messages"),
        "edits": ("log_edits", "Edited messages"),
        "joins": ("log_joins", "Members joining"),
        "leaves": ("log_leaves", "Members leaving"),
        "roles": ("log_roles", "Role changes"),
    }

    @group.command(name="toggle", description="Turn one log type on or off")
    @app_commands.describe(event="Which event type", enabled="on or off")
    @app_commands.choices(
        event=[
            app_commands.Choice(name="Deleted messages", value="deletes"),
            app_commands.Choice(name="Edited messages", value="edits"),
            app_commands.Choice(name="Members joining", value="joins"),
            app_commands.Choice(name="Members leaving", value="leaves"),
            app_commands.Choice(name="Role changes", value="roles"),
        ]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def toggle(
        self,
        interaction: discord.Interaction,
        event: app_commands.Choice[str],
        enabled: bool,
    ) -> None:
        key, label = self.EVENTS[event.value]
        await self.bot.db.set_setting(
            interaction.guild_id, key, "1" if enabled else "0"
        )

        note = ""
        if enabled:
            log_channel = await self.bot.db.get_int_setting(
                interaction.guild_id, "log_channel"
            )
            if log_channel is None:
                note = "\n\n⚠️ No log channel set yet — run `/config log-channel` too."

        await interaction.response.send_message(
            f"**{label}** logging is now **{'on' if enabled else 'off'}**.{note}",
            ephemeral=True,
        )

    @group.command(name="all", description="Turn every log type on or off at once")
    @app_commands.describe(enabled="on or off")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def all_logs(self, interaction: discord.Interaction, enabled: bool) -> None:
        for key, _ in self.EVENTS.values():
            await self.bot.db.set_setting(
                interaction.guild_id, key, "1" if enabled else "0"
            )
        await interaction.response.send_message(
            f"All logging turned **{'on' if enabled else 'off'}**.", ephemeral=True
        )

    @group.command(name="status", description="Show which logs are on")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def status(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(title="Event logging", color=config.COLOR_PRIMARY)
        for key, label in self.EVENTS.values():
            on = await self.bot.db.get_setting(interaction.guild_id, key, "0") == "1"
            embed.add_field(name=label, value="on" if on else "off", inline=True)

        channel_id = await self.bot.db.get_int_setting(
            interaction.guild_id, "log_channel"
        )
        embed.add_field(
            name="Log channel",
            value=f"<#{channel_id}>" if channel_id else "*not set*",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerLog(bot))
