"""Config messages whose buttons must survive a bot restart."""

import asyncio
import logging

import discord

from cogs.utils.BotUtils import bot_utils as utils


_ban_config_lock = asyncio.Lock()


def ban_subscribers(bot, guild_id: int) -> list[int]:
    subscriptions = bot.db['bansub']
    role_id = subscriptions.get('guild_to_role', {}).get(str(guild_id))
    if role_id is None:
        return []
    return [int(user_id) for user_id, roles in subscriptions.get('user_to_role', {}).items()
            if role_id in roles]


def ban_config_url(bot, guild_id: int) -> str | None:
    config = bot.db.get('persistent_embeds', {}).get('ban_subscriptions', {}).get(str(guild_id))
    if not config:
        return None
    return f"https://discord.com/channels/{guild_id}/{config['channel_id']}/{config['message_id']}"


def ban_here_enabled(bot, guild_id: int) -> bool:
    return bot.db['bansub'].get('here_enabled', {}).get(str(guild_id), True)


def ban_config_embed(bot, guild_id: int) -> discord.Embed:
    subscribers = ban_subscribers(bot, guild_id)
    names = " ".join(f"<@{user_id}>" for user_id in subscribers) or "No one yet."
    here_status = "On" if ban_here_enabled(bot, guild_id) else "Off"
    return discord.Embed(
        title="Cross-server ban alerts",
        description="Use the button below to add or remove yourself from the pings when someone banned "
                    f"in another server joins this server.\n\n**Currently pinged:** {names}\n**`@here` ping:** {here_status}",
        color=0x8013E0,
    )


class BanSubscriptionView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Subscribe / unsubscribe", style=discord.ButtonStyle.primary,
                       custom_id="rai:ban_subscriptions:toggle")
    async def toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        config = (self.bot.db.get('persistent_embeds', {}).get('ban_subscriptions', {})
                  .get(str(guild.id)) if guild else None)
        if not config or interaction.message.id != config['message_id']:
            await interaction.response.send_message("This subscription message is no longer active.", ephemeral=True)
            return

        subscriptions = self.bot.db['bansub']
        role_id = subscriptions.get('guild_to_role', {}).get(str(guild.id))
        if role_id is None:
            await interaction.response.send_message("Ban alert subscriptions are not configured for this server.",
                                                    ephemeral=True)
            return

        users = subscriptions.setdefault('user_to_role', {})
        user_id = str(interaction.user.id)
        roles = users.setdefault(user_id, [])
        if role_id in roles:
            roles.remove(role_id)
            if not roles:
                del users[user_id]
            result = "You will no longer be pinged for cross-server ban alerts here."
        else:
            roles.append(role_id)
            result = "You will be pinged for cross-server ban alerts here."
        try:
            await interaction.response.send_message(result, ephemeral=True)
        except discord.HTTPException:
            logging.exception("Could not acknowledge ban subscription for user %s", user_id)
        try:
            await interaction.message.edit(embed=ban_config_embed(self.bot, guild.id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            logging.exception("Could not refresh ban subscription config for guild %s", guild.id)


    @discord.ui.button(label="Enable / disable @here", style=discord.ButtonStyle.secondary,
                       custom_id="rai:ban_subscriptions:toggle_here")
    async def toggle_here(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        config = (self.bot.db.get('persistent_embeds', {}).get('ban_subscriptions', {})
                  .get(str(guild.id)) if guild else None)
        if not config or interaction.message.id != config['message_id']:
            await interaction.response.send_message("This subscription message is no longer active.", ephemeral=True)
            return
        if not interaction.permissions.manage_guild:
            await interaction.response.send_message("You need Manage Server to change this setting.", ephemeral=True)
            return

        enabled = not ban_here_enabled(self.bot, guild.id)
        self.bot.db['bansub'].setdefault('here_enabled', {})[str(guild.id)] = enabled
        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(f"The `@here` ping is now {status}.", ephemeral=True)
        await interaction.message.edit(embed=ban_config_embed(self.bot, guild.id))


def restore_views(bot):
    for config in bot.db.get('persistent_embeds', {}).get('ban_subscriptions', {}).values():
        bot.add_view(BanSubscriptionView(bot), message_id=config['message_id'])


async def ensure_ban_config_message(bot, guild_id: int) -> str | None:
    """Create this guild's config message when its first alert needs a link."""
    key = str(guild_id)
    if key not in bot.db['bansub'].get('guild_to_role', {}):
        return None
    channel_id = bot.db['mod_channel'].get(key)
    channel = bot.get_channel(channel_id) if channel_id else None
    if not channel or channel.guild.id != guild_id:
        return None

    async with _ban_config_lock:
        configs = bot.db.setdefault('persistent_embeds', {}).setdefault('ban_subscriptions', {})
        current = configs.get(key)
        if current and current['channel_id'] == channel.id:
            try:
                message = await channel.fetch_message(current['message_id'])
                if not any(
                    getattr(button, 'custom_id', None) == 'rai:ban_subscriptions:toggle_here'
                    for row in message.components for button in row.children
                ):
                    await message.edit(embed=ban_config_embed(bot, guild_id), view=BanSubscriptionView(bot),
                                       allowed_mentions=discord.AllowedMentions.none())
                return ban_config_url(bot, guild_id)
            except discord.NotFound:
                pass
            except (discord.Forbidden, discord.HTTPException):
                return None

        try:
            message = await channel.send(embed=ban_config_embed(bot, guild_id), view=BanSubscriptionView(bot),
                                         allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.HTTPException):
            return None
        configs[key] = {'channel_id': channel.id, 'message_id': message.id}
        bot.add_view(BanSubscriptionView(bot), message_id=message.id)
        try:
            await utils.dump_json('db')
        except Exception:
            logging.exception("Could not save ban subscription config message for guild %s", guild_id)
        return ban_config_url(bot, guild_id)
