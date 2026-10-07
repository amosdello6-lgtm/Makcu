"""Self-assignable roles via buttons.

Buttons use DynamicItem because the role id isn't known until an admin
builds the menu, so a fixed custom_id isn't possible.
"""

from __future__ import annotations

import re

import discord
from discord import app_commands
from discord.ext import commands

from core import config


class RoleButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"rolemenu:(?P<role_id>\d+)",
):
    def __init__(self, role_id: int, label: str) -> None:
        self.role_id = role_id
        super().__init__(
            discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.secondary,
                custom_id=f"rolemenu:{role_id}",
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
    ) -> "RoleButton":
        return cls(int(match["role_id"]), item.label or "Role")

    async def callback(self, interaction: discord.Interaction) -> None:
        bot = interaction.client
        guild = interaction.guild
        if guild is None:
            return

        # role_id arrives in the custom_id, which is client-visible. Without
        # this check a crafted interaction could request any role.
        if not await bot.db.role_option_exists(guild.id, self.role_id):
            await interaction.response.send_message(
                "That role isn't available from this menu.", ephemeral=True
            )
            return

        role = guild.get_role(self.role_id)
        if role is None:
            await interaction.response.send_message(
                "That role no longer exists.", ephemeral=True
            )
            return

        if role >= guild.me.top_role:
            await interaction.response.send_message(
                "I can't manage that role - it's above me in the role list. "
                "Tell an admin to move my role higher.",
                ephemeral=True,
            )
            return

        member = interaction.user
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Role menu")
                await interaction.response.send_message(
                    f"Removed {role.mention}.", ephemeral=True
                )
            else:
                await member.add_roles(role, reason="Role menu")
                await interaction.response.send_message(
                    f"Gave you {role.mention}.", ephemeral=True
                )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have the **Manage Roles** permission.", ephemeral=True
            )


class RoleMenu(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    group = app_commands.Group(
        name="rolemenu",
        description="Build self-assignable role menus",
        default_permissions=discord.Permissions(manage_roles=True),
        guild_only=True,
    )

    @group.command(name="create", description="Post an empty role menu")
    @app_commands.describe(
        title="Heading for the menu",
        message="Text under the heading",
        channel="Where to post it (default: here)",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def create(
        self,
        interaction: discord.Interaction,
        title: str = "Pick your roles",
        message: str = "Click a button to give yourself a role. Click again to remove it.",
        channel: discord.TextChannel | None = None,
    ) -> None:
        target = channel or interaction.channel

        embed = discord.Embed(
            title=title, description=message, color=config.COLOR_PRIMARY
        )
        embed.set_footer(text=config.EMBED_FOOTER)

        try:
            posted = await target.send(embed=embed, view=discord.ui.View(timeout=None))
        except discord.Forbidden:
            await interaction.response.send_message(
                f"I can't post in {target.mention}.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"Menu created in {target.mention}.\n"
            f"Now add roles to it with:\n"
            f"`/rolemenu add message_id:{posted.id} role:@YourRole`",
            ephemeral=True,
        )

    @group.command(name="add", description="Add a role button to an existing menu")
    @app_commands.describe(
        message_id="The menu's message ID (given when you created it)",
        role="Which role the button grants",
        label="Button text (default: the role's name)",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def add(
        self,
        interaction: discord.Interaction,
        message_id: str,
        role: discord.Role,
        label: str | None = None,
    ) -> None:
        if not message_id.isdigit():
            await interaction.response.send_message(
                "That isn't a valid message ID.", ephemeral=True
            )
            return

        guild = interaction.guild
        if role >= guild.me.top_role:
            await interaction.response.send_message(
                f"I can't hand out {role.mention} - it's above my own top role. "
                "Move my role higher in Server Settings → Roles first.",
                ephemeral=True,
            )
            return

        if role.is_default() or role.managed:
            await interaction.response.send_message(
                "That role can't be self-assigned (it's @everyone or managed "
                "by an integration).",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        message = await self._find_message(interaction, int(message_id))
        if message is None:
            await interaction.followup.send(
                "Couldn't find that message. Make sure the ID is right and the "
                "menu is in a channel I can see.",
                ephemeral=True,
            )
            return

        existing = await self.bot.db.get_role_options(message.id)
        if len(existing) >= 25:
            await interaction.followup.send(
                "That menu already has 25 buttons, which is Discord's limit.",
                ephemeral=True,
            )
            return

        await self.bot.db.add_role_option(
            message.id, guild.id, role.id, label or role.name
        )

        # Rebuild from the database so the view always matches stored state.
        options = await self.bot.db.get_role_options(message.id)
        view = discord.ui.View(timeout=None)
        for option in options:
            view.add_item(RoleButton(option["role_id"], option["label"]))

        try:
            await message.edit(view=view)
        except discord.Forbidden:
            await interaction.followup.send(
                "I can't edit that message.", ephemeral=True
            )
            return

        await interaction.followup.send(
            f"Added {role.mention} to the menu ({len(options)} button(s) total).",
            ephemeral=True,
        )

    async def _find_message(
        self, interaction: discord.Interaction, message_id: int
    ) -> discord.Message | None:
        """Check the current channel first, then every text channel."""
        try:
            return await interaction.channel.fetch_message(message_id)
        except (discord.NotFound, discord.Forbidden):
            pass

        for channel in interaction.guild.text_channels:
            try:
                return await channel.fetch_message(message_id)
            except (discord.NotFound, discord.Forbidden):
                continue
        return None


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RoleMenu(bot))
