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

        self.new_reason = discord.ui.TextInput(
            label=field_label,
            style=discord.TextStyle.paragraph,
            default=log_view.current_reason,
            max_length=2000,
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
        old_display = self.log_view.current_reason if self.log_view.current_reason else "—"
        new_display = new_reason_value if new_reason_value else "—"
        preview_embed.add_field(name="Current Message", value=old_display[:1024], inline=False)
        preview_embed.add_field(name="New Message", value=new_display[:1024], inline=False)

        confirm_view = ConfirmEditView(log_view=self.log_view, new_reason=new_reason_value)

        await interaction.response.send_message(
            embed=preview_embed,
            view=confirm_view,
            ephemeral=True,
        )


class ConfirmEditView(discord.ui.View):
    """Shown after the modal is submitted; nothing is changed until Confirm is pressed."""

    def __init__(self, log_view: "LogEditView", new_reason: str):
        super().__init__(timeout=300)
        self.log_view = log_view
        self.new_reason = new_reason

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, custom_id="modlog_edit_confirm")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.log_view.apply_edit(interaction, self.new_reason)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey, custom_id="modlog_edit_cancel")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Edit cancelled — the log was not changed.",
                                                  embed=None, view=None)
        self.stop()


class LogEditView(discord.ui.View):
    """
    Attached below a sent modlog embed (warn, mute, or any future command that
    builds an embed with a "Reason" field). Lets a moderator open a modal to
    edit the reason, preview the change, and only apply it on explicit Confirm.

    - modlog_entry: anything with an update_reason(new_reason) method, e.g.
      hf.ModlogEntry or a ModlogDictEntryRef wrapping a raw modlog dict.
    - field_label: the embed field name to treat as the editable reason
      (defaults to "Reason"; a "<field_label> (cont.)" field is handled too).
    - modal_title: the title shown on the edit modal.
    """

    def __init__(self, *, modlog_entry, message: discord.Message,
                base_embed: discord.Embed, current_reason: str,
                field_label: str = "Reason", modal_title: str = "Edit Reason"):
        super().__init__(timeout=None)
        self.modlog_entry = modlog_entry
        self.message = message
        self.base_embed = base_embed
        self.current_reason = current_reason
        self.field_label = field_label
        self.modal_title = modal_title

    @discord.ui.button(label="Edit", style=discord.ButtonStyle.blurple, custom_id="modlog_log_edit_button")
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            EditReasonModal(self, modal_title=self.modal_title, field_label=self.field_label)
        )

    async def apply_edit(self, interaction: discord.Interaction, new_reason: str):
        """Called only after the moderator clicks Confirm on the preview."""
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

        rebuilt = discord.Embed.from_dict(self.base_embed.to_dict())
        rebuilt.clear_fields()
        for field in fields_to_keep[:insert_at]:
            rebuilt.add_field(name=field.name, value=field.value, inline=field.inline)

        if len(new_reason) <= 1024:
            rebuilt.add_field(name=self.field_label, value=new_reason, inline=False)
        elif len(new_reason) <= 2048:
            rebuilt.add_field(name=self.field_label, value=new_reason[:1024], inline=False)
            rebuilt.add_field(name=f"{self.field_label} (cont.)", value=new_reason[1024:2048], inline=False)
        else:
            await interaction.response.edit_message(
                content=f"That {self.field_label.lower()} is too long ({len(new_reason)} characters). "
                        f"Please edit again with a message under 2048 characters.",
                embed=None, view=None,
            )
            return

        for field in fields_to_keep[insert_at:]:
            rebuilt.add_field(name=field.name, value=field.value, inline=field.inline)

        # Persist the new reason to the modlog storage, if the entry supports it.
        if hasattr(self.modlog_entry, "update_reason"):
            self.modlog_entry.update_reason(new_reason)

        self.current_reason = new_reason
        self.base_embed = rebuilt

        try:
            await self.message.edit(embed=rebuilt, view=self)
        except discord.HTTPException:
            pass

        await interaction.response.edit_message(
            content="✅ The log has been updated.", embed=None, view=None
        )


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
