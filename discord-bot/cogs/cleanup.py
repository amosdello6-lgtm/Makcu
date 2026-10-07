"""Channel clearing, manual and scheduled.

Clearing works by cloning the channel and deleting the original, because
Discord's bulk delete refuses messages older than 14 days. The clone keeps
permissions, topic, slowmode and position but gets a new id, so stored
settings pointing at the old channel are remapped afterwards.
"""

from __future__ import annotations

import logging
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core import config


log = logging.getLogger("cogs.cleanup")

MIN_INTERVAL_HOURS = 1
MAX_INTERVAL_HOURS = 720  # 30 days


async def wipe_channel(
    bot: commands.Bot, channel: discord.TextChannel, reason: str
) -> discord.TextChannel | None:
    """Replace a channel with an empty clone. Returns the new channel."""
    guild = channel.guild
    position = channel.position

    try:
        clone = await channel.clone(reason=reason)
        await clone.edit(position=position)
        await channel.delete(reason=reason)
    except discord.Forbidden:
        log.warning("missing Manage Channels to wipe %s", channel.id)
        return None
    except discord.HTTPException:
        log.exception("failed to wipe channel %s", channel.id)
        return None

    remapped = await bot.db.remap_channel_references(guild.id, channel.id, clone.id)
    if remapped:
        log.info(
            "remapped settings %s from channel %s to %s",
            ", ".join(remapped), channel.id, clone.id,
        )
    return clone


class ConfirmWipe(discord.ui.View):
    """Short-lived confirmation. Not persistent on purpose - a stale
    confirm button for a destructive action is a hazard."""

    def __init__(self, author_id: int) -> None:
        super().__init__(timeout=30)
        self.author_id = author_id
        self.confirmed = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Only the person who ran the command can confirm this.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Delete everything", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.confirmed = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(content="Cancelled.", embed=None, view=None)
        self.stop()


