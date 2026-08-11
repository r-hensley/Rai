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
