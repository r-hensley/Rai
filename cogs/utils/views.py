import asyncio
from copy import deepcopy

import discord
from discord.ext import commands

from .BotUtils import bot_utils as utils


SP_SERVER_ID = 243838819743432704
SP_PUBLIC_MOD_NOTIFICATION_CHANNEL_ID = 247135634265735168


def is_public_notification_channel(channel) -> bool:
    """Return whether a channel can safely hold a public moderation notice."""
    if isinstance(channel, (discord.TextChannel, discord.Thread)):
        return True
    if isinstance(channel, discord.abc.GuildChannel):
        return False

    # Preserve duck typing for lightweight Discord-compatible objects.
    return callable(getattr(channel, 'send', None))


def public_notification_channel(bot, guild: discord.Guild):
    """Resolve the configured public DM fallback, with the Spanish-server default."""
    modlog_config = bot.db.get('modlog', {}).get(str(guild.id), {})
    channel_id = modlog_config.get('warn_notification_channel')
    if not channel_id and guild.id == SP_SERVER_ID:
        channel_id = SP_PUBLIC_MOD_NOTIFICATION_CHANNEL_ID
    if not channel_id:
        return None

    try:
        channel_id = int(channel_id)
    except (TypeError, ValueError):
        return None
    channel = guild.get_channel_or_thread(channel_id)
    return channel if is_public_notification_channel(channel) else None


