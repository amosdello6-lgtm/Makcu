"""help, ping, serverinfo, userinfo, avatar."""

from __future__ import annotations

import datetime

import discord
from discord import app_commands
from discord.ext import commands

from core import config


CATEGORY_LABELS = {
    "General": "General",
    "Moderation": "Moderation",
    "AutoMod": "Auto-moderation",
    "Leveling": "Levels & XP",
    "Tickets": "Support tickets",
    "RoleMenu": "Self-assignable roles",
    "ServerLog": "Event logging",
    "Settings": "Configuration (admins)",
    "Welcome": "Welcome system",
}


class General(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="help", description="Show everything this bot can do")
    async def help(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Commands",
            description="Everything this bot can do. Admin commands are only "
                        "visible to people who can use them.",
            color=config.COLOR_PRIMARY,
        )

        by_category: dict[str, list[str]] = {}
        for command in self.bot.tree.walk_commands():
            if isinstance(command, app_commands.Group):
                continue
            cog_name = getattr(command.binding, "__cog_name__", None) or "Other"
            label = CATEGORY_LABELS.get(cog_name, cog_name)
            by_category.setdefault(label, []).append(
                f"`/{command.qualified_name}` - {command.description}"
            )

        for label in sorted(by_category):
            body = "\n".join(sorted(by_category[label]))
            if len(body) > 1024:  # embed field limit
                body = body[:1000] + "\n*…and more*"
            embed.add_field(name=label, value=body, inline=False)

        embed.set_footer(text=config.EMBED_FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="ping", description="Check if the bot is responsive")
    async def ping(self, interaction: discord.Interaction) -> None:
        latency_ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(
            f"Pong - **{latency_ms}ms** to Discord.", ephemeral=True
        )

    @app_commands.command(name="serverinfo", description="Stats about this server")
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        assert guild is not None

        humans = sum(1 for m in guild.members if not m.bot)
        bots = guild.member_count - humans if guild.member_count else 0

        embed = discord.Embed(title=guild.name, color=config.COLOR_PRIMARY)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Members", value=f"{humans:,} humans · {bots:,} bots")
        embed.add_field(name="Channels", value=str(len(guild.channels)))
        embed.add_field(name="Roles", value=str(len(guild.roles)))
        embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "?")
        embed.add_field(
            name="Created",
            value=discord.utils.format_dt(guild.created_at, style="D"),
        )
        embed.add_field(name="Boosts", value=str(guild.premium_subscription_count or 0))
        embed.set_footer(text=f"Server ID: {guild.id}")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="Info about a member")
    @app_commands.describe(member="Who to look up (default: yourself)")
    @app_commands.guild_only()
    async def userinfo(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        member = member or interaction.user  # type: ignore[assignment]

        roles = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]

        embed = discord.Embed(
            title=str(member),
            color=member.color if member.color.value else config.COLOR_PRIMARY,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(
            name="Joined server",
            value=discord.utils.format_dt(member.joined_at, style="R")
            if member.joined_at else "unknown",
        )
        embed.add_field(
            name="Account created",
            value=discord.utils.format_dt(member.created_at, style="R"),
        )
        embed.add_field(name="Top role", value=member.top_role.mention)
        if roles:
            value = " ".join(roles)
            embed.add_field(
                name=f"Roles ({len(roles)})",
                value=value if len(value) <= 1024 else f"{len(roles)} roles",
                inline=False,
            )
        embed.set_footer(text=f"User ID: {member.id}")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="Show a member's avatar in full size")
    @app_commands.describe(member="Whose avatar (default: yourself)")
    async def avatar(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        member = member or interaction.user  # type: ignore[assignment]
        embed = discord.Embed(
            title=f"{member.display_name}'s avatar", color=config.COLOR_PRIMARY
        )
        embed.set_image(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(General(bot))
