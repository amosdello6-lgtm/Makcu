"""Welcome / goodbye messages and auto-role.

Everything here is driven by settings, so the same code behaves
differently in every server it runs in. If no welcome channel is set,
the whole feature silently does nothing — that's deliberate, a bot that
spams an unconfigured server gets removed.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from core import config


log = logging.getLogger("cogs.welcome")

DEFAULT_WELCOME = "Welcome to **{server}**, {user}! You're member #{count}."
DEFAULT_GOODBYE = "**{username}** has left the server."


def render(template: str, member: discord.Member) -> str:
    """Substitute the placeholders a server owner can use in their text."""
    return (
        template.replace("{user}", member.mention)
        .replace("{username}", member.display_name)
        .replace("{server}", member.guild.name)
        .replace("{count}", str(member.guild.member_count or 0))
    )


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self._assign_autorole(member)
        await self._send_welcome(member)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        channel_id = await self.bot.db.get_int_setting(member.guild.id, "goodbye_channel")
        if channel_id is None:
            return
        channel = member.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        try:
            await channel.send(render(DEFAULT_GOODBYE, member))
        except discord.Forbidden:
            log.warning("no permission to post goodbye in %s", channel.id)

    # -----------------------------------------------------------------

    async def _assign_autorole(self, member: discord.Member) -> None:
        role_id = await self.bot.db.get_int_setting(member.guild.id, "autorole")
        if role_id is None:
            return
        role = member.guild.get_role(role_id)
        if role is None:
            # The role was deleted since it was configured — clean up.
            await self.bot.db.clear_setting(member.guild.id, "autorole")
            return

        try:
            await member.add_roles(role, reason="Auto-role on join")
        except discord.Forbidden:
            log.warning(
                "can't assign autorole %s in guild %s — check role hierarchy",
                role.id, member.guild.id,
            )

    async def _send_welcome(self, member: discord.Member) -> None:
        channel_id = await self.bot.db.get_int_setting(member.guild.id, "welcome_channel")
        if channel_id is None:
            return
        channel = member.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        template = await self.bot.db.get_setting(
            member.guild.id, "welcome_message", DEFAULT_WELCOME
        )

        embed = discord.Embed(
            description=render(template, member),
            color=config.COLOR_SUCCESS,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=config.EMBED_FOOTER)

        try:
            await channel.send(content=member.mention, embed=embed)
        except discord.Forbidden:
            log.warning("no permission to post welcome in %s", channel.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Welcome(bot))
