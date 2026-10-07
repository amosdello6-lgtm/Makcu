"""Moderation commands: warn, kick, ban, timeout, purge.

The interesting part of a moderation cog is not the kick call — it's the
safety checks around it. Cheap bots skip these and then a moderator can
ban someone above them in the role hierarchy, or ban the owner, or ban
themselves. Every command here runs the same `_can_moderate` gate first.
"""

from __future__ import annotations

import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from core import config


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # -----------------------------------------------------------------
    # Shared safety + logging
    # -----------------------------------------------------------------

    def _can_moderate(
        self, actor: discord.Member, target: discord.Member
    ) -> Optional[str]:
        """Return an error string if this action isn't allowed, else None."""
        if actor.id == target.id:
            return "You can't do that to yourself."
        if target.id == actor.guild.owner_id:
            return "You can't moderate the server owner."
        if target.bot and target.id == self.bot.user.id:
            return "I'm not going to do that to myself."

        # The guild owner outranks everyone, including by role position.
        if actor.id != actor.guild.owner_id and target.top_role >= actor.top_role:
            return (
                f"{target.mention} has a role equal to or above yours, "
                "so you can't moderate them."
            )

        me = actor.guild.me
        if target.top_role >= me.top_role:
            return (
                f"{target.mention} is above me in the role list, so I can't act on "
                f"them. Drag my role ({me.top_role.mention}) higher in "
                "Server Settings → Roles."
            )
        return None

    async def _log(
        self,
        guild: discord.Guild,
        action: str,
        target: discord.abc.User,
        moderator: discord.abc.User,
        reason: str,
        colour: int,
    ) -> None:
        """Post to the configured log channel, if there is one."""
        channel_id = await self.bot.db.get_int_setting(guild.id, "log_channel")
        if channel_id is None:
            return
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        embed = discord.Embed(
            title=action,
            color=colour,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Member", value=f"{target} (`{target.id}`)", inline=False)
        embed.add_field(name="Moderator", value=moderator.mention, inline=True)
        embed.add_field(name="Reason", value=reason or "No reason given", inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            # Missing permission in the log channel shouldn't fail the action.
            pass

    # -----------------------------------------------------------------
    # Warn
    # -----------------------------------------------------------------

    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.describe(member="Who to warn", reason="Why")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "No reason given",
    ) -> None:
        error = self._can_moderate(interaction.user, member)  # type: ignore[arg-type]
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        await self.bot.db.add_warn(
            interaction.guild_id, member.id, interaction.user.id, reason
        )
        warns = await self.bot.db.get_warns(interaction.guild_id, member.id)

        await interaction.response.send_message(
            f"Warned {member.mention}. They now have **{len(warns)}** warning(s).\n"
            f"Reason: {reason}"
        )

        # Tell the member privately. They may have DMs closed — that's fine.
        try:
            await member.send(
                f"You were warned in **{interaction.guild.name}**.\nReason: {reason}"
            )
        except discord.Forbidden:
            pass

        await self._log(
            interaction.guild, "Member warned", member, interaction.user,
            reason, config.COLOR_WARNING,
        )

    @app_commands.command(name="warnings", description="List a member's warnings")
    @app_commands.describe(member="Whose warnings to show")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def warnings(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        warns = await self.bot.db.get_warns(interaction.guild_id, member.id)
        if not warns:
            await interaction.response.send_message(
                f"{member.mention} has no warnings.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"Warnings for {member.display_name}",
            description=f"{len(warns)} total",
            color=config.COLOR_WARNING,
        )
        # Embeds cap at 25 fields — show the 10 most recent.
        for warn in warns[:10]:
            embed.add_field(
                name=f"#{warn['id']} · {warn['created_at']}",
                value=f"By <@{warn['moderator_id']}>\n{warn['reason']}",
                inline=False,
            )
        if len(warns) > 10:
            embed.set_footer(text=f"Showing 10 of {len(warns)}")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="clearwarns", description="Delete all of a member's warnings")
    @app_commands.describe(member="Whose warnings to clear")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def clearwarns(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        removed = await self.bot.db.clear_warns(interaction.guild_id, member.id)
        await interaction.response.send_message(
            f"Cleared **{removed}** warning(s) from {member.mention}."
        )

    # -----------------------------------------------------------------
    # Timeout
    # -----------------------------------------------------------------

    @app_commands.command(
        name="timeout", description="Temporarily mute a member (Discord timeout)"
    )
    @app_commands.describe(
        member="Who to time out",
        minutes="How many minutes (max 40320 = 28 days)",
        reason="Why",
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: app_commands.Range[int, 1, 40320],
        reason: str = "No reason given",
    ) -> None:
        error = self._can_moderate(interaction.user, member)  # type: ignore[arg-type]
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        duration = datetime.timedelta(minutes=minutes)
        try:
            await member.timeout(duration, reason=reason)
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have the **Timeout Members** permission.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"{member.mention} timed out for **{minutes} minute(s)**.\nReason: {reason}"
        )
        await self._log(
            interaction.guild, f"Member timed out ({minutes}m)", member,
            interaction.user, reason, config.COLOR_WARNING,
        )

    @app_commands.command(name="untimeout", description="Remove a member's timeout")
    @app_commands.describe(member="Who to un-timeout")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def untimeout(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        try:
            await member.timeout(None, reason=f"Lifted by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to do that.", ephemeral=True
            )
            return
        await interaction.response.send_message(f"Timeout removed from {member.mention}.")

    # -----------------------------------------------------------------
    # Kick / ban
    # -----------------------------------------------------------------

    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(member="Who to kick", reason="Why")
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.guild_only()
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "No reason given",
    ) -> None:
        error = self._can_moderate(interaction.user, member)  # type: ignore[arg-type]
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        # DM before kicking — afterwards we may no longer share a server.
        try:
            await member.send(
                f"You were kicked from **{interaction.guild.name}**.\nReason: {reason}"
            )
        except discord.Forbidden:
            pass

        try:
            await member.kick(reason=f"{interaction.user}: {reason}")
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have the **Kick Members** permission.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"Kicked {member.mention}.\nReason: {reason}"
        )
        await self._log(
            interaction.guild, "Member kicked", member, interaction.user,
            reason, config.COLOR_DANGER,
        )

    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(
        member="Who to ban",
        reason="Why",
        delete_days="Days of their messages to delete (0-7)",
    )
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.guild_only()
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "No reason given",
        delete_days: app_commands.Range[int, 0, 7] = 0,
    ) -> None:
        error = self._can_moderate(interaction.user, member)  # type: ignore[arg-type]
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        try:
            await member.send(
                f"You were banned from **{interaction.guild.name}**.\nReason: {reason}"
            )
        except discord.Forbidden:
            pass

        try:
            await member.ban(
                reason=f"{interaction.user}: {reason}",
                delete_message_days=delete_days,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have the **Ban Members** permission.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"Banned {member.mention}.\nReason: {reason}"
        )
        await self._log(
            interaction.guild, "Member banned", member, interaction.user,
            reason, config.COLOR_DANGER,
        )

    @app_commands.command(name="unban", description="Unban a user by their ID")
    @app_commands.describe(user_id="The numeric user ID to unban")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.guild_only()
    async def unban(self, interaction: discord.Interaction, user_id: str) -> None:
        if not user_id.isdigit():
            await interaction.response.send_message(
                "That isn't a valid user ID — it should be all digits.", ephemeral=True
            )
            return

        try:
            user = await self.bot.fetch_user(int(user_id))
            await interaction.guild.unban(user)
        except discord.NotFound:
            await interaction.response.send_message(
                "No banned user with that ID.", ephemeral=True
            )
            return
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to unban.", ephemeral=True
            )
            return

        await interaction.response.send_message(f"Unbanned **{user}**.")

    # -----------------------------------------------------------------
    # Purge
    # -----------------------------------------------------------------

    @app_commands.command(name="purge", description="Bulk-delete recent messages")
    @app_commands.describe(
        amount="How many messages to delete (1-100)",
        member="Only delete messages from this member",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def purge(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100],
        member: Optional[discord.Member] = None,
    ) -> None:
        # Deleting can take a few seconds, which is longer than Discord's
        # 3-second window to reply — so acknowledge first, answer later.
        await interaction.response.defer(ephemeral=True)

        def matches(message: discord.Message) -> bool:
            return member is None or message.author.id == member.id

        try:
            deleted = await interaction.channel.purge(limit=amount, check=matches)
        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have the **Manage Messages** permission here.", ephemeral=True
            )
            return

        who = f" from {member.mention}" if member else ""
        await interaction.followup.send(
            f"Deleted **{len(deleted)}** message(s){who}.", ephemeral=True
        )

    # -----------------------------------------------------------------
    # Error handling for every command in this cog
    # -----------------------------------------------------------------

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            message = "You don't have permission to use that command."
        elif isinstance(error, app_commands.BotMissingPermissions):
            message = "I'm missing a permission I need for that."
        else:
            message = f"Something went wrong: `{type(error).__name__}`"

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
