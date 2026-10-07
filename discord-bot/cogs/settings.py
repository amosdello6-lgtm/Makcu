"""Per-server configuration commands.

This is the most commercially important file in the bot. Without it you
have a bot that does whatever you hardcoded. With it, the person who
bought the bot can point it at their own channels and roles, change the
welcome text, and turn features on and off — without ever asking you for
a code change.

Every setting is just a row in the `settings` table keyed by guild, so
adding a new one is one command here plus one `get_setting` call wherever
the feature lives.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core import config


# Every key the bot understands, with a human label for /config view.
# Add a row here when you add a setting and it shows up automatically.
KNOWN_SETTINGS: dict[str, str] = {
    "welcome_channel": "Welcome channel",
    "welcome_message": "Welcome message",
    "goodbye_channel": "Goodbye channel",
    "autorole": "Auto-role on join",
    "log_channel": "Moderation log channel",
    "levelup_channel": "Level-up announcement channel",
    "leveling_enabled": "Leveling system",
    "mute_role": "Mute role",
}


class Settings(commands.Cog):
    """Server owners configure the bot here."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # `default_permissions` hides these commands from members who can't
    # use them. It's a UI hint — the real check is the decorator on each
    # command, because a server admin can override Discord's defaults.
    group = app_commands.Group(
        name="config",
        description="Configure the bot for this server",
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
    )

    # -----------------------------------------------------------------
    # Viewing
    # -----------------------------------------------------------------

    @group.command(name="view", description="Show every current setting")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def view(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild_id
        assert guild_id is not None

        embed = discord.Embed(
            title="Bot configuration",
            description=f"Settings for **{interaction.guild.name}**",
            color=config.COLOR_PRIMARY,
        )

        for key, label in KNOWN_SETTINGS.items():
            raw = await self.bot.db.get_setting(guild_id, key)
            embed.add_field(name=label, value=self._render(key, raw), inline=False)

        embed.set_footer(text=config.EMBED_FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    def _render(self, key: str, raw: str | None) -> str:
        """Turn a stored string into something readable in Discord."""
        if raw is None:
            return "*not set*"
        if key.endswith("_channel"):
            return f"<#{raw}>"
        if key in ("autorole", "mute_role"):
            return f"<@&{raw}>"
        if key.endswith("_enabled"):
            return "on" if raw == "1" else "off"
        # Long text — keep the embed from exploding.
        return raw if len(raw) <= 300 else raw[:297] + "..."

    # -----------------------------------------------------------------
    # Channels
    # -----------------------------------------------------------------

    @group.command(
        name="welcome-channel",
        description="Where to post welcome messages when someone joins",
    )
    @app_commands.describe(channel="Leave empty to turn welcome messages off")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        await self._set_or_clear(interaction, "welcome_channel", channel)

    @group.command(
        name="goodbye-channel",
        description="Where to post a message when someone leaves",
    )
    @app_commands.describe(channel="Leave empty to turn goodbye messages off")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def goodbye_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        await self._set_or_clear(interaction, "goodbye_channel", channel)

    @group.command(
        name="log-channel",
        description="Where to log moderation actions (warns, kicks, bans)",
    )
    @app_commands.describe(channel="Leave empty to turn logging off")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def log_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        await self._set_or_clear(interaction, "log_channel", channel)

    @group.command(
        name="levelup-channel",
        description="Where to announce level-ups (default: the channel they spoke in)",
    )
    @app_commands.describe(channel="Leave empty to announce in the current channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def levelup_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        await self._set_or_clear(interaction, "levelup_channel", channel)

    # -----------------------------------------------------------------
    # Roles
    # -----------------------------------------------------------------

    @group.command(
        name="autorole",
        description="Role automatically given to every new member",
    )
    @app_commands.describe(role="Leave empty to turn auto-role off")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def autorole(
        self, interaction: discord.Interaction, role: discord.Role | None = None
    ) -> None:
        # A bot can only hand out roles below its own highest role.
        if role is not None and interaction.guild is not None:
            me = interaction.guild.me
            if role >= me.top_role:
                await interaction.response.send_message(
                    f"I can't assign {role.mention} — it's higher than my own top "
                    f"role ({me.top_role.mention}). Drag my role above it in "
                    "Server Settings → Roles.",
                    ephemeral=True,
                )
                return
        await self._set_or_clear(interaction, "autorole", role)

    # -----------------------------------------------------------------
    # Text
    # -----------------------------------------------------------------

    @group.command(
        name="welcome-message",
        description="Custom welcome text. Placeholders: {user} {username} {server} {count}",
    )
    @app_commands.describe(message="Leave empty to reset to the default message")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome_message(
        self, interaction: discord.Interaction, message: str | None = None
    ) -> None:
        guild_id = interaction.guild_id
        assert guild_id is not None

        if message is None:
            await self.bot.db.clear_setting(guild_id, "welcome_message")
            await interaction.response.send_message(
                "Welcome message reset to the default.", ephemeral=True
            )
            return

        if len(message) > 1500:
            await interaction.response.send_message(
                "That's too long — keep it under 1500 characters.", ephemeral=True
            )
            return

        await self.bot.db.set_setting(guild_id, "welcome_message", message)
        preview = (
            message.replace("{user}", interaction.user.mention)
            .replace("{username}", interaction.user.display_name)
            .replace("{server}", interaction.guild.name if interaction.guild else "")
            .replace("{count}", str(interaction.guild.member_count if interaction.guild else 0))
        )
        await interaction.response.send_message(
            f"Welcome message saved. Preview:\n\n{preview}", ephemeral=True
        )

    # -----------------------------------------------------------------
    # Toggles
    # -----------------------------------------------------------------

    @group.command(name="leveling", description="Turn the XP / leveling system on or off")
    @app_commands.describe(enabled="on or off")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def leveling(self, interaction: discord.Interaction, enabled: bool) -> None:
        guild_id = interaction.guild_id
        assert guild_id is not None
        await self.bot.db.set_setting(guild_id, "leveling_enabled", "1" if enabled else "0")
        await interaction.response.send_message(
            f"Leveling is now **{'on' if enabled else 'off'}**.", ephemeral=True
        )

    # -----------------------------------------------------------------
    # Shared helper
    # -----------------------------------------------------------------

    async def _set_or_clear(
        self,
        interaction: discord.Interaction,
        key: str,
        value: discord.TextChannel | discord.Role | None,
    ) -> None:
        guild_id = interaction.guild_id
        assert guild_id is not None

        if value is None:
            await self.bot.db.clear_setting(guild_id, key)
            await interaction.response.send_message(
                f"`{KNOWN_SETTINGS.get(key, key)}` cleared.", ephemeral=True
            )
        else:
            await self.bot.db.set_setting(guild_id, key, value.id)
            await interaction.response.send_message(
                f"`{KNOWN_SETTINGS.get(key, key)}` set to {value.mention}.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Settings(bot))