class PublicNotificationFallbackView(utils.RaiView):
    """Let the invoking moderator post a failed DM notification publicly."""

    def __init__(self, *, author, target, channel, embed: discord.Embed,
                 notification_label: str):
        super().__init__(timeout=60)
        self.author = author
        self.target = target
        self.channel = channel
        self.embed = embed.copy()
        self.notification_label = notification_label
        self.message = None
        self.handling = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user == self.author:
            return True
        await interaction.response.send_message(
            "Only the moderator who initiated this action can use these buttons.",
            ephemeral=True,
        )
        return False

    def disable_items(self):
        for item in self.children:
            item.disabled = True

    async def reject_if_handled(self, interaction: discord.Interaction) -> bool:
        if not self.handling and not self.is_finished():
            self.handling = True
            return False
        await interaction.response.send_message(
            "This public-delivery prompt has already been handled.",
            ephemeral=True,
        )
        return True

    @discord.ui.button(label="Send publicly", style=discord.ButtonStyle.green)
    async def send_publicly(self, interaction: discord.Interaction, _: discord.ui.Button):
        if await self.reject_if_handled(interaction):
            return
        await interaction.response.defer()

        public_text = (
            f"{self.target.mention}: Due to your privacy settings disabling messages from bots, "
            f"we are delivering this {self.notification_label} in a public channel. "
            "If you believe this to be an error, please contact a mod."
        )
        try:
            await utils.safe_send(self.channel, public_text, embed=self.embed)
        except (discord.Forbidden, discord.HTTPException) as exc:
            self.handling = False
            await interaction.followup.send(
                f"I couldn't post in {self.channel.mention}: `{exc}`. "
                "Fix Rai's Send Messages and Embed Links permissions there, then retry. "
                "To use another channel, cancel this prompt, run `;warn set`, and trigger "
                "a new notification.",
                ephemeral=True,
            )
            return

        self.disable_items()
        self.stop()
        await interaction.message.edit(
            content=(f"Sent the {self.notification_label} publicly in {self.channel.mention} "
                     f"for {self.target.mention}."),
            view=self,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        if await self.reject_if_handled(interaction):
            return
        await interaction.response.defer()
        self.disable_items()
        self.stop()
        await interaction.message.edit(
            content=f"I will not post the {self.notification_label} publicly for {self.target.mention}.",
            view=self,
        )

    async def on_timeout(self):
        self.handling = True
        self.disable_items()
        if self.message:
            try:
                await self.message.edit(
                    content=(f"Public delivery timed out; the {self.notification_label} for "
                             f"{self.target.mention} was not posted."),
                    view=self,
                )
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
        self.stop()


async def offer_public_notification_fallback(
        ctx: commands.Context,
        target: discord.Member,
        embed: discord.Embed,
        notification_label: str,
):
    """Offer a public notification when a moderator's DM could not be delivered."""
    channel = public_notification_channel(ctx.bot, ctx.guild)
    if not channel:
        await utils.safe_send(
            ctx,
            f"I could not DM {target.mention}, and no usable public fallback channel is configured. "
            "Use `;warn set #channel` to choose one.",
        )
        return None

    view = PublicNotificationFallbackView(
        author=ctx.author,
        target=target,
        channel=channel,
        embed=embed,
        notification_label=notification_label,
    )
    view.message = await utils.safe_send(
        ctx,
        f"I could not DM {target.mention}. Would you like to send the "
        f"{notification_label} publicly in {channel.mention}?",
        view=view,
    )
    return view


class ModlogDictEntryRef:
    """
    Adapter so LogEditView can update a raw modlog dict entry (as returned by
    the module-level hf.add_to_modlog function, e.g. used by mute()) the same
    way it updates an object that already has an update_reason() method
    (e.g. hf.ModlogEntry, used by warn()).
    """

    def __init__(self, entry_dict: dict):
        self._entry = entry_dict

    def update_reason(self, new_reason: str):
        if self._entry is None:
            return
        self._entry['reason'] = new_reason


class EditReasonModal(discord.ui.Modal):
    """Modal shown when a moderator clicks the Edit button on a modlog message."""

    def __init__(self, log_view: "LogEditView", *,
                modal_title: str = "Edit Reason", field_label: str = "Reason"):
        super().__init__(title=modal_title)
        self.log_view = log_view
        self.field_label = field_label
        self.original_reason = log_view.current_reason
        # Views sent before a utility reload can still use the old single-message class.
        state = getattr(log_view, "state", None)
        self.expected_revision = state.revision if state is not None else None

        self.new_reason = discord.ui.TextInput(
            label=field_label,
            style=discord.TextStyle.paragraph,
            default=log_view.current_reason,
            max_length=2048,
            required=True,
        )
        self.add_item(self.new_reason)

    async def on_submit(self, interaction: discord.Interaction):
        new_reason_value = str(self.new_reason.value)

        preview_embed = discord.Embed(
            title=f"Confirm Edited {self.field_label}",
            description="Review the change below. Nothing has been updated yet.",
            color=0x5865F2,
        )
        old_display = self.original_reason or "—"
        new_display = new_reason_value if new_reason_value else "—"
        preview_embed.add_field(name="Current Message", value=old_display[:1024], inline=False)
        preview_embed.add_field(name="New Message", value=new_display[:1024], inline=False)

        confirm_view = ConfirmEditView(
            log_view=self.log_view, new_reason=new_reason_value,
            expected_revision=self.expected_revision,
        )

        await interaction.response.send_message(
            embed=preview_embed,
            view=confirm_view,
            ephemeral=True,
        )


class ConfirmEditView(discord.ui.View):
    """Shown after the modal is submitted; nothing is changed until Confirm is pressed."""

    def __init__(self, log_view: "LogEditView", new_reason: str, *, expected_revision: int = None):
        super().__init__(timeout=300)
        self.log_view = log_view
        self.new_reason = new_reason
        self.expected_revision = expected_revision

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, custom_id="modlog_edit_confirm")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.expected_revision is None:
            await self.log_view.apply_edit(interaction, self.new_reason)
        else:
            await self.log_view.apply_edit(
                interaction, self.new_reason, expected_revision=self.expected_revision,
            )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey, custom_id="modlog_edit_cancel")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Edit cancelled — the log was not changed.",
                                                  embed=None, view=None)
        self.stop()


