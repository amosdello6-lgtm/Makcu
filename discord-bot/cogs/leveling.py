"""XP and levels.

Members earn a random amount of XP per message, with a cooldown so that
spamming doesn't farm levels. This is the single most requested feature
in small Discord servers because it visibly rewards activity.

The level curve is deliberately simple:

    level = floor( sqrt(xp / 100) )

So level 1 is 100 XP, level 2 is 400, level 3 is 900, level 10 is 10,000.
Each level costs more than the last, which is what keeps it interesting.
"""

from __future__ import annotations

import math
import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from core import config


def level_from_xp(xp: int) -> int:
    return int(math.sqrt(xp / 100))


def xp_for_level(level: int) -> int:
    return (level ** 2) * 100


class Leveling(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # -----------------------------------------------------------------
    # Earning XP
    # -----------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return

        enabled = await self.bot.db.get_setting(
            message.guild.id, "leveling_enabled", "1"
        )
        if enabled != "1":
            return

        now = time.time()
        current_xp, last_message_at = await self.bot.db.get_xp(
            message.guild.id, message.author.id
        )

        # Cooldown: without this, one person spamming "a" fifty times
        # outranks everyone who actually talks.
        if now - last_message_at < config.XP_COOLDOWN_SECONDS:
            return

        gain = random.randint(config.XP_PER_MESSAGE_MIN, config.XP_PER_MESSAGE_MAX)
        new_xp = await self.bot.db.add_xp(
            message.guild.id, message.author.id, gain, now
        )

        old_level = level_from_xp(current_xp)
        new_level = level_from_xp(new_xp)
        if new_level > old_level:
            await self._announce_levelup(message, new_level)

    async def _announce_levelup(self, message: discord.Message, level: int) -> None:
        channel_id = await self.bot.db.get_int_setting(
            message.guild.id, "levelup_channel"
        )
        channel = (
            message.guild.get_channel(channel_id) if channel_id else message.channel
        )
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            channel = message.channel

        embed = discord.Embed(
            description=f"{message.author.mention} reached **level {level}**",
            color=config.COLOR_SUCCESS,
        )
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

    # -----------------------------------------------------------------
    # Viewing progress
    # -----------------------------------------------------------------

    @app_commands.command(name="rank", description="Show your level and XP")
    @app_commands.describe(member="Whose rank to show (default: yourself)")
    @app_commands.guild_only()
    async def rank(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        member = member or interaction.user  # type: ignore[assignment]
        xp, _ = await self.bot.db.get_xp(interaction.guild_id, member.id)

        if xp == 0:
            await interaction.response.send_message(
                f"{member.mention} hasn't earned any XP yet.", ephemeral=True
            )
            return

        level = level_from_xp(xp)
        rank = await self.bot.db.get_rank(interaction.guild_id, member.id)

        current_floor = xp_for_level(level)
        next_floor = xp_for_level(level + 1)
        progress = xp - current_floor
        needed = next_floor - current_floor

        filled = int((progress / needed) * 20)
        bar = "█" * filled + "░" * (20 - filled)

        embed = discord.Embed(
            title=f"{member.display_name}'s rank",
            color=config.COLOR_PRIMARY,
        )
        embed.add_field(name="Level", value=str(level), inline=True)
        embed.add_field(name="Rank", value=f"#{rank}", inline=True)
        embed.add_field(name="Total XP", value=f"{xp:,}", inline=True)
        embed.add_field(
            name=f"Progress to level {level + 1}",
            value=f"`{bar}`\n{progress:,} / {needed:,} XP",
            inline=False,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=config.EMBED_FOOTER)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="Top members by XP")
    @app_commands.guild_only()
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.get_leaderboard(interaction.guild_id, limit=10)
        if not rows:
            await interaction.response.send_message(
                "Nobody has earned XP yet.", ephemeral=True
            )
            return

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = []
        for position, row in enumerate(rows, start=1):
            prefix = medals.get(position, f"`#{position}`")
            level = level_from_xp(row["xp"])
            lines.append(
                f"{prefix} <@{row['user_id']}> — level **{level}** ({row['xp']:,} XP)"
            )

        embed = discord.Embed(
            title=f"Leaderboard · {interaction.guild.name}",
            description="\n".join(lines),
            color=config.COLOR_PRIMARY,
        )
        embed.set_footer(text=config.EMBED_FOOTER)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Leveling(bot))