class Cleanup(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.autoclear_loop.start()

    async def cog_unload(self) -> None:
        self.autoclear_loop.cancel()

    @app_commands.command(
        name="clear",
        description="Delete every message in a channel by replacing it with an empty copy",
    )
    @app_commands.describe(channel="Which channel (default: this one)")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def clear(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        target = channel or interaction.channel

        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message(
                "That only works on text channels.", ephemeral=True
            )
            return

        warning = discord.Embed(
            title="Delete every message in this channel?",
            description=(
                f"This wipes **all** history in {target.mention}.\n\n"
                "The channel is replaced by an identical empty copy, keeping "
                "its name, permissions, topic and position.\n\n"
                "**This cannot be undone.**"
            ),
            color=config.COLOR_DANGER,
        )

        view = ConfirmWipe(interaction.user.id)
        await interaction.response.send_message(
            embed=warning, view=view, ephemeral=True
        )
        await view.wait()

        if not view.confirmed:
            if not view.is_finished():
                await interaction.edit_original_response(
                    content="Timed out.", embed=None, view=None
                )
            return

        clone = await wipe_channel(
            self.bot, target, reason=f"/clear by {interaction.user}"
        )
        if clone is None:
            await interaction.edit_original_response(
                content="Failed. I need the **Manage Channels** permission.",
                embed=None,
                view=None,
            )
            return

        await self._log_wipe(interaction.guild, clone, interaction.user, "Manual")

        # The original channel is gone, so if the command ran there the
        # original response went with it. Post into the clone instead.
        if target.id == interaction.channel_id:
            try:
                await clone.send(
                    embed=discord.Embed(
                        description=f"Channel cleared by {interaction.user.mention}.",
                        color=config.COLOR_SUCCESS,
                    )
                )
            except discord.Forbidden:
                pass
        else:
            await interaction.edit_original_response(
                content=f"Cleared {clone.mention}.", embed=None, view=None
            )

    group = app_commands.Group(
        name="autoclear",
        description="Clear channels automatically on a schedule",
        default_permissions=discord.Permissions(manage_channels=True),
        guild_only=True,
    )

    @group.command(name="set", description="Clear a channel every X hours")
    @app_commands.describe(
        channel="Which channel to clear",
        hours="How often, in hours (1 = hourly, 24 = daily, 168 = weekly)",
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def autoclear_set(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        hours: app_commands.Range[int, MIN_INTERVAL_HOURS, MAX_INTERVAL_HOURS],
    ) -> None:
        await self.bot.db.set_autoclear(
            channel.id, interaction.guild_id, hours, time.time()
        )

        if hours == 24:
            cadence = "every day"
        elif hours == 168:
            cadence = "every week"
        elif hours == 1:
            cadence = "every hour"
        else:
            cadence = f"every {hours} hours"

        await interaction.response.send_message(
            f"{channel.mention} will be cleared **{cadence}**.\n"
            f"First clear in {hours} hour(s). Turn it off with "
            f"`/autoclear remove`.",
            ephemeral=True,
        )

    @group.command(name="remove", description="Stop auto-clearing a channel")
    @app_commands.describe(channel="Which channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def autoclear_remove(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        removed = await self.bot.db.remove_autoclear(channel.id)
        if removed:
            await interaction.response.send_message(
                f"{channel.mention} will no longer be cleared automatically.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"{channel.mention} wasn't set to auto-clear.", ephemeral=True
            )

    @group.command(name="list", description="Show channels set to auto-clear")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def autoclear_list(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.get_autoclears(interaction.guild_id)
        if not rows:
            await interaction.response.send_message(
                "No channels are set to auto-clear.", ephemeral=True
            )
            return

        now = time.time()
        lines = []
        for row in rows:
            due_in = (row["last_cleared"] + row["interval_hours"] * 3600) - now
            when = (
                "due now" if due_in <= 0
                else f"in {int(due_in // 3600)}h {int((due_in % 3600) // 60)}m"
            )
            lines.append(
                f"<#{row['channel_id']}> - every {row['interval_hours']}h ({when})"
            )

        embed = discord.Embed(
            title="Scheduled clears",
            description="\n".join(lines),
            color=config.COLOR_PRIMARY,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tasks.loop(minutes=10)
    async def autoclear_loop(self) -> None:
        now = time.time()
        try:
            due = await self.bot.db.get_due_autoclears(now)
        except Exception:
            log.exception("autoclear: failed to read schedule")
            return

        for row in due:
            channel = self.bot.get_channel(row["channel_id"])
            if not isinstance(channel, discord.TextChannel):
                # Channel was deleted by hand - drop the schedule.
                await self.bot.db.remove_autoclear(row["channel_id"])
                continue

            clone = await wipe_channel(self.bot, channel, reason="Scheduled auto-clear")
            if clone is None:
                # Leave the row alone so it retries next tick.
                continue

            await self.bot.db.mark_autoclear_run(row["channel_id"], clone.id, now)
            await self._log_wipe(clone.guild, clone, self.bot.user, "Scheduled")
            log.info("auto-cleared %s in guild %s", clone.name, clone.guild.id)

    @autoclear_loop.before_loop
    async def before_autoclear(self) -> None:
        await self.bot.wait_until_ready()

    async def _log_wipe(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        actor: discord.abc.User,
        kind: str,
    ) -> None:
        channel_id = await self.bot.db.get_int_setting(guild.id, "log_channel")
        if channel_id is None or channel_id == channel.id:
            return
        log_channel = guild.get_channel(channel_id)
        if not isinstance(log_channel, discord.TextChannel):
            return

        embed = discord.Embed(
            title=f"{kind} channel clear",
            color=config.COLOR_WARNING,
        )
        embed.add_field(name="Channel", value=channel.mention)
        embed.add_field(name="By", value=getattr(actor, "mention", str(actor)))

        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Cleanup(bot))