class LogEditState:
    """One moderation record shared by its confirmation and summary views."""

    def __init__(self, *, modlog_entry, base_embed: discord.Embed, current_reason: str):
        self.modlog_entry = modlog_entry
        self.base_embed = discord.Embed.from_dict(deepcopy(base_embed.to_dict()))
        self.current_reason = current_reason
        self.views: list[LogEditView] = []
        self.lock = asyncio.Lock()
        self.revision = 0


class LogEditView(discord.ui.View):
    """
    Attached below a sent modlog embed (warn, mute, or any future command that
    builds an embed with a "Reason" field). Lets a moderator open a modal to
    edit the reason, preview the change, and only apply it on explicit Confirm.

    - state: the moderation record and embed shared by all its message copies.
    - field_label: the embed field name to treat as the editable reason
      (defaults to "Reason"; a "<field_label> (cont.)" field is handled too).
    - modal_title: the title shown on the edit modal.
    """

    def __init__(self, *, state: LogEditState, message: discord.Message = None,
                field_label: str = "Reason", modal_title: str = "Edit Reason",
                permission_check=None,
                permission_error="You need permission to issue warnings to edit this log."):
        super().__init__(timeout=None)
        self.state = state
        self.message = message
        self.field_label = field_label
        self.modal_title = modal_title
        self.permission_check = permission_check
        self.permission_error = permission_error
        state.views.append(self)

    @property
    def base_embed(self):
        return self.state.base_embed

    @property
    def current_reason(self):
        return self.state.current_reason

    async def check_edit_permission(self, interaction: discord.Interaction) -> bool:
        # Other commands can supply their own authorization policy.
        from . import helper_functions as hf

        if self.permission_check:
            allowed = await self.permission_check(interaction)
        else:
            allowed = hf.trial_helper_check(interaction)
        if allowed:
            return True
        await interaction.response.send_message(
            self.permission_error,
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Edit", style=discord.ButtonStyle.blurple, custom_id="modlog_log_edit_button")
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_edit_permission(interaction):
            return
        await interaction.response.send_modal(
            EditReasonModal(self, modal_title=self.modal_title, field_label=self.field_label)
        )

    async def apply_edit(self, interaction: discord.Interaction, new_reason: str,
                         *, expected_revision: int = None):
        """Called only after the moderator clicks Confirm on the preview."""
        if not await self.check_edit_permission(interaction):
            return

        await interaction.response.defer()
        async with self.state.lock:
            if expected_revision is not None and expected_revision != self.state.revision:
                await interaction.edit_original_response(
                    content="This log changed while you were editing it. "
                            "Click Edit again to review the latest reason.",
                    embed=None, view=None,
                )
                return
            await self._apply_edit(interaction, new_reason)

    async def _apply_edit(self, interaction: discord.Interaction, new_reason: str):
        """Update the linked messages while holding the record's lock."""

        # Remove old "<field_label>" / "<field_label> (cont.)" fields, then insert
        # the new one(s) back in the same position.
        insert_at = None
        fields_to_keep = []
        for i, field in enumerate(self.base_embed.fields):
            if field.name and field.name.startswith(self.field_label):
                if insert_at is None:
                    insert_at = i
            else:
                fields_to_keep.append(field)
        if insert_at is None:
            insert_at = len(fields_to_keep)

        rebuilt = discord.Embed.from_dict(deepcopy(self.base_embed.to_dict()))
        rebuilt.clear_fields()
        for field in fields_to_keep[:insert_at]:
            rebuilt.add_field(name=field.name, value=field.value, inline=field.inline)

        if len(new_reason) <= 1024:
            rebuilt.add_field(name=self.field_label, value=new_reason, inline=False)
        elif len(new_reason) <= 2048:
            rebuilt.add_field(name=self.field_label, value=new_reason[:1024], inline=False)
            rebuilt.add_field(name=f"{self.field_label} (cont.)", value=new_reason[1024:2048], inline=False)
        else:
            await interaction.edit_original_response(
                content=f"That {self.field_label.lower()} is too long ({len(new_reason)} characters). "
                        f"Please edit again with a message under 2048 characters.",
                embed=None, view=None,
            )
            return

        for field in fields_to_keep[insert_at:]:
            rebuilt.add_field(name=field.name, value=field.value, inline=field.inline)

        updated = []
        seen = set()
        for linked_view in list(self.state.views):
            message = linked_view.message
            if message is None or message.id in seen:
                continue
            seen.add(message.id)
            try:
                # Preserve each message's distinct view and Discord registration.
                await message.edit(embed=rebuilt)
            except discord.NotFound:
                self.state.views.remove(linked_view)
                linked_view.stop()
            except discord.HTTPException:
                rollback_failed = False
                for previous_view in updated:
                    try:
                        await previous_view.message.edit(embed=self.base_embed)
                    except discord.NotFound:
                        self.state.views.remove(previous_view)
                        previous_view.stop()
                    except discord.HTTPException:
                        rollback_failed = True
                content = "I couldn't update every log message. The saved reason was not changed."
                if rollback_failed:
                    content += " I also couldn't restore some messages; their displayed reasons may be out of sync."
                await interaction.edit_original_response(content=content, embed=None, view=None)
                return
            else:
                updated.append(linked_view)

        if not updated:
            await interaction.edit_original_response(
                content="No log messages could be updated. The saved reason was not changed.",
                embed=None, view=None,
            )
            return

        # Commit only after all remaining copies have accepted the edit.
        if hasattr(self.state.modlog_entry, "update_reason"):
            self.state.modlog_entry.update_reason(new_reason)

        self.state.current_reason = new_reason
        self.state.base_embed = rebuilt
        self.state.revision += 1

        await interaction.edit_original_response(
            content="✅ The log has been updated.", embed=None, view=None
        )


class BanLogEditState(LogEditState):
    """A single-user ban, awaiting its saved record and ban-event summary."""

    def __init__(self, *, base_embed, current_reason, helper_role_id=None):
        super().__init__(modlog_entry=None, base_embed=base_embed, current_reason=current_reason)
        self.helper_role_id = helper_role_id


def register_pending_ban_edit(bot, guild_id: int, user_id: int, state: BanLogEditState):
    pending = getattr(bot, "pending_ban_edits", None)
    if pending is None:
        pending = bot.pending_ban_edits = {}
    key = (guild_id, user_id)
    pending[key] = state

    def expire():
        if pending.get(key) is state:
            pending.pop(key)

    # The event normally arrives immediately; do not retain failed/missing events.
    asyncio.get_running_loop().call_later(90, expire)
    return expire


class BanLogEditView(LogEditView):
    async def check_edit_permission(self, interaction: discord.Interaction) -> bool:
        from . import helper_functions as hf

        if hf.admin_check(interaction):
            return True
        role_id = self.state.helper_role_id
        if role_id and interaction.guild and hf.submod_check(interaction):
            role = interaction.guild.get_role(role_id)
            if role and role in interaction.user.roles:
                return True
        await interaction.response.send_message(
            "You need permission to moderate this ban to edit its log.", ephemeral=True,
        )
        return False


class PaginationView(discord.ui.View):
    """Generic paginated embed view with ◄/►/✖ buttons."""

    def __init__(self, embeds, author, timeout=60):
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.author = author
        self.current_page = 0
        self.message = None
        self.update_buttons()

    def update_buttons(self):
        self.prev_button.disabled = self.current_page == 0
        self.page_indicator.label = f"{self.current_page + 1}/{len(self.embeds)}"
        self.next_button.disabled = self.current_page == len(self.embeds) - 1

    @discord.ui.button(label="◄", style=discord.ButtonStyle.blurple)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("You cannot control this menu.", ephemeral=True)
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.gray, disabled=True)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="►", style=discord.ButtonStyle.blurple)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("You cannot control this menu.", ephemeral=True)
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="✖", style=discord.ButtonStyle.red)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()
        self.stop()

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.NotFound:
                pass
        self.stop()
