"""Support ticket system.

A staff member posts a panel with `/ticket-panel`. Members click its
button and get a private channel only they and staff can see. Staff close
it with another button, which posts a transcript-style summary to the log
channel and deletes the channel.

The important technical detail here is **persistent views**. A normal
Discord button stops working when the bot restarts, because the bot
forgets the callback. To survive restarts a view needs:

  1. `timeout=None`
  2. a fixed `custom_id` on every button
  3. registration in `bot.setup_hook` via `bot.add_view(...)`

Get any of those wrong and your customer's ticket panel quietly dies the
next time the bot redeploys — which is exactly the kind of bug that gets
you a refund request.
"""

from __future__ import annotations

import datetime
import logging

import discord
from discord import app_commands
from discord.ext import commands

from core import config


log = logging.getLogger("cogs.tickets")

MAX_OPEN_PER_USER = 3


class TicketPanelView(discord.ui.View):
    """The permanent 'Open a ticket' button."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Open a ticket",
        style=discord.ButtonStyle.primary,
        emoji="📩",
        custom_id="ticket:open",
    )
    async def open_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        bot = interaction.client
        guild = interaction.guild
        if guild is None:
            return

        # Creating a channel takes a moment — acknowledge immediately.
        await interaction.response.defer(ephemeral=True)

        open_count = await bot.db.count_open_tickets(guild.id, interaction.user.id)
        if open_count >= MAX_OPEN_PER_USER:
            await interaction.followup.send(
                f"You already have {open_count} open tickets. Close one first.",
                ephemeral=True,
            )
            return

        category_id = await bot.db.get_int_setting(guild.id, "ticket_category")
        staff_role_id = await bot.db.get_int_setting(guild.id, "ticket_staff_role")

        category = guild.get_channel(category_id) if category_id else None
        if not isinstance(category, discord.CategoryChannel):
            category = None

        # Only the opener, staff, and the bot can see the channel.
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, attach_files=True,
                read_message_history=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True,
                read_message_history=True,
            ),
        }
        staff_role = guild.get_role(staff_role_id) if staff_role_id else None
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
            )

        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{interaction.user.name}",
                category=category,
                overwrites=overwrites,
                topic=f"Ticket opened by {interaction.user} ({interaction.user.id})",
                reason=f"Ticket opened by {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have the **Manage Channels** permission, so I can't "
                "create your ticket. Tell an admin.",
                ephemeral=True,
            )
            return

        await bot.db.create_ticket(channel.id, guild.id, interaction.user.id)

        embed = discord.Embed(
            title="Ticket opened",
            description=(
                f"Hi {interaction.user.mention} — describe your problem here and "
                "someone will be with you shortly.\n\n"
                "Staff can close this ticket with the button below."
            ),
            color=config.COLOR_PRIMARY,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.set_footer(text=config.EMBED_FOOTER)

        mention = staff_role.mention if staff_role else ""
        await channel.send(content=mention, embed=embed, view=TicketCloseView())

        await interaction.followup.send(
            f"Ticket created: {channel.mention}", ephemeral=True
        )


class TicketCloseView(discord.ui.View):
    """The permanent 'Close ticket' button inside a ticket channel."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Close ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="ticket:close",
    )
    async def close_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        bot = interaction.client
        guild = interaction.guild
        if guild is None:
            return

        ticket = await bot.db.get_ticket(interaction.channel.id)
        if ticket is None:
            await interaction.response.send_message(
                "This doesn't look like a ticket channel.", ephemeral=True
            )
            return

        # The opener can close their own; otherwise you need Manage Channels.
        is_opener = interaction.user.id == ticket["user_id"]
        is_staff = interaction.user.guild_permissions.manage_channels
        if not (is_opener or is_staff):
            await interaction.response.send_message(
                "Only staff or the person who opened this can close it.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Closing this ticket in 5 seconds..."
        )
        await bot.db.close_ticket(interaction.channel.id)

        log_channel_id = await bot.db.get_int_setting(guild.id, "ticket_log_channel")
        if log_channel_id:
            log_channel = guild.get_channel(log_channel_id)
            if isinstance(log_channel, discord.TextChannel):
                embed = discord.Embed(
                    title="Ticket closed",
                    color=config.COLOR_WARNING,
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                )
                embed.add_field(name="Opened by", value=f"<@{ticket['user_id']}>")
                embed.add_field(name="Closed by", value=interaction.user.mention)
                embed.add_field(name="Channel", value=f"#{interaction.channel.name}")
                embed.add_field(name="Opened at", value=ticket["created_at"], inline=False)
                try:
                    await log_channel.send(embed=embed)
                except discord.Forbidden:
                    pass

        import asyncio
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
        except discord.Forbidden:
            log.warning("couldn't delete ticket channel %s", interaction.channel.id)


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="ticket-panel",
        description="Post the ticket panel that members click to open a ticket",
    )
    @app_commands.describe(
        channel="Where to post it (default: here)",
        title="Panel heading",
        message="Panel body text",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def ticket_panel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        title: str = "Need help?",
        message: str = "Click the button below to open a private ticket with staff.",
    ) -> None:
        target = channel or interaction.channel

        embed = discord.Embed(
            title=title, description=message, color=config.COLOR_PRIMARY
        )
        embed.set_footer(text=config.EMBED_FOOTER)

        try:
            await target.send(embed=embed, view=TicketPanelView())
        except discord.Forbidden:
            await interaction.response.send_message(
                f"I can't post in {target.mention}.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"Ticket panel posted in {target.mention}.", ephemeral=True
        )

    @app_commands.command(
        name="ticket-add", description="Add a member to this ticket channel"
    )
    @app_commands.describe(member="Who to add")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def ticket_add(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        ticket = await self.bot.db.get_ticket(interaction.channel.id)
        if ticket is None:
            await interaction.response.send_message(
                "This isn't a ticket channel.", ephemeral=True
            )
            return

        await interaction.channel.set_permissions(
            member, view_channel=True, send_messages=True, read_message_history=True
        )
        await interaction.response.send_message(
            f"Added {member.mention} to this ticket."
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tickets(bot))
