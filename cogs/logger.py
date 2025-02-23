import time
from collections import deque

import aiohttp.client_exceptions
import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta, timezone
from Levenshtein import distance as LDist
import re
from .utils import helper_functions as hf
from cogs.utils.BotUtils import bot_utils as utils

from typing import Optional, List, Tuple, Dict, Union

import os

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
JP_SERV_ID = 189571157446492161
SPAN_SERV_ID = 243838819743432704
M_SERVER = 257984339025985546
NADEKO_ID = 116275390695079945
SPAN_WELCOME_CHAN_ID = 243838819743432704
JP_SERV_JHO_ID = 189571157446492161
BANS_CHANNEL_ID = 329576845949534208
ABELIAN_ID = 414873201349361664


class Logger(commands.Cog):
    """Logs stuff"""

    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.bot.recently_removed_members = {}

    async def cog_check(self, ctx):
        if not ctx.guild:
            return
        if str(ctx.guild.id) not in self.bot.db['mod_channel'] and ctx.command.name != 'set_mod_channel':
            return
        return hf.admin_check(ctx)

    # ############### general functions #####################

    @commands.group(aliases=['logging'])
    async def logs(self, ctx):
        """The top-level command for the logging module. All configuration can be done starting here."""
        modules = sorted([self.edits, self.deletes, self.joins, self.leaves, self.reactions, self.bans, self.kicks,
                          self.nicknames, self.voice], key=lambda x: x.name)
        emb_desc = "This is the module for logging various server events. The current module settings are below:"
        emb = discord.Embed(description=emb_desc, color=0x77dbf7)
        emb_value = "**ENABLED MODULES**\nThe following are the currently enabled modules and the respective " \
                    "log channels they're associated with."

        disabled_modules = []
        guild_id = str(ctx.guild.id)
        for module in modules:
            try:
                if self.bot.db[module.name][guild_id]['enable']:
                    config = self.bot.db[module.name][guild_id]
                else:
                    raise KeyError
            except KeyError:
                disabled_modules.append(module)
                continue
            emb_value += (f"\n\n・{module.name.capitalize()} "
                          f"{ctx.guild.get_channel_or_thread(config['channel']).mention})")
            if module.name == 'edits':
                emb_value += f"\n[Levenshtein limit](https://github.com/ryry013/Rai/wiki/Rai-Info-Pages#" \
                             f"levenshtein-distance-limit): {config.get('distance_limit', False)}"
            if module.name == 'joins':
                emb_value += "\n[Invite tracking](https://github.com/ryry013/Rai/wiki/Rai-Info-Pages#invite-tracking)" \
                             f": {config.get('invites_enable', False)}"
                emb_value += "\n[Save previous roles](https://github.com/ryry013/Rai/wiki/Rai-Info-Pages" \
                             f"#save-previous-roles): {config.get('readd_roles', {'enable': False})['enable']}"
            if module.name == 'bans' and ctx.author in self.bot.get_guild(257984339025985546).members:
                emb_value += f"\n[Ban crossposting](https://discordapp.com/channels/257984339025985546/" \
                             f"329576845949534208/603019430536151041): {config.get('crosspost', False)}"

        emb.add_field(name=f"**__{'　' * 30}__**", value=emb_value, inline=False)

        emb_value = "**DISABLED MODULES**\nThe following are the currently disabled modules."
        for module in disabled_modules:
            emb_value += f"\n・`{module.name}` ― {module.brief}"
            emb.add_field(name=f"**__{'　' * 30}__**", value=emb_value, inline=False)

        emb_value = "**TO EDIT SETTINGS**\nTo enable/disable a module, type just the module name as a command. \n" \
                    "- Examples: `;joins`   `;edits`   `leaves`\n" \
                    "To set where that channel logs to, add `set` to the command.\n" \
                    "- Examples: `joins set`   `;edits set`   `;leaves set`"
        emb.add_field(name=f"**__{'　' * 30}__**", value=emb_value, inline=False)
        await utils.safe_send(ctx, embed=emb)

    @logs.command()
    async def set(self, ctx, module):
        """Sets the logging channel for a module"""

    @logs.command(aliases=['toggle'])
    async def enable(self, ctx, module):
        pass

    @logs.command()
    async def edits(self, ctx):
        """Log when users edit messages"""
        pass

    @staticmethod
    async def module_logging(ctx, module):
        guild = str(ctx.guild.id)
        if guild in module:
            guild_config: dict = module[guild]
            if guild_config['enable']:  # if the guild has enabled logging
                guild_config['enable'] = False
                result = 1
            else:
                if guild_config['channel']:
                    guild_config['enable'] = True
                    result = 2
                else:
                    result = 3
        else:  # first time register for a new guild
            module[guild] = {"enable": False, "channel": ""}
            result = 4
        return result

    @staticmethod
    async def module_set(ctx, module):
        guild = str(ctx.guild.id)
        if guild in module:  # server already registered
            guild_config: dict = module[guild]
            guild_config['channel'] = ctx.channel.id
            result = 1
        else:  # new server
            module[guild] = {"enable": True, "channel": ctx.channel.id}
            result = 2
        return result

    async def module_disable_notification(self, guild, guild_config, module_name):
        try:
            channel = self.bot.db['mod_channel'][str(guild.id)]
        except KeyError:
            pass
        else:
            channel = self.bot.get_channel(channel)
            await utils.safe_send(channel, f"Disabled the {module_name} logs due to Rai possibly lacking some permission "
                                        f"(possibly `Send Messages`, `Embed Links`, or for bans, `View Audit Log`)")
        finally:
            guild_config['enable'] = False

    # ############### voice channel joins/changes/leaves #####################

    @commands.group(invoke_without_command=True, name='voice')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def voice(self, ctx):
        """Logs edited messages"""
        result = await self.module_logging(ctx, self.bot.db['voice'])
        if result == 1:
            await utils.safe_send(ctx, 'Disabled voice logging for this server')
        elif result == 2:
            await utils.safe_send(ctx, 'Enabled voice logging for this server. Embeds have a secret ID '
                                    'inside of that you can find by searching the user ID with "V" in front (like '
                                    '`V202995638860906496`).')
        elif result == 3:
            await utils.safe_send(ctx, 'You have not yet set a channel for voice logging yet. Run `;voice_logging set`')
        elif result == 4:
            await utils.safe_send(ctx, 'Before doing this, set a channel for logging with `;voice_logging set`.  '
                                    'Then, enable/disable logging by typing `;voice_logging`.')

    @voice.command(name='set')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def voice_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['voice'])
        if result == 1:
            await utils.safe_send(ctx, f'Set the voice logging channel as {ctx.channel.name}')
        elif result == 2:
            await utils.safe_send(ctx, f'Enabled voice logging and set the channel to `{ctx.channel.name}`.  '
                                    f'Enable/disable logging by typing `;voice_logging`. Embeds have a secret ID '
                                    f'inside of that you can find by searching the user ID with "V" in front (like '
                                    f'`V202995638860906496`).')

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                    before: discord.VoiceState,
                                    after: discord.VoiceState):
        guild = str(member.guild.id)
        
        t_start = time.perf_counter()
        t_start = hf.line_profile(t_start, "on_voice_state_update")
        if guild in self.bot.db['voice']:
            guild_config: dict = self.bot.db['voice'][guild]
            if not guild_config['enable'] or not guild_config['channel']:
                guild_config = {}
        else:
            guild_config = {}

        try:
            await hf.wait_for('voice_state_update',
                              'voice_state_update',
                              timeout=0.5,
                              check=lambda m, b, a: m == member)
            return
        except asyncio.TimeoutError:
            pass

        description = color = footer_text = None

        try:
            config = self.bot.db['super_voicewatch'][str(member.guild.id)]
            channel = self.bot.get_channel(config['channel'])
        except KeyError:
            config = channel = None

        if not config and not guild_config:
            return

        ###################################
        # join, leave, switching channels
        ###################################

        # joins voice ➡️ 3B88C3
        if not before.channel and after.channel:
            description = f"➡️ **{str(member)}** has `joined` **#{after.channel.name}**."
            color = 0x3B88C3
            footer_text = "Voice Join"
            if after.channel.guild.id == 243838819743432704:
                # self.bot.db['spvoice'].append(("Join",
                # discord.utils.utcnow().timestamp(),
                # member.id, after.channel.id))
                pass

        # leave voice  DD2E44
        elif before.channel and not after.channel:
            description = f"❌ **{str(member)}** has `left` **#{before.channel.name}**."
            color = 0xDD2E44
            footer_text = "Voice Leave"
            if before.channel.guild.id == 243838819743432704:
                # self.bot.db['spvoice'].append(("Leave",
                # discord.utils.utcnow().timestamp(),
                # member.id, before.channel.id))
                pass

        # switch channel 🔄️ 3B88C3
        elif before.channel and after.channel and before.channel != after.channel:
            description = f"🔄 **{str(member)}** has `switched` from " \
                          f"**#{before.channel.name}** to **#{after.channel.name}**."
            color = 0x3B88C3
            footer_text = "Voice Switch"
            if after.channel.guild.id == 243838819743432704:
                # self.bot.db['spvoice'].append(("Leave",
                # discord.utils.utcnow().timestamp(),
                # member.id, before.channel.id))
                # self.bot.db['spvoice'].append(("Join",
                # discord.utils.utcnow().timestamp(),
                # member.id, after.channel.id))
                pass

        ############################
        # streaming / broadcasting
        ############################

        # start self_stream 📳 F4900C
        elif not before.self_stream and after.self_stream:
            description = f"📳 **{str(member)}** has went LIVE and started streaming."
            color = 0xF4900C
            footer_text = "Stream Start"

        # stop self_stream 🔇 CCD6DD
        elif before.self_stream and not after.self_stream:
            description = f"🔇 **{str(member)}** has stopped streaming."
            color = 0xCCD6DD
            footer_text = "Stream Stop"

        # start self_video 📳 F4900C
        elif not before.self_video and after.self_video:
            description = f"**{str(member)}** has turned on their camera."
            color = 0xF4900C
            footer_text = "Video Start"

        # stop self_video 🔇 CCD6DD
        elif before.self_video and not after.self_video:
            description = f"🔇 **{str(member)}** has turned off their camera."
            color = 0xCCD6DD
            footer_text = "Video Stop"

        if not description:  # just in case some case slipped through
            return

        footer_text = f"V{member.id} - " + footer_text

        emb = discord.Embed(description=description, color=color, timestamp=discord.utils.utcnow())
        emb.set_footer(text=footer_text,
                       icon_url=member.display_avatar.replace(static_format="png").url)
        
        t_start = hf.line_profile(t_start, "on_voice_state_update: embed construction", offset=0.5)

        if after.channel:
            users_in_voice = ""
            needed_two_fields = False

            if isinstance(after.channel, discord.StageChannel):
                name_text = "Current stage channel speakers"
            else:
                name_text = "Users currently in joined voice channel"

            for user in after.channel.members:
                if user.voice.suppress:  # a listener in a stage channel
                    pass
                text_to_add = f"\n- [{str(user)}"
                if user.nick:
                    text_to_add += f" ({user.nick})"
                text_to_add += f"](https://rai/participant-id-is-P{user.id})"

                # Check to make sure the total length of the embed isn't going over 6000, cut off if so
                if (len(emb) + len(name_text) + len(users_in_voice) + len(text_to_add)) > 6000:
                    users_in_voice += "\n[...]"
                    break
                if len(users_in_voice + text_to_add) < 1024:
                    users_in_voice += text_to_add
                else:
                    if needed_two_fields:
                        emb.add_field(name="User list (cont.)", value=users_in_voice)
                    else:
                        emb.add_field(name=name_text, value=users_in_voice)
                    users_in_voice = text_to_add
                    needed_two_fields = True

            if needed_two_fields:
                emb.add_field(name="User list (cont.)", value=users_in_voice)
            else:
                emb.add_field(name=name_text, value=users_in_voice)
                
        t_start = hf.line_profile(t_start, "on_voice_state_update: user list")

        """Voice logging"""
        if guild_config:
            try:
                await utils.safe_send(self.bot.get_channel(guild_config['channel']), embed=emb)
                t_start = hf.line_profile(t_start, "on_voice_state_update: send to guild channel")
            except (discord.DiscordServerError, aiohttp.client_exceptions.ClientOSError):
                await hf.sleep("voice_state_update", 3, add=True)
                try:
                    await utils.safe_send(self.bot.get_channel(guild_config['channel']), embed=emb)
                except discord.DiscordServerError:
                    pass
        
        t_start = hf.line_profile(t_start, "on_voice_state_update: voice logging")

        """ Super voice watch"""
        if config:
            b = before.channel
            a = after.channel
            if a and not b:
                if member.id in config['users']:
                    try:
                        await utils.safe_send(channel, member.id, embed=emb)
                    except discord.Forbidden:
                        pass

                five_hours_in_seconds = 60 * 60 * 30
                if (discord.utils.utcnow() - member.created_at).total_seconds() < five_hours_in_seconds:
                    emb.description += "\n(Newly created account joining voice):"
                    emb.description += f"\nCreation date: <t:{int(member.created_at.timestamp())}>"
                    emb.description += f"\nJoin date: <t:{int(member.joined_at.timestamp())}>"
                    if hf.calculate_voice_time(member.id, member.guild.id) < 60 * 60:  # 60 mins
                        try:
                            await utils.safe_send(channel, member.id, embed=emb)
                        except discord.Forbidden:
                            pass
        
        t_start = hf.line_profile(t_start, "on_voice_state_update: super voice watch")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        """For use with voice_logging if someone creates a private voice channel"""
        guild = str(channel.guild.id)
        if guild in self.bot.db['voice']:
            guild_config: dict = self.bot.db['voice'][guild]
            if not guild_config['enable'] or not guild_config['channel']:
                return
        else:
            return

        description = f"⤴ **#{channel.name}** has been created."
        color = 0x00FFFF  # slightly lighter blue than the "joined" blue
        footer_text = f"{channel.id} - Channel Creation"

        emb = discord.Embed(description=description, color=color, timestamp=discord.utils.utcnow())
        emb.set_footer(text=footer_text)
        await utils.safe_send(self.bot.get_channel(guild_config['channel']), embed=emb)

    # ############### edits #####################

    @commands.group(invoke_without_command=True, name='edits')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def edit_logging(self, ctx):
        """Logs edited messages"""
        result = await self.module_logging(ctx, self.bot.db['edits'])
        if result == 1:
            await utils.safe_send(ctx, 'Disabled edit logging for this server')
        elif result == 2:
            await utils.safe_send(ctx, 'Enabled edit logging for this server')
        elif result == 3:
            await utils.safe_send(ctx, 'You have not yet set a channel for edit logging yet. Run `;edit_logging set`')
        elif result == 4:
            self.bot.db['edits'][str(ctx.guild.id)]['distance_limit'] = 3
            await utils.safe_send(ctx, 'Before doing this, set a channel for logging with `;edit_logging set`.  '
                                    'Then, enable/disable logging by typing `;edit_logging`.')

    @edit_logging.command(name='set')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def edits_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['edits'])
        if result == 1:
            await utils.safe_send(ctx, f'Set the edit logging channel as {ctx.channel.name}')
        elif result == 2:
            self.bot.db['edits'][str(ctx.guild.id)]['distance_limit'] = 3
            await utils.safe_send(ctx, f'Enabled edit logging and set the channel to `{ctx.channel.name}`.  '
                                    f'Enable/disable logging by typing `;edit_logging`.')

    @edit_logging.command(aliases=['set_distance'])
    async def distance_set(self, ctx, distance_limit: int = 3):
        """Sets the Levenshtein Distance limit for edited messages logs. Anything below this limit won't get counted\
        as an edit (the Levenshtein Distance measures the distance between strings)."""
        guild = str(ctx.guild.id)
        guild_config: dict = self.bot.db['edits'][guild]
        guild_config['distance_limit'] = distance_limit
        await utils.safe_send(ctx, f'Successfully set Levenshtein Distance limit to {distance_limit}.')

    @staticmethod
    async def log_edit_event(before: discord.Message, after, levenshtein_distance: int, channel: discord.abc.Messageable):
        author = before.author
        time_dif = round((discord.utils.utcnow() - before.created_at).total_seconds(), 1)
        time_dif_str = hf.format_interval(time_dif, show_seconds=True, include_spaces=True)
        emb = discord.Embed(
            description=f'**{str(author)}** (M{author.id})'
                        f'\n**Message edited after {time_dif_str}.** [(LD={levenshtein_distance})]'
                        f'(https://en.wikipedia.org/wiki/Levenshtein_distance) - ([Jump URL]({after.jump_url}))',
            colour=0xFF9933,
            timestamp=discord.utils.utcnow()
        )
        
        emb.set_footer(text=f'#{before.channel.name}',
                       icon_url=before.author.display_avatar.replace(static_format="png").url)
   
        # try to remove text from beginning or end in the case that the embed is long
        iteration_counter = 0
        before_content = before.content
        after_content = after.content
        while len(emb) + len(before_content) + len(after_content) > 5900:
            iteration_counter += 1
            if iteration_counter == 20:
                raise ValueError("Infinite loop")  # infinite loop
            if before_content[:100] == after_content[:100]:
                before_content = "[...] " + before_content[100:]
                after_content = "[...] " + after_content[100:]
                continue
            elif before_content[-100:] == after_content[-100:]:
                before_content = before_content[:-100] + " [...]"
                after_content = after_content[:-100] + " [...]"
                continue
            else:
                break
                    
        before_str_segments = utils.split_text_into_segments(before_content, 1024)
        after_str_segments = utils.split_text_into_segments(after_content, 1024)
        for i in range(len(before_str_segments)):
            if i == 0:
                emb.add_field(name=f'**Before:**', value=before_str_segments[i])
            else:
                emb.add_field(name=f'**Before:** (Part {i+1})', value=before_str_segments[i])
        for i in range(len(after_str_segments)):
            if i == 0:
                emb.add_field(name=f'**After:**', value=after_str_segments[i])
            else:
                emb.add_field(name=f'**After:** (Part {i+1})', value=after_str_segments[i])
        
        iteration = 0
        while len(emb) > 6000:
            iteration += 1
            if iteration == 20:
                raise ValueError("Infinite loop")  # infinite loop
            emb.remove_field(0)
        await utils.safe_send(channel, embed=emb)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if isinstance(before.channel, discord.DMChannel):
            return
        if not before.guild:
            return

        # exempt a certain channel from logging by the request of the mods of that server
        if after.channel.id == 243858886266847233:
            return

        guild = str(before.guild.id)
        if not before.author.bot:
            if guild in self.bot.db['edits']:
                guild_config: dict = self.bot.db['edits'][guild]
                if guild_config['enable']:
                    try:
                        distance_limit = guild_config["distance_limit"]
                    except KeyError:
                        channel = self.bot.get_channel(guild_config["channel"])
                        if not channel:
                            return
                        await utils.safe_send(channel, 'Please set a Levenshtein Distance with `;edit set_distance 3`')
                        return
                    levenshtein_distance = LDist(before.content, after.content)
                    if levenshtein_distance > distance_limit:
                        channel = self.bot.get_channel(guild_config["channel"])
                        try:
                            await self.log_edit_event(before, after, levenshtein_distance, channel)
                        except discord.Forbidden:
                            return
        await hf.uhc_check(after)

    # ############### deletes #####################

    @commands.group(invoke_without_command=True)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def deletes(self, ctx):
        """Logs deleted messages"""
        result = await self.module_logging(ctx, self.bot.db['deletes'])
        if result == 1:
            await utils.safe_send(ctx, 'Disabled delete logging for this server')
        elif result == 2:
            await utils.safe_send(ctx, 'Enabled delete logging for this server')
        elif result == 3:
            await utils.safe_send(ctx, 'You have not yet set a channel for delete logging yet. Run `;delete_logging set`')
        elif result == 4:
            await utils.safe_send(ctx, 'Before doing this, set a channel for logging with `;delete_logging set`.  '
                                    'Then, enable/disable logging by typing `;delete_logging`.')

    @deletes.command(name='set')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def deletes_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['deletes'])
        if result == 1:
            await utils.safe_send(ctx, f'Set the delete logging channel as {ctx.channel.name}')
        elif result == 2:
            await utils.safe_send(ctx,
                               f'Enabled delete logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                               f' logging by typing `;delete_logging`.')

    async def log_delete_event(self, message: discord.Message, channel: discord.abc.Messageable):
        author = message.author
        time_dif = round((discord.utils.utcnow() - message.created_at).total_seconds(), 1)
        time_dif_str = hf.format_interval(time_dif, show_seconds=True, include_spaces=True)
        jump_url = ''
        if hasattr(message.channel, "history"):
            try:
                async for msg in message.channel.history(limit=1, before=message):
                    jump_url = msg.jump_url
            except discord.NotFound:
                pass  # somehow got discord.errors.NotFound: 404 Not Found (error code: 10003): Unknown Channel
            except asyncio.TimeoutError:
                # rare timeout from discord API, just try again once
                async for msg in message.channel.history(limit=1, before=message):
                    jump_url = msg.jump_url
        emb = discord.Embed(
            description=f'**{str(author)}** (M{author.id})'
                        f'\n**Message deleted after {time_dif_str}.** ([Jump URL]({jump_url}))',
            colour=0xDB3C3C,
            timestamp=discord.utils.utcnow()
        )

        if message.content:
            if len(message.content) < 1025:
                emb.add_field(name='**Message:**', value=message.content)
            else:
                emb.add_field(name='**Message:** (Part 1):', value=message.content[:1000])
                emb.add_field(name='**Message:** (Part 2):', value=message.content[1000:2000])

        if message.attachments:
            list_of_attachments = []
            attachment_names = []
            file_bool = False  # marks if someone uploaded a non-picture file

            for attachment in message.attachments:
                list_of_attachments.append(attachment.proxy_url)
                if attachment.filename.split('.')[-1].casefold() not in ['jpg', 'jpeg', 'png', 'gif',
                                                                         'apng', 'tiff', 'mov', 'mp4']:
                    attachment_names.append(attachment.filename)
                    file_bool = True
                    continue

            if file_bool:
                emb.add_field(name='**File Attachments:**', value='\n'.join(attachment_names))

        emb.set_footer(text=f'#{message.channel.name}',
                       icon_url=message.author.display_avatar.replace(static_format="png").url)
        
        log_message = await utils.safe_send(channel, embed=emb)
        await hf.send_attachments_to_thread_on_message(log_message, message)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not hasattr(self.bot, "deletion_tracker"):
            self.bot.deletion_tracker = deque(maxlen=20)
        self.bot.deletion_tracker.append(message.id)

        if not message.guild or message.author.bot:
            return
        guild = str(message.guild.id)
        guild_config: dict = self.bot.db['deletes'].get(guild, {'enable': False})
        if not guild_config['enable']:
            return

        # exempt a certain channel from logging by the request of the mods of that server
        if message.channel.id == 243858886266847233:
            return

        try:
            channel = self.bot.get_channel(guild_config["channel"])
        except KeyError:
            del self.bot.db['deletes'][guild]
            return
        if not channel:
            del self.bot.db['deletes'][guild]
            return

        try:
            await self.log_delete_event(message, channel)
        except discord.Forbidden:
            # await self.module_disable_notification(message.guild, guild_config, 'message deletes')
            pass

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        await hf.sleep("raw_message_delete", 0.2)  # to give on_message_delete time to potentially add a message to the deletion_tracker
        if payload.message_id in getattr(self.bot, "deletion_tracker", []):
            return
        await self.log_raw_payload(payload)
        
    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        await self.log_raw_payload(payload)

    async def log_raw_payload(self, payload: Union[discord.RawMessageDeleteEvent, discord.RawMessageUpdateEvent]):
        """This is going to be the real version of new_log_raw_payload. The function above is almost completley
        just debug stuff.

        Ignore bot messages, messages in DMs, and messages in the message cache.

        Messages that are sent and immediately deleted by a bot will be removed from the message cache by Discord.py
        so searching for them in the message cache won't work. The solution to avoid that is to ignore messages that
        are less than five seconds old since deletion."""
        if isinstance(payload, discord.RawMessageUpdateEvent):
            event_type = "edits"
        elif isinstance(payload, discord.RawMessageDeleteEvent):
            event_type = "deletes"
        else:
            raise ValueError("Invalid payload type")
        
        # ignore messages in DMs
        if not payload.guild_id:
            return
        
        # ignore guilds that have this kind of logging disabled
        guild_id_str = str(payload.guild_id)
        try:
            if not self.bot.db[event_type][guild_id_str]['enable']:
                return
        except KeyError:
            return
        
        # if message is in bot_message_queue, ignore it
        bot_message_queue = getattr(self.bot, 'bot_message_queue', None)
        if bot_message_queue:
            bot_message_list = bot_message_queue.find(payload.message_id)
            if bot_message_list:
                return # ignore bot messages
        
        # ignore edits that don't have an edited_timestamp
        original_timestamp = discord.utils.snowflake_time(payload.message_id)
        if event_type == "edits":
            if not payload.data.get('edited_timestamp', None):
                return
                
        # for bot messages: if message is in bot.cached_messages, ignore it here
        for msg in self.bot.cached_messages:
            if msg.id == payload.message_id:
                return
            
        guild_config: dict = self.bot.db[event_type][guild_id_str]
        logging_channel = self.bot.get_channel(int(guild_config['channel']))
        if not logging_channel:
            return
        
        # try to get old message from bot.message_queue
        mini_message_list: list[hf.MiniMessage] = self.bot.message_queue.find(payload.message_id)
        if mini_message_list:
            old_message = mini_message_list[0]
        else:
            if event_type == "deletes":
                age = hf.format_interval(discord.utils.utcnow() - original_timestamp, show_seconds=True)
                emb = utils.red_embed(f"**A message was deleted.** This is all I know:\n")
                
                # check if the message that wasn't found was within the queue's depth
                if self.bot.message_queue[0].created_at < original_timestamp:
                    # this message theoretically should've been in the queue
                    # if it's not, that means it's most likely a bot message, so it wasn't recorded
                    emb.description += f"*(it's possible this was an old bot message that was deleted)*\n"
                emb.description += (f"Message ID: {payload.message_id}\n"
                                      f"Channel ID: {payload.channel_id}\n"
                                      f"Approximate link: https://discord.com/channels/"
                                      f"{logging_channel.guild.id}/{payload.channel_id}/{payload.message_id}")
                emb.timestamp = original_timestamp
                emb.set_footer(text=f"{age} ago")
                await utils.safe_send(logging_channel, embed=emb)
                return
            else:  # edits
                # there's weird events where messages from like 1000's of days in the past get edited randomly
                # I think it's discord reloading the embeds for some reason
                # so if the edited timestamp is more than 10 seconds in the past, ignore it
                # discord sends timestamps in ISO 8601 format
                timestamp_iso_string: str = payload.data['edited_timestamp']
                edited_timestamp: datetime = discord.utils.parse_time(timestamp_iso_string)
                if (discord.utils.utcnow() - edited_timestamp).total_seconds() > 10:
                    content = "<Old message content not known> (potentially no change)"
                else:
                    content = "<Old message content not known>"
                author_id = payload.data['author']['id']
                author = self.bot.get_user(int(author_id))
                if not author:
                    try:
                        author = await self.bot.fetch_user(author_id)
                    except discord.NotFound:
                        return
                if author.bot:
                    return
                old_message = hf.MiniMessage(message_id=payload.message_id,
                                             content=content,
                                             author_id=payload.data['author']['id'],
                                             channel_id=payload.channel_id,
                                             guild_id=payload.guild_id)
                if not hasattr(self.bot, "after_edit_content"):
                    self.bot.after_edit_content = []
                self.bot.after_edit_content.append(payload.data)
                
            
        # for a deleted message event, old_message is the message that was deleted
        # for a message edit event, old_message is the message before the edit
        if event_type == "deletes":
            old_message_dmsg = old_message.to_discord_message()
            await self.log_delete_event(old_message_dmsg, logging_channel)
            
        elif event_type == "edits":
            # get the new message from the cache
            message_guild = self.bot.get_guild(payload.guild_id)
            message_channel = message_guild.get_channel_or_thread(payload.channel_id) if message_guild else None
            try:
                new_message = await message_channel.fetch_message(payload.message_id)
            except discord.NotFound:
                return
            distance_limit = guild_config.get("distance_limit", 3)
            levenshtein_distance = LDist(old_message.content, new_message.content)
            if levenshtein_distance > distance_limit or levenshtein_distance == 0:
                await self.log_edit_event(old_message.to_discord_message(), new_message, levenshtein_distance, logging_channel)
            
    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        if not payload.guild_id:
            return
        guild = str(payload.guild_id)

        try:
            if not self.bot.db['deletes'][guild]['enable']:
                return
        except KeyError:
            return

        guild_config: dict = self.bot.db['deletes'][guild]
        channel = self.bot.get_channel(int(guild_config['channel']))
        if not channel:
            del (guild_config['channel'])
            return

        message_channel = self.bot.get_channel(payload.channel_id)
        cached = [m.id for m in payload.cached_messages]
        uncached = [m for m in payload.message_ids if m not in cached]
        cached_authors = {m.author for m in payload.cached_messages}

        if payload.cached_messages:
            if message_channel:
                text = f"Deleted {len(payload.cached_messages)} messages from #{message_channel.name} " \
                       f"({message_channel.id}) (times are in UTC)\n"
            else:
                text = f"Deleted {len(payload.cached_messages)} messages from <#{payload.channel_id}> " \
                       f"(times are in UTC)\n"

            msgs = sorted(list(payload.cached_messages), key=lambda m: m.id)
            text = hf.message_list_to_text(msgs, text)
            file = hf.text_to_file(text, f"{payload.channel_id}_{msgs[0].id}-{msgs[-1].id}_messages.txt")

            # Reset text variable, start building text for embed
            text = f"**{len(msgs)}** messages have been cleared from <#{payload.channel_id}> and logged above.\n" \
                   f"This file contains messages from the following authors:"
            for author in cached_authors:
                addition = f"\n- M{author.id} ({str(author)})"
                addition += f" **x{len([m for m in payload.cached_messages if m.author == author])}**"
                if len(text + addition) < 2048:
                    text += addition
                else:
                    break
            emb = utils.red_embed(text)
            if uncached:
                text = f"\nAdditionally, {len(uncached)} old uncached message(s) were deleted." \
                       f"I am unable to see who sent uncached messages.\n"
                if len(emb.description + text) < 2048:
                    emb.description += text

        else:
            file = None
            text = f"{len(payload.message_ids)} old uncached messages have been cleared from <#{payload.channel_id}>." \
                   f" The removed message IDs were:\n"
            for msg_id in payload.message_ids:
                addition = f"M{msg_id}, "
                if len(text + addition) < 2048:
                    text += addition
                else:
                    break
            emb = utils.red_embed(text)

        try:
            await utils.safe_send(channel, embed=emb, file=file)
        except discord.Forbidden:
            await self.module_disable_notification(channel.guild, guild_config, 'message deletes')

    # ############### joins #####################

    @commands.group(invoke_without_command=True, name='joins')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def joins(self, ctx):
        """Logs server joins + tracks invite links."""
        result = await self.module_logging(ctx, self.bot.db['joins'])
        server_config = self.bot.db['joins'][str(ctx.guild.id)]
        if result == 1:
            await utils.safe_send(ctx, 'Disabled join logging for this server')
        elif result == 2:
            try:
                invites = await ctx.guild.invites()
                server_config['invites'] = await self.make_invites_dict(ctx.guild, invites)
                server_config['invites_enable'] = True
                await utils.safe_send(ctx,
                                   'Enabled join logging + invite tracking for this server (type `;joins invites` to '
                                   'disable invite tracking)')
            except discord.Forbidden:
                await utils.safe_send(ctx, "I've enabled join tracking, but I lack permissions to get invite codes.  "
                                        "If you want invite tracking too, give me `Manage Server` and then type "
                                        f"`{ctx.message.content} invites` to enable invite tracking for future joins.")
                server_config['invites_enable'] = False

        elif result == 3:
            await utils.safe_send(ctx,
                               'You have not yet set a channel for join logging yet. Run `;joins set`')
        elif result == 4:
            await utils.safe_send(ctx, 'Before doing this, set a channel for logging with `;joins set`.  '
                                    'Then, enable/disable logging by typing `;joins`.')

    @joins.command(name='set')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def joins_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['joins'])
        server_config = self.bot.db['joins'][str(ctx.guild.id)]
        if result == 1:
            await utils.safe_send(ctx, f'Set the join logging channel as {ctx.channel.name}')
        elif result == 2:
            try:
                invites = await ctx.guild.invites()
                server_config['invites'] = await self.make_invites_dict(ctx.guild, invites)
                server_config['invites_enable'] = True
                await utils.safe_send(ctx,
                                   f'Enabled join logging + invite tracking / set the channel to `{ctx.channel.name}`.'
                                   f'  Enable/disable logging by typing `;joins`.')
            except discord.Forbidden:
                await utils.safe_send(ctx, "I've enabled join logging, but I lack permissions to get invite codes.  "
                                        "If you want invite tracking too, give me `Manage Server` and then type "
                                        "`;joins invites` to enable invite tracking for future joins.")
                server_config['invites_enable'] = False

    @joins.command(name='invites')
    @commands.bot_has_permissions(send_messages=True, embed_links=True, manage_guild=True)
    async def invites_enable(self, ctx):
        """Enables/disables the identification of used invite links when people join"""
        guild = str(ctx.guild.id)
        if guild in self.bot.db['joins']:
            server_config = self.bot.db['joins'][guild]
            try:
                server_config['invites_enable'] = not server_config['invites_enable']
                await utils.safe_send(ctx, f"Set invite tracking to `{server_config['invites_enable']}`")
            except KeyError:
                server_config['invites_enable'] = True
                await utils.safe_send(ctx, 'Enabled invites tracking')
            except discord.Forbidden:
                pass
            if server_config['invites_enable']:
                await self.get_invites(ctx.guild)

    @staticmethod
    async def make_join_embed(member: discord.Member, used_invites, channel, config,
                              list_of_roles=None, failed_roles=None):
        minutes_ago_created = int(((discord.utils.utcnow() - member.created_at).total_seconds()) // 60)
        if 60 < minutes_ago_created < 3600:
            time_str = f'\n\nAccount created **{int(minutes_ago_created // 60)}** hours ago'
        elif minutes_ago_created < 60:
            time_str = f'\n\nAccount created **{minutes_ago_created}** minutes ago'
        else:
            time_str = ''

        emb = discord.Embed(
            description=f":inbox_tray: **[{str(member)}](https://rai/user-id-is-J{member.id})** "
                        f"has `joined`. ({member.mention}){time_str}",
            colour=0x7BA600,
            timestamp=discord.utils.utcnow()
        )

        if channel and hasattr(channel.last_message, 'jump_url'):
            emb.description += f"\n([Jump URL]({channel.last_message.jump_url}))"

        if len(used_invites) > 1:
            emb.add_field(name="Notification", value="I was unable to determine exactly which invite the user "
                                                     "used. Here were the multiple possibilities.", inline=False)
        for invite in used_invites:  # considering the possibilty of the bot not being able to pinpoint a link
            if not invite:
                continue
            if type(invite) == str:
                emb.add_field(name="Invite Link Used", value=f"Expired invite: {invite}")
                continue
            if invite.max_uses == 0:
                max_uses = ''
            else:
                max_uses = f"/{invite.max_uses}"

            field_value = f"`{invite.code}`"
            if invite.inviter:
                field_value += f" by {str(invite.inviter)} " \
                               f"([ID](https://rai/inviter-id-is-I{invite.inviter.id}))"
            field_value += f" ({invite.uses}{max_uses} uses"  # add a final ')' below
            if invite.created_at:
                seconds_ago_created = (discord.utils.utcnow() - invite.created_at).total_seconds()

                if 3600 < seconds_ago_created < 86400:
                    field_value += f" - created **{int(seconds_ago_created // 3600)}** hours ago)"
                elif seconds_ago_created < 3600:
                    field_value += f" - created **{int(seconds_ago_created // 60)}** minutes ago)"
                else:
                    field_value += ")"
            else:
                field_value += ")"

            emb.add_field(name="Invite link used", value=field_value)

        if not used_invites and config['invites_enable']:
            if "DISCOVERABLE" in member.guild.features:
                emb.add_field(name="Invite link used", value="Through server discovery")
            else:
                emb.add_field(name="Invite link used", value="Unable to be determined")

        if list_of_roles:
            emb.add_field(name='Readded roles:',
                          value=', '.join(reversed([role.name for role in list_of_roles])))
        if failed_roles:
            emb.add_field(name='Failed to add these roles:',
                          value=', '.join(reversed([role.name for role in failed_roles])))
        footer_text = f'User Join ({member.guild.member_count}) - {member.id}'
        emb.set_footer(text=footer_text, icon_url=member.display_avatar.replace(static_format="png").url)

        return emb

    @commands.Cog.listener()
    async def on_invite_create(self, invite):
        try:
            config = self.bot.db['joins'][str(invite.guild.id)]
        except KeyError:
            return
        if not config.get('invites_enable', None):
            return
        if invite.max_age:
            expiration = (invite.created_at + timedelta(seconds=invite.max_age)).timestamp()
        else:
            expiration = None
        config['invites'][invite.code] = (0, expiration)

    @commands.Cog.listener()
    async def on_invite_remove(self, invite):
        try:
            config = self.bot.db['joins'][str(invite.guild.id)]
        except KeyError:
            return
        if not config.get('invites_enable', None):
            return
        try:
            del (config['invites'][invite.code])
        except KeyError:
            return

    # ############### welcome message #####################

    @commands.group(invoke_without_command=True)
    async def welcome_message(self, ctx):
        """enable welcome messages"""
        guild = str(ctx.guild.id)
        if guild in self.bot.db['welcome_message']:
            config = self.bot.db['welcome_message'][guild]
            try:
                config['enable'] = not config['enable']
                x = config['enable']
                await utils.safe_send(ctx, f'Set welcome message posting to {x}')
            except KeyError:
                config['enable'] = True
                x = config['enable']
                await utils.safe_send(ctx, f'Set welcome message posting to {x}')
        else:
            self.bot.db['welcome_message'][guild] = {}
            config = self.bot.db['welcome_message'][guild]
            config['enable'] = True
            x = config['enable']
            await utils.safe_send(ctx, f'Set welcome message posting to {x}')

    @welcome_message.command()
    async def set_message(self, ctx, *, message: str = None):
        if not message:
            text = ('Please put your welcome message after the command invocation.  For example: \n'
                    '```;welcome_message set_message Welcome to the server `$NAME$`! Please read the rules```\n'
                    "Valid flags to use are: \n$NAME$ = The user's name in text\n`$USERMENTION$` = Mentions "
                    "the user\n`$SERVER$` = The name of the server")
            await utils.safe_send(ctx, text)
        else:
            try:
                config = self.bot.db['welcome_message'][str(ctx.guild.id)]
            except KeyError:
                await utils.safe_send(ctx, "Run `;welcome_message` first to setup the module")
                return
            config['message'] = message
            await utils.safe_send(ctx, f"Set welcome message to ```{message}```")

    @welcome_message.command()
    async def set_channel(self, ctx):
        try:
            config = self.bot.db['welcome_message'][str(ctx.guild.id)]
        except KeyError:
            await ctx.invoke(self.welcome_message)
            config = self.bot.db['welcome_message'][str(ctx.guild.id)]
        config['channel'] = ctx.channel.id
        await utils.safe_send(ctx, f"Set welcome message channel to {ctx.channel.mention}")

    @welcome_message.command()
    async def show_message(self, ctx):
        config = self.bot.db['welcome_message'][str(ctx.guild.id)]
        await utils.safe_send(ctx, "```" + config['message'] + "```")

    @staticmethod
    async def make_invites_dict(guild, invites_in: List[discord.Invite]):
        invites_dict: Dict[str: Tuple[int, Optional[float]]] = {}
        for invite in invites_in:
            if not invite:
                continue
            if invite.max_age:
                expiration = (invite.created_at + timedelta(seconds=invite.max_age)).timestamp()
            else:
                expiration = None
            invites_dict[invite.code] = (invite.uses, expiration)
        return invites_dict

    async def get_invites(self, guild):
        guild_id = str(guild.id)
        config: dict = self.bot.db['joins'][str(guild.id)]
        if not config.get('invites_enable', None):
            return None, None
        if 'invites' not in config:
            config['invites'] = {}

        old_invites: Dict[str, List[Optional[str]]] = self.bot.db['joins'][guild_id]['invites']

        try:
            invites: List[discord.Invite] = await guild.invites()
            for i in invites:
                if not i:  # in case there are some NoneType returned in the list
                    invites.remove(i)
        except discord.Forbidden:
            self.bot.db['joins'][guild_id]['invites_enable'] = False
            return None, None
        except discord.HTTPException:
            return None, None

        if 'VANITY_URL' in guild.features:
            try:
                vanity = await guild.vanity_invite()
                if vanity:
                    invites.append(vanity)
            except (discord.HTTPException, discord.Forbidden):
                pass

        self.bot.db['joins'][guild_id]['invites'] = await self.make_invites_dict(guild, invites)
        return old_invites, invites

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """welcome message"""
        async def welcome_message():
            guild = str(member.guild.id)
            _welcome_channel: Optional[discord.TextChannel] = None
            if guild in self.bot.db['welcome_message']:
                config = self.bot.db['welcome_message'][guild]
                if 'channel' in self.bot.db['welcome_message'][guild]:
                    _welcome_channel = self.bot.get_channel(config['channel'])
                if self.bot.db['welcome_message'][guild]['enable']:
                    message = config['message']
                    message = message. \
                        replace('$NAME$', member.name). \
                        replace('$USERMENTION$', member.mention). \
                        replace('$SERVER$', member.guild.name)
                    await utils.safe_send(_welcome_channel, message)
            return _welcome_channel

        welcome_channel = await welcome_message()

        """Join logging"""

        async def join_logging():
            guild: discord.Guild = member.guild
            guild_id = str(member.guild.id)
            try:
                server_config: dict = self.bot.db['joins'][guild_id]
                log_channel: discord.TextChannel = self.bot.get_channel(server_config['channel'])
                if not log_channel:
                    del server_config
                    return
            except KeyError:
                return
            if not server_config['enable']:
                return

            if not log_channel.permissions_for(guild.me).embed_links:
                try:
                    await utils.safe_send(log_channel, "I tried to post a join notification but I lack the permission to"
                                                    " post embeds. Please give me the permission to embed links.")
                except discord.Forbidden:
                    del server_config
                return
            if server_config['invites_enable'] and not member.guild.me.guild_permissions.manage_guild:
                disable_message = "Invite tracking is currently enabled, but Discord requries the `Manage Server` " \
                                  "permission to view invite links. Please give Rai this persmission then type " \
                                  "`;joins invites` to reenable the tracking of invite links."
                await utils.safe_send(log_channel, disable_message)
                server_config['invites_enable'] = False

            old_invites: Optional[Dict[str, List[Optional[float]]]]
            invites: Optional[List[discord.Invite]]
            old_invites, invites = await self.get_invites(guild)  # returns None, None if invites_enable=False in config
            used_invite: List[discord.Invite] = []
            maybe_used_invite: List[str] = []
            if invites:
                invites_dict: Dict[str, discord.Invite] = {}
                for i in invites:
                    assert isinstance(i, discord.Invite), f"{guild.name} - {i} - {len(invites)}"
                    if i:
                        invites_dict[i.code] = i  # same form as old_invites

                for invite in old_invites:
                    assert isinstance(invite, str)
                    if invite not in invites_dict:  # the invite disappeared
                        if old_invites[invite][1]:
                            if discord.utils.utcnow().timestamp() > old_invites[invite][1]:
                                continue  # it was a timed invite that simply expired
                        maybe_used_invite.append(invite)  # it was an invite that reached its max uses
                        continue
                    try:
                        if old_invites[invite][0] < getattr(invites_dict.get(invite, 0), "uses", 0):
                            used_invite.append(invites_dict[invite])
                    except TypeError:
                        pass

                for invite in invites_dict:
                    if invite not in old_invites:  # a new invite was made but not detected in on_invite_create
                        if invites_dict[invite].uses:  # it has uses
                            used_invite.append(invites_dict[invite])

            if maybe_used_invite and not used_invite:
                used_invite = maybe_used_invite

            def get_list_of_roles() -> tuple[dict, List[discord.Role]]:
                try:
                    config: dict = self.bot.db['joins'][guild_id]['readd_roles']
                except KeyError:
                    return None, None
                if not config['enable'] or str(member.id) not in config['users']:
                    return None, None

                list_of_roles: List[discord.Role] = []
                roles_dict: Dict[int: discord.Role] = {role.id: role for role in member.guild.roles}
                for role_code in config['users'][str(member.id)][1].split(','):
                    try:
                        list_of_roles.append(roles_dict[config['roles'][role_code]])
                    except KeyError:
                        pass
                return config, list_of_roles

            readd_config: dict
            list_of_readd_roles: List[discord.Role]
            readd_config, list_of_readd_roles = get_list_of_roles()
            failed_roles = []  # roles higher than the bot's highest role
            if list_of_readd_roles:
                try:
                    stage_visitor = member.guild.get_role(645021058184773643)
                    if stage_visitor in list_of_readd_roles:
                        list_of_readd_roles.remove(stage_visitor)
                    try:
                        for role in list_of_readd_roles:
                            try:
                                await member.add_roles(role)
                            except discord.Forbidden:
                                list_of_readd_roles.remove(role)
                                failed_roles.append(role)
                            except AttributeError:  # role is None
                                list_of_readd_roles.remove(role)
                                continue
                    except discord.NotFound:
                        pass
                    try:
                        readded_roles_str = f"`{'`, `'.join(reversed([r.name for r in list_of_readd_roles]))}`"
                        notif_msg = f"Welcome back {member.name}! I've given your previous roles back to you: " \
                                    f"{readded_roles_str}"
                        if failed_roles:
                            failed_roles_str = f"`{'`, `'.join(reversed([r.name for r in failed_roles]))}`"
                            notif_msg += f"\nI failed to add the following roles to you: {failed_roles_str}."
                        await member.send(notif_msg)
                    except discord.HTTPException:
                        pass
                except discord.Forbidden:
                    pass
                del readd_config['users'][str(member.id)]
            x = await self.make_join_embed(member, used_invite, welcome_channel, server_config,
                                           list_of_readd_roles, failed_roles)
            log_message = await utils.safe_send(log_channel, member.id, embed=x)

            # Logging join info for modlog pulls
            recorded_info = {}
            if log_message:
                recorded_info['jump_url'] = log_message.jump_url

            if used_invite:
                recorded_info['invite'] = getattr(used_invite[0], "code", None)
                # invite_creator = getattr(used_invite[0].inviter, "id", None)

            server_config.setdefault('join_history', {})[str(member.id)] = recorded_info

            # Special Japanese server invite management
            if guild_id == str(JP_SERV_ID):
                jpJHO = self.bot.get_channel(JP_SERV_JHO_ID)
                new_user_role = member.guild.get_role(249695630606336000)
                ne = member.guild.get_role(197100137665921024)  # native english role
                ol = member.guild.get_role(248982130246418433)  # other language role
                nj = member.guild.get_role(196765998706196480)  # native japanese role
                JHO_msg = f"Welcome {member.name}!"

                # check if they joined from a Japanese site or other
                if used_invite:
                    # the following links are specifically the ones we've used to advertise on japanese sites
                    japanese_links = ['6DXjBs5', 'WcBF7XZ', 'jzfhS2', 'w6muGjF', 'TxdPsSm', 'MF9XF89', 'RJrcSb3']
                    for link in used_invite:
                        if type(link) == str:
                            continue
                        if link.code in japanese_links:
                            JHO_msg = f'{member.name}さん、サーバーへようこそ！'
                            break

                # check if they've been in the server before
                if list_of_readd_roles:
                    JHO_msg += " I've readded your previous roles to you!"
                    await hf.sleep("member_join", 2)

                    # else, if they are a returning *tagged* user, take away "new user" if they have it for some reason
                    if new_user_role in member.roles:
                        await member.remove_roles(new_user_role)

                # if the user has no language roles, give them the "new user" role
                if (ne not in member.roles) and (ol not in member.roles) and (nj not in member.roles):
                    await member.add_roles(new_user_role)

                try:
                    await utils.safe_send(jpJHO, JHO_msg)
                except (discord.Forbidden, discord.HTTPException):
                    pass

                # secret entry for Abelian
                if member.id == ABELIAN_ID:
                    async for message in jpJHO.history(limit=10):
                        if message.author.id == 159985870458322944:
                            await message.delete()
                            break
                    try:
                        def check(m):
                            return m.author.id == 299335689558949888 and m.channel == jpJHO

                        msg = await hf.wait_for('member_join', 'message', timeout=10.0, check=check)
                        await msg.delete()
                    except asyncio.TimeoutError:
                        pass

        await join_logging()

        """ban invite link names"""
        try:
            if self.bot.db['auto_bans'][str(member.guild.id)]['enable']:
                pat = re.compile(r'.*(discord|discordapp).(gg|com/invite)/[A-Z0-9]{1,7}.*', re.I)
                if re.match(pat, member.name):
                    # guild = str(member.guild.id)
                    await member.ban(reason="Name was a discord invite link")
                    message = f"Banned user `{member.name}` from {member.guild.name} for being an invite link name\n" \
                              f"({member.id} {member.mention})"
                    await self.bot.get_channel(BANS_CHANNEL_ID).send(message)
                    self.bot.db['global_blacklist']['blacklist'].append(member.id)
                    channel = self.bot.get_channel(533863928263082014)
                    await utils.safe_send(channel,
                                       f"❌ Automatically added `{member.name} ({member.id}`) to the blacklist for "
                                       f"being an invite-link name")
                    return  # stops execution of the rest of the code if was invite link name
        except KeyError:
            pass

        """blacklist bans"""
        config = self.bot.db['global_blacklist']
        if member.id in config.get('blacklist', {}):
            try:
                if config[str(member.guild.id)]['enable']:
                    bans_channel = self.bot.get_channel(BANS_CHANNEL_ID)
                    try:
                        await member.ban(reason="On the global blacklist")
                    except discord.Forbidden:
                        await utils.safe_send(bans_channel, embed=utils.red_embed("WARNING: I tried to ban a user for being "
                                                                            "on the global blacklist but I lacked "
                                                                            "the permission to ban users on that "
                                                                            "server."))
                    await hf.ban_check_servers(self.bot, bans_channel, member, ping=True, embed=None)
                    return
            except KeyError:
                pass

        if str(member.id) in self.bot.db['banlog']:
            config = self.bot.db['banlog'][str(member.id)]  # a list of lists of: [guild.id, crosspost_msg.id]
            bans_channel = self.bot.get_channel(BANS_CHANNEL_ID)
            emb = utils.red_embed(f"WARNING: The user **{str(member)}** ({member.id}) has joined **{member.guild.name}**"
                               f"\n\nThey were banned before on the following servers:\n")
            emb.color = 0x8013E0

            for entry in config:
                banned_guild = self.bot.get_guild(entry[0])

                # check to see if actual ban still exists
                try:
                    await banned_guild.fetch_ban(member)
                except (discord.NotFound, discord.Forbidden):
                    config.remove(entry)
                    continue

                # get original ban notification / event from bans logging channel
                try:
                    message = await bans_channel.fetch_message(entry[1])
                except discord.NotFound:  # if the ban log message was deleted
                    config.remove(entry)
                    continue

                date_str = message.created_at.strftime("%Y/%m/%d")
                emb.description += f"　　・[{banned_guild.name}]({message.jump_url}) ({date_str})\n"
                emb.description += f"　　　__Reason__: {message.embeds[0].description.split('__Reason__: ')[1]}\n\n"

            pings = ""
            if str(member.guild.id) in self.bot.db['bansub']['guild_to_role']:
                role_id: int = self.bot.db['bansub']['guild_to_role'][str(member.guild.id)]
                for user_id in self.bot.db['bansub']['user_to_role']:  # type: Dict[str: List[int]]
                    if role_id in self.bot.db['bansub']['user_to_role'][user_id]:
                        pings += f" <@{user_id}> "

                sent_to_mod_channel = False  # default to False unless it sends it below
                # The point of this is: if you can send to mod_channel, ping the mods there.
                # Otherwise, ping them in the mod server
                if str(member.guild.id) in self.bot.db['mod_channel']:
                    mod_channel = self.bot.get_channel(self.bot.db['mod_channel'][str(member.guild.id)])
                    if mod_channel:
                        try:
                            await utils.safe_send(mod_channel, f"{member.mention}\n{pings} (@here)", embed=emb)
                            sent_to_mod_channel = True
                        except (discord.Forbidden, discord.HTTPException):
                            pass

                if config:  # this will be False if the last entry in config was deleted above from the NotFound error
                    if sent_to_mod_channel:
                        msg = f"{member.mention}"
                    else:
                        msg = f"{member.mention}\n{pings}"
                    await utils.safe_send(bans_channel, msg, embed=emb)

                else:
                    del (self.bot.db['banlogs'][str(member.id)])  # cleanup

            # check if this modlog entry doesn't already exist in the user's modlog
            # only do hf.add_to_modlog if it wasn't already there with that emb.description
            this_user_modlog = self.bot.db['modlog'].get(str(member.id), [])
            if this_user_modlog:
                for entry in this_user_modlog:
                    if entry[1] == emb.description:
                        return
            hf.add_to_modlog(None, [member, member.guild], 'Log', emb.description, False, None)

    # ############### leaves #####################

    @commands.group(invoke_without_command=True, name='leaves')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def leaves(self, ctx):
        """Logs leaves + shows list of roles at time of leave"""
        result = await self.module_logging(ctx, self.bot.db['leaves'])
        if result == 1:
            await utils.safe_send(ctx, 'Disabled leave logging for this server')
        elif result == 2:
            await utils.safe_send(ctx, 'Enabled leave logging for this server')
        elif result == 3:
            await utils.safe_send(ctx, 'You have not yet set a channel for leave logging yet. Run `;leave_logging set`')
        elif result == 4:
            await utils.safe_send(ctx, 'Before doing this, set a channel for logging with `;leave_logging set`.  '
                                    'Then, enable/disable logging by typing `;leave_logging`.')

    @leaves.command(name='set')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def leaves_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['leaves'])
        if result == 1:
            await utils.safe_send(ctx, f'Set the leave logging channel as `{ctx.channel.name}`')
        elif result == 2:
            await utils.safe_send(ctx,
                               f'Enabled leave logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                               f' logging by typing `;leave_logging`.')

    @staticmethod
    def make_leave_embed(member):
        emb = discord.Embed(
            description=''
                        f":outbox_tray: **[{str(member)}](https://rai/user-id-is-J{member.id})**"
                        f" has `left` the server. ({member.mention})",
            colour=0xD12B2B,
            timestamp=discord.utils.utcnow()
        )

        if len(member.roles) > 1:  # all members have the @everyone role
            emb.add_field(name='Roles:', value=', '.join(reversed([role.name for role in member.roles[1:]])))

        emb.set_footer(
            text=f'User Leave ({member.guild.member_count}) - {member.id}',
            icon_url=member.display_avatar.replace(static_format="png").url
        )
        return emb

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        # ### This is used for 1) allowing submods to ban users who have joined less than an hour ago but
        # ### have already left the server, and 2) for the make_ban_embed command if it didn't get a member
        self.bot.recently_removed_members.setdefault(str(member.guild.id), [member]).append(member)
        if len(self.bot.recently_removed_members[str(member.guild.id)]) > 10:
            del (self.bot.recently_removed_members[str(member.guild.id)][0])

        guild = str(member.guild.id)
        if guild in self.bot.db['leaves']:
            if self.bot.db['leaves'][guild]['enable']:
                guild_config = self.bot.db['leaves'][guild]
                channel = self.bot.get_channel(guild_config['channel'])
                if not channel:
                    del self.bot.db['leaves'][guild]
                    return
                try:
                    await utils.safe_send(channel, member.id, embed=self.make_leave_embed(member))
                except discord.Forbidden:
                    await self.module_disable_notification(member.guild, guild_config, 'member leave')

        try:
            config = self.bot.db['joins'][str(member.guild.id)]['readd_roles']
        except KeyError:
            pass
        else:
            if config['enable']:
                if 'roles' in config:
                    codes = {str(y): x for x, y in config['roles'].items()}  # {str(role_id): index} dictionary
                else:
                    codes = config['roles'] = {}
                found_roles = []
                for role in member.roles:
                    if role.name in ['Nitro Booster', 'New User'] or \
                            role.id in [249695630606336000,  # jp server new user role
                                        member.guild.id,  # the "@everyone" role
                                        645021058184773643,  # jp server "stage visitor" role
                                        590163584856752143]:  # awesome supporter role (jp server)

                        pass
                    else:
                        if str(role.id) in codes:
                            found_roles.append(codes[str(role.id)])
                        else:
                            index = str(len(codes))
                            config['roles'][index] = role.id
                            codes[str(role.id)] = index
                            found_roles.append(codes[str(role.id)])

                if found_roles:  # if the role list isn't empty (i.e., no roles)
                    config['users'][str(member.id)] = [discord.utils.utcnow().strftime("%Y%m%d"), ','.join(found_roles)]

        if guild in self.bot.db['kicks']:
            guild_config: dict = self.bot.db['kicks'][guild]
            if guild_config['enable']:
                channel = self.bot.get_channel(guild_config["channel"])
                try:
                    emb = await self.make_kick_embed(member)
                except discord.Forbidden:
                    await self.module_disable_notification(member.guild, guild_config, 'member kick')
                    return
                if emb:
                    await utils.safe_send(channel, embed=emb)

        # ### Remove from join_history used in modlog command
        try:
            del self.bot.db['joins'][str(member.guild.id)]['join_history'][str(member.id)]
        except KeyError:
            pass

    # ############### nicknames/usernames #####################

    @commands.group(invoke_without_command=True, name='nicknames')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def nicknames(self, ctx):
        """Logs nicknames changes"""
        result = await self.module_logging(ctx, self.bot.db['nicknames'])
        if result == 1:
            await utils.safe_send(ctx, 'Disabled nickname logging for this server')
        elif result == 2:
            await utils.safe_send(ctx, 'Enabled nickname logging for this server')
        elif result == 3:
            await utils.safe_send(ctx,
                               'You have not yet set a channel for nickname logging yet. Run `;nickname_logging set`')
        elif result == 4:
            await utils.safe_send(ctx, 'Before doing this, set a channel for logging with `;nickname_logging set`.  '
                                    'Then, enable/disable logging by typing `;nickname_logging`.')

    @nicknames.command(name='set')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def nicknames_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['nicknames'])
        if result == 1:
            await utils.safe_send(ctx, f'Set the nickname logging channel as `{ctx.channel.name}`')
        elif result == 2:
            await utils.safe_send(ctx,
                               f'Enabled nickname logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                               f' logging by typing `;nickname_logging`.')

    @staticmethod
    def make_nickname_embed(before, after):
        emb = discord.Embed(timestamp=discord.utils.utcnow())
        emb.set_footer(
            text=f'{str(after)} (N{before.id})',
            icon_url=before.display_avatar.replace(static_format="png").url
        )
        return emb

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        if before.name != after.name:
            updated_attr = '__username__'
            before_name = before.name
            after_name = after.name
        elif before.global_name != after.global_name:
            updated_attr = '__global display name__'
            before_name = before.global_name
            after_name = after.global_name
        else:
            return

        async def get_mutual_guilds():
            return before.mutual_guilds
        
        mutual_guilds_task = utils.asyncio_task(get_mutual_guilds)
        mutual_guilds = await mutual_guilds_task
        for g in mutual_guilds:
            guild = str(g.id)
            if not self.bot.db['nicknames'].get(guild, {'enable': False})['enable']:
                continue  # if the guild doesn't have username changes enabled

            channel = self.bot.get_channel(self.bot.db['nicknames'][guild]['channel'])
            if not channel:
                continue

            emb = self.make_nickname_embed(before, after)
            if not before_name:
                emb.description = f"**{str(after)}** set their {updated_attr} to **{after_name}**"
            else:
                emb.description = f"**{before_name}**'s {updated_attr} was changed to **{after_name}**"
            emb.colour = 0xFF8800
            try:
                await utils.safe_send(channel, embed=emb)
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_member_update(self: commands.Cog, before: discord.Member, after: discord.Member):
        # ######### Nicknames #############
        async def phys_server_remove_to_check():
            guild = before.guild
            to_check = guild.get_role(1199077563839033395)
            checked = guild.get_role(1199070835080691795)
            if checked not in before.roles and checked in after.roles:
                if to_check in after.roles:
                    await after.remove_roles(to_check)
        await phys_server_remove_to_check()

        async def phys_server_verification_check():
            guild = before.guild
            if guild.id != 965307041314918461:
                return

            if before.roles == after.roles and before.nick == after.nick:
                return  # user did not update roles or nickname

            verified_user_role = guild.get_role(1199091196417548339)
            if verified_user_role in after.roles:
                return  # User already fully verified, no checks needed

            # get list of important roles
            important_role_ids = [968631535265796147, 968631629474037800, 968631666371346462, 968631689477763123,
                                  968631711778869319, 968631736567214101, 1121216657772253204, 1123015201642512558,
                                  1123015668590198834, 1123015305669640322]
            important_roles = []
            for role_id in important_role_ids:
                role = guild.get_role(role_id)
                if not role:
                    raise discord.NotFound
                important_roles.append(role)

            meta_channel = guild.get_channel(966400278054203403)
            valid_name_role = guild.get_role(1199070835080691795)
            check_name_role = guild.get_role(1199077563839033395)
            roles_verified = False  # becomes True if they have one of the important roles
            for role in important_roles:
                if role in after.roles:
                    roles_verified = True

            name_verified = valid_name_role in after.roles  # becomes True if they have the "Valid Name" role

            if before.nick != after.nick:
                if (after.nick or '').count(" ") == 0:
                    await meta_channel.send(f"<@202995638860906496> ❌❌❌\n{before.mention} changed their nickname from "
                                            f"`{before.nick}` --> `{after.nick}`. Their name doesn't have a space in it"
                                            f" so it potentially doesn't include their last name. Please check it.")
                else:
                    await meta_channel.send(f"<@202995638860906496> ✅✅✅\n{before.mention} changed their nickname from "
                                            f"`{before.nick}` --> `{after.nick}`. I'm assuming it's a valid name format"
                                            f" since it has a space in it, so I'm adding the {valid_name_role.name} "
                                            f"role to them.")
                    if not roles_verified:
                        # check because if roles_verified is True, this role will be immediately removed below
                        await after.add_roles(valid_name_role)
                    await after.remove_roles(check_name_role)
                    name_verified = True

            if name_verified and roles_verified:
                await meta_channel.send(f"<@202995638860906496> ✅✅✅\n{before.mention} has both verified roles and "
                                        f"a valid name so I'm adding them to the server.")
                await after.add_roles(verified_user_role)
                if valid_name_role in after.roles:
                    try:
                        await after.remove_roles(valid_name_role)
                    except discord.HTTPException:
                        pass

        await phys_server_verification_check()

        async def check_nickname_change():
            guild = str(before.guild.id)
            if not self.bot.db['nicknames'].get(guild, {'enable': False})['enable']:
                return

            guild_config = self.bot.db['nicknames'][guild]
            channel = self.bot.get_channel(guild_config['channel'])
            if not channel or before.nick == after.nick:
                return

            emb = self.make_nickname_embed(before, after)
            emb.colour = 0xFFA500

            if before.nick and not after.nick:  # nickname removed
                emb.description = f"**{before.nick}**'s __server nickname__ was **removed**"
            elif not before.nick and after.nick:  # nickname added
                emb.description = f"**{str(before)}**'s __server nickname__ was set to **{after.nick}**"
            elif before.nick and after.nick:  # nickname changed
                emb.description = f"**{before.nick}**'s __server nickname__ was changed to **{after.nick}**"
            try:
                await utils.safe_send(channel, embed=emb)
            except discord.Forbidden:
                pass

        await check_nickname_change()

        # ######### Timeouts #############
        async def check_timeouts():
            if not (self.bot.db['modlog'].get(str(before.guild.id), None)):
                return  # guild has not setup modlog

            if not (not before.is_timed_out() and after.is_timed_out()):
                return  # event is not a timeout event

            if before.guild.id == 189571157446492161:
                return

            guild = before.guild
            attempts = 0
            time_left: float = 0
            timeout_length_str = None
            reason = None
            author = None
            while attempts < 3:  # in case there's discord lag and something doesn't make it into the audit log
                async for entry in guild.audit_logs(limit=None, oldest_first=False,
                                                    action=discord.AuditLogAction.member_update,
                                                    after=discord.utils.utcnow() - timedelta(seconds=60)):
                    if entry.target == before:
                        author = entry.user
                        if author == guild.me:
                            return  # A timeout by Rai, probably in the mute command. Let that command handle the modlog
                        if after.timed_out_until:
                            time_left = (after.timed_out_until - discord.utils.utcnow()).total_seconds()
                        else:
                            time_left = 0
                        reason = entry.reason

                        if reason:
                            if "SELFMUTE" in reason and len(reason.split()) == 1:  # for RAI_SELFMUTE or CIRI_SELFMUTE":
                                return

                        if 0 < time_left < 70:  # 60 SEC
                            timeout_length_str = "1m"
                        elif 250 < time_left < 350:  # 5 MIN = 300 SEC
                            timeout_length_str = "5m"
                        elif 550 < time_left < 650:  # 10 MIN = 600 SEC
                            timeout_length_str = "10m"
                        elif 3550 < time_left < 3650:  # 1 HOUR = 3600 SEC
                            timeout_length_str = "1h"
                        elif 86350 < time_left < 86450:  # 1 DAY = 86400 SEC
                            timeout_length_str = "1d"
                        elif 604750 < time_left < 604850:  # 1 WEEK = 604,800 SEC
                            timeout_length_str = "7d"
                        else:
                            timeout_length_str = "Unknown"

                        break  # this breaks the for entry in guild.audit_logs() if it finds the entry
                if time_left:
                    break  # this breaks the while loop if it found an entry
                attempts += 1
                await hf.sleep("member_update", 15)

            if not time_left:
                return  # No matching entries found

            emb = utils.red_embed("")
            emb.title = f"You have been timed out on {guild.name}"
            emb.color = 0xff8800  # orange
            emb.add_field(name="User", value=f"{after.name} ({after.id})", inline=False)
            timestamp = int(after.timed_out_until.timestamp())
            emb.add_field(name="Length",
                          value=f"{timeout_length_str} (unmute time: <t:{timestamp}> - <t:{timestamp}:R>)",
                          inline=False)
            if reason:
                emb.add_field(name="Reason", value=reason)

            # Add default prompt to go to modbot for questions about the warning
            modbot = guild.get_member(713245294657273856)
            if modbot:
                emb.add_field(name="Questions about this mute?",
                              value=f"Please send a message to {modbot.mention}.",
                              inline=False)
                content = f"Questions → {modbot.mention}"
            else:
                content = ""

            try:
                await utils.safe_send(after, content, embed=emb)
            except discord.Forbidden:
                try:
                    await utils.safe_send(author, "Notification: I was unable to notify the user of the timeout due to "
                                               "their privacy settings.", embed=emb)
                except (discord.Forbidden, discord.HTTPException):
                    pass

            emb.set_footer(text=f"Muted by {author.name} ({author.id})")
            emb.title = "Timeout"
            modlog_channel = self.bot.get_channel(self.bot.db['modlog'][str(guild.id)]['channel'])
            if modlog_channel:
                if guild.id == SPAN_SERV_ID:
                    incidents_channel = guild.get_channel(808077477703712788)
                    notif_msg = await utils.safe_send(incidents_channel, str(after.id), embed=emb)
                    ctx = await self.bot.get_context(notif_msg)
                else:
                    notif_msg = await utils.safe_send(modlog_channel, str(after.id), embed=emb)
                    ctx = await self.bot.get_context(notif_msg)

                hf.add_to_modlog(ctx, after, 'Timeout', reason, False, timeout_length_str)
            else:
                hf.add_to_modlog(None, [after, after.guild], 'Timeout', reason, False, timeout_length_str)

            # send second notification for sesion mods
            event_helper = guild.get_role(830821949382983751)
            voice_mod = guild.get_role(1228581686443507722)
            event_host = guild.get_role(874020674124021760)
            if {event_helper, voice_mod, event_host} & set(author.roles):  # if any of the lower helper roles exist
                trial_staff = guild.get_role(591745589054668817)
                server_helper = guild.get_role(258819531193974784)
                admin = guild.get_role(243854949522472971)
                if not {trial_staff, server_helper, admin} & set(author.roles):  # check to make sure no higher roles
                    event_helpers_channel = guild.get_channel(861337623636475944)
                    if event_helpers_channel:
                        await utils.safe_send(event_helpers_channel, str(after.id), embed=emb)
                        await utils.safe_send(event_helpers_channel,
                                              f"{author.mention}: \n- If you have any extra information to add "
                                              f"for this timeout for us, please let us know here when you get the "
                                              f"chance. For example, why you muted, what was happening when you muted, "
                                              f"etc. Thanks!\n"
                                              f"- Si tienes alguna información extra que añadir para este tiempo "
                                              f"de espera para nosotros, por favor háznoslo saber aquí cuando "
                                              f"tengas la oportunidad. Por ejemplo, por qué lo silenciaste, "
                                              f"qué estaba pasando cuando lo silenciaste, etc. ¡Gracias!")

        await check_timeouts()

    # ############### reaction removals #####################

    @commands.group(invoke_without_command=True, name='reactions')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def reactions(self, ctx):
        """Logs deleted reactions"""
        result = await self.module_logging(ctx, self.bot.db['reactions'])
        if result == 1:
            await utils.safe_send(ctx, 'Disabled reaction logging for this server')
        elif result == 2:
            await utils.safe_send(ctx, 'Enabled reaction logging for this server')
        elif result == 3:
            await utils.safe_send(ctx,
                               'You have not yet set a channel for reaction logging yet. Run `;reaction_logging set`')
        elif result == 4:
            await utils.safe_send(ctx, 'Before doing this, set a channel for logging with `;reaction_logging set`.  '
                                    'Then, enable/disable logging by typing `;reaction_logging`.')

    @reactions.command(name='set')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def reactions_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['reactions'])
        if result == 1:
            await utils.safe_send(ctx, f'Set the reaction logging channel as {ctx.channel.name}')
        elif result == 2:
            await utils.safe_send(ctx,
                               f'Enabled reaction logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                               f' logging by typing `;reaction_logging`.')

    @staticmethod
    def make_reaction_embed(emoji, member, message, message_id, channel):
        jump_url = f"https://discord.com/channels/{channel.guild.id}/{channel.id}/{message_id}"
        emb = discord.Embed(
            description=f"**{str(member)}** (R{member.id}) "
                        f" removed a reaction. ([Jump URL]({jump_url}))",
            colour=0xD12B2B,
            timestamp=discord.utils.utcnow()
        )

        if message:
            if message.content:
                emb.add_field(name='Original message:', value=message.content[:1024])

        if emoji.is_custom_emoji():
            emb.set_thumbnail(url=emoji.url)
        else:
            emb.add_field(name='Removed reaction', value=f'{str(emoji)}')

        emb.set_footer(text=f'#{channel.name}',
                       icon_url=member.display_avatar.replace(static_format="png").url)

        return emb

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return

        guild_config: dict = self.bot.db['reactions'].get(str(payload.guild_id), {})
        if not guild_config.get("enable", False):
            return

        emoji = payload.emoji
        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        channel = guild.get_channel(payload.channel_id)

        cache = {i.id: i for i in self.bot.cached_messages}
        message = cache.get(payload.message_id, None)

        log_channel = self.bot.get_channel(guild_config["channel"])
        try:
            await utils.safe_send(log_channel,
                               embed=self.make_reaction_embed(emoji, member, message, payload.message_id, channel))
        except discord.Forbidden:
            await self.module_disable_notification(guild, guild_config, 'reaction remove')
            return
        except AttributeError:
            del guild_config

    # ############### bans/unbans #####################

    @commands.group(invoke_without_command=True, name='bans')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def bans(self, ctx):
        """Logs deleted bans"""
        if not ctx.me.guild_permissions.view_audit_log or not ctx.me.guild_permissions.embed_links:
            await utils.safe_send(ctx,
                               "I lack the permission to either view audit logs or embed links.  Please try again.")
            return
        result = await self.module_logging(ctx, self.bot.db['bans'])
        if result == 1:
            await utils.safe_send(ctx, 'Disabled ban logging for this server')
        elif result == 2:
            await utils.safe_send(ctx, 'Enabled ban logging for this server')
        elif result == 3:
            await utils.safe_send(ctx, 'You have not yet set a channel for ban logging yet. Run `;ban_logging set`')
        elif result == 4:
            await utils.safe_send(ctx, 'Before doing this, set a channel for logging with `;ban_logging set`.  '
                                    'Then, enable/disable logging by typing `;ban_logging`.')

    @bans.command(name='set', short_name='set')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def bans_set(self, ctx):
        self.short_name = 'set'
        result = await self.module_set(ctx, self.bot.db['bans'])
        if result == 1:
            await utils.safe_send(ctx, f'Set the ban logging channel as {ctx.channel.name}')
        elif result == 2:
            await utils.safe_send(ctx, f'Enabled ban logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                                    f' logging by typing `;ban_logging`.')

    async def make_ban_embed(self, guild: discord.Guild, member: discord.User):
        ban_entry = None
        reason = "(could not find audit log entry)"
        by = None

        # ################## NORMAL BAN EMBED #########################

        await hf.sleep("member_ban", 3)
        attempts = 0
        while attempts < 3:  # in case there's discord lag and something doesn't make it into the audit log
            async for entry in guild.audit_logs(limit=None, oldest_first=False,
                                                action=discord.AuditLogAction.ban,
                                                after=discord.utils.utcnow() - timedelta(seconds=60)):
                if entry.action == discord.AuditLogAction.ban and entry.target == member:
                    ban_entry = entry
                    reason = ban_entry.reason
                    by = ban_entry.user
                    break  # this breaks the for entry in guild.audit_logs() if it finds the entry
            if by:
                break  # this breaks the while loop if it found an entry
            attempts += 1
            await hf.sleep("member_ban", 15, add=True)
        emb = discord.Embed(colour=0x000000, timestamp=discord.utils.utcnow(), description='')
        if not reason:
            reason = '(none given)'
        if reason.startswith('⁣') or '-s' in reason:  # skip crossposting if enabled
            reason = reason.replace('⁣', '').replace('-s ', '').replace(' -s', '')
            emb.description = '⁣'
        if reason.startswith('⠀') or '-c' in reason:  # specially crosspost if disabled
            reason = reason.replace('⠀', '').replace('-c', '')
            emb.description = '⠀'
        if reason.startswith('*by* '):
            emb.description += f'❌ **{str(member)}** was `banned` ({member.id})\n\n' \
                               f'{reason}'
        else:
            emb.description += f'❌ **{str(member)}** was `banned` ({member.id})\n\n'
            if by:
                emb.description += f'*by* {by.name}\n'
            emb.description += f'**Reason**: {reason}'

        emb.set_footer(text=f'User Banned - {member.id}',
                       icon_url=member.display_avatar.replace(static_format="png").url)

        already_added = False  # if the ban event has already been added to the modlog, don't do it here again
        try:
            last_modlog = self.bot.db['modlog'][str(guild.id)][str(member.id)][-1]
            time = datetime.strptime(last_modlog['date'], "%Y/%m/%d %H:%M UTC").replace(tzinfo=timezone.utc)
            if (discord.utils.utcnow() - time).total_seconds() < 70 and last_modlog['type'] == "Ban":
                already_added = True
            if last_modlog['length'] and last_modlog['type'] == 'Ban':
                emb.add_field(name="Temporary ban length", value=last_modlog['length'])
        except KeyError:
            pass

        # if you used the Rai command, then this should've already been run in that command with more info
        if not already_added:
            hf.add_to_modlog(None, [member, guild], 'Ban', reason, False, None)

        ban_emb = emb  # saving for later

        # #################### crossposting ban embed #######################

        colour = 0x9C1313
        if reason:
            for text in ['Automatic ban: Chinese banned words spam', 'Rai automatic word filter ban',
                         'For posting spam link', 'Name was a discord invite link', "On the global blacklist"]:
                if text in reason:
                    colour = 0xDD2E44
            reason = reason.replace('%20', ' ')

        author = re.search(r'^(\*by\* |Issued by: |^)(<@!?)?((?P<ID>\d{17,21})|(?P<name>.*?)#\d{0,4})(> |: |\. )'
                           r'(\(.*?\)\n?\*\*Reason:\*\* |Reason: |)(?P<reason>.*)',
                           reason,
                           flags=re.DOTALL)  # make "." include new lines
        if author:
            if author.group('ID'):
                admin = self.bot.get_user(int(author.group("ID")))
            elif author.group('name'):
                m_server = self.bot.get_guild(M_SERVER)
                admin: Optional[discord.Member] = discord.utils.get(m_server.members, name=author.group('name'))
            else:
                admin = None
            if author.group('reason'):
                re_reason = author.group('reason')
            else:
                re_reason = None
            if admin and re_reason:
                by = admin
                reason = re_reason

        emb = discord.Embed(colour=colour, timestamp=discord.utils.utcnow(),
                            title="GBL Network Ban",
                            description=f"**{str(member)}** － {member.mention}\n({member.id})\n")

        emb.description += f"__Server__: [{guild.name}](https://rai/server-id-is-S{guild.id})\n"

        if by:
            if not by.bot:
                emb.description += f"__Admin__: [{str(by)}](https://rai/admin-id-is-A{by.id})\n"

        messages_in_guild = hf.count_messages(member.id, guild)
        if messages_in_guild:
            emb.set_footer(text=f"Messages: {messages_in_guild}\n",
                           icon_url=member.display_avatar.replace(static_format="png").url)
        else:
            emb.set_footer(text='Ban', icon_url=member.display_avatar.replace(static_format="png").url)

        creation_date = member.created_at.strftime("%Y/%m/%d")
        time_ago = discord.utils.utcnow() - member.created_at
        if time_ago.total_seconds() <= 3600:  # they joined less than a day ago
            creation_date += f" (**__{int(time_ago.total_seconds() // 60)} minutes__** ago)"
        elif 3600 < time_ago.total_seconds() <= 86400:  # they joined less than a day ago
            creation_date += f" (**{int(time_ago.total_seconds() // 3600)} hours** ago)"
        elif 86400 < time_ago.total_seconds() <= 2592000:  # they joined less than a day ago
            creation_date += f" ({int(time_ago.total_seconds() // 86400)} days ago)"
        emb.description += f"__Creation date__: {creation_date}\n"

        if hasattr(member, "joined_at"):  # if it's a user, there will be no join date
            join_date = member.joined_at.strftime("%Y/%m/%d")
            time_ago = discord.utils.utcnow() - member.joined_at
            if time_ago.total_seconds() <= 3600:  # they joined less than a day ago
                join_date += f" (**__{int(time_ago.total_seconds() // 60)} minutes__** ago)"
            elif 3600 < time_ago.total_seconds() <= 86400:  # they joined less than a day ago
                join_date += f" (**{int(time_ago.total_seconds() // 3600)} hours** ago)"
            elif 86400 < time_ago.total_seconds() <= 2592000:  # they joined less than a day ago
                join_date += f" ({int(time_ago.total_seconds() // 86400)} days ago)"
            emb.description += f"__Join date__: {join_date}\n"

        if reason:
            emb.description += f"\n__Reason__: {reason}"

        crosspost_emb = emb

        # #################### END OF CROSSPOSTING EMBED #######################

        return ban_emb, crosspost_emb

    @commands.Cog.listener()
    async def on_member_ban(self, guild, member):
        if not isinstance(member, discord.Member):
            id_to_member_dict = {m.id: m for m in self.bot.recently_removed_members.get(str(guild.id), [])}
            if member.id in id_to_member_dict:
                member = id_to_member_dict[member.id]

        guild_id: str = str(guild.id)
        if guild_id in self.bot.db['bans']:
            guild_config: dict = self.bot.db['bans'][guild_id]
            try:
                ban_emb, crosspost_emb = await self.make_ban_embed(guild, member)
            except discord.Forbidden:
                await self.module_disable_notification(guild, guild_config, 'bans')
                return
            if guild_config['enable']:
                channel = self.bot.get_channel(guild_config["channel"])
                await utils.safe_send(channel, member.id, embed=ban_emb)

            if 'crosspost' in guild_config and member.id not in self.bot.db['bansub']['ignore']:
                # ⁣ is a flag to *skip* crossposting
                # "⠀" is flag to specially *enable* crossposting for one ban
                if (guild_config['crosspost'] and not ban_emb.description.startswith('⁣')) or \
                        (ban_emb.description.startswith('⠀')):
                    bans_channel = self.bot.get_channel(BANS_CHANNEL_ID)
                    crosspost_msg = await bans_channel.send(member.mention, embed=crosspost_emb)
                    mod_channel = self.bot.get_channel(self.bot.db['mod_channel'].get(guild, 0))
                    if mod_channel:
                        try:
                            await utils.safe_send(mod_channel, f"@here {member.mention}", embed=crosspost_emb)
                        except (discord.Forbidden, discord.HTTPException):
                            pass

                    if member.id == self.bot.user.id:
                        return

                    if member not in bans_channel.guild.members:
                        await hf.ban_check_servers(self.bot, bans_channel, member, ping=True, embed=crosspost_emb)

                    await crosspost_msg.add_reaction('⬆')

                    # if member not in bans_channel.guild.members:
                    if member not in bans_channel.guild.members:
                        self.bot.db['banlog'].setdefault(str(member.id), []).append([guild.id, crosspost_msg.id])

        if member.id == ABELIAN_ID:
            try:
                if hasattr(member, 'unban'):
                    await member.unban()
                else:
                    await guild.unban(member)
            except (discord.NotFound, discord.Forbidden):
                pass

            try:
                del (self.bot.db['banlog'][str(ABELIAN_ID)])
            except KeyError:
                pass

            try:
                self.bot.db['global_blacklist']['blacklist'].remove(ABELIAN_ID)
            except ValueError:
                pass

    @staticmethod
    def make_unban_embed(user):
        emb = discord.Embed(
            description=f'❕ **{str(user)}** was `unbanned` ({user.id})',
            colour=0x7F8C8D,
            timestamp=discord.utils.utcnow()
        )
        emb.set_footer(text='User unbanned',
                       icon_url=user.display_avatar.replace(static_format="png").url)
        return emb

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        guild_id = str(guild.id)
        if str(user.id) in self.bot.db['banlog']:  # a list of lists of [guild.id, crosspost_msg.id]
            for entry in self.bot.db['banlog'][str(user.id)]:
                if guild.id == entry[0]:
                    self.bot.db['banlog'][str(user.id)].remove(entry)
                    if not self.bot.db['banlog'][str(user.id)]:
                        del (self.bot.db['banlog'][str(user.id)])  # if the list is now empty
                    try:
                        crosspost_msg = await self.bot.get_channel(329576845949534208).fetch_message(entry[1])
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        pass
                    else:
                        emb = crosspost_msg.embeds[0]
                        emb.colour = 0xFFFFFE  # for some reason, FFFFFF defaults to black, and FFFFFE is fine
                        emb.description.replace('\n', '~~\n')
                        emb.description = f"UNBANNED {discord.utils.utcnow().strftime('%y/%m/%d %H:%M:%S UTC')}\n" \
                                          f"~~{emb.description}~~"
                        await crosspost_msg.edit(embed=emb)

        if guild_id in self.bot.db['bans']:
            guild_config: dict = self.bot.db['bans'][guild_id]
            if guild_config['enable']:
                channel = self.bot.get_channel(guild_config["channel"])
                try:
                    await utils.safe_send(channel, embed=self.make_unban_embed(user))
                except discord.Forbidden:
                    await self.module_disable_notification(guild, guild_config, 'unban')
                    return

    # ############### kicks #####################

    @commands.group(invoke_without_command=True, name='kicks')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def kicks(self, ctx):
        """Logs deleted kicks"""
        result = await self.module_logging(ctx, self.bot.db['kicks'])
        if result == 1:
            await utils.safe_send(ctx, 'Disabled kick logging for this server')
        elif result == 2:
            await utils.safe_send(ctx, 'Enabled kick logging for this server')
        elif result == 3:
            await utils.safe_send(ctx, 'You have not yet set a channel for kick logging yet. Run `;kick_logging set`')
        elif result == 4:
            await utils.safe_send(ctx, 'Before doing this, set a channel for logging with `;kick_logging set`.  '
                                    'Then, enable/disable logging by typing `;kick_logging`.')

    @kicks.command(name='set')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def kicks_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['kicks'])
        if result == 1:
            await utils.safe_send(ctx, f'Set the kick logging channel as {ctx.channel.name}')
        elif result == 2:
            await utils.safe_send(ctx, f'Enabled kick logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                                    f' logging by typing `;kick_logging`.')

    async def make_kick_embed(self, member):
        log_channel = self.bot.get_channel(self.bot.db['kicks'][str(member.guild.id)]['channel'])
        reason = "(could not find audit log entry)"
        kick_entry = None
        try:
            emb = None  # action=discord.AuditLogAction.kick
            async for entry in member.guild.audit_logs(limit=1, oldest_first=False, action=discord.AuditLogAction.kick,
                                                       after=discord.utils.utcnow() - timedelta(seconds=10)):
                if entry.created_at > discord.utils.utcnow() - timedelta(seconds=10) and entry.target == member:
                    kick_entry = entry
                    reason = kick_entry.reason
                    emb = True
        except discord.Forbidden:
            await log_channel.send('I tried to check the audit log to see if a user who just left the server was '
                                   'kicked, but I lack the permission to view the audit log. ')
            return
        if not reason:
            reason = "(no reason given)"

        if emb:
            hf.add_to_modlog(None, [member, member.guild], 'Kick', reason, False, None)
            emb = discord.Embed(
                description=f'❌ **{str(member)}** was `kicked` ({member.id})\n\n'
                            f'*by* {kick_entry.user.mention}\n**Reason**: {reason}',
                colour=0x4C4C4C,
                timestamp=discord.utils.utcnow()
            )
            emb.set_footer(text='User Kicked',
                           icon_url=member.display_avatar.replace(static_format="png").url)
            return emb

    # ############### channel modifications logging #####################

    @commands.group(invoke_without_command=True, name='channels')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def channels(self, ctx):
        """Logs creation, deletion, and modifications to channels"""
        result = await self.module_logging(ctx, self.bot.db['channels'])
        if result == 1:
            await utils.safe_send(ctx, 'Disabled logging of channel modifications for this server')
        elif result == 2:
            await utils.safe_send(ctx, 'Enabled logging of channel modifications for this server')
        elif result == 3:
            await utils.safe_send(ctx, 'You have not yet set a channel for channel logging yet. Run `;channels set`')
        elif result == 4:
            await utils.safe_send(ctx, 'Before doing this, set a channel for logging with `;channels set`.  '
                                    'Then, enable/disable logging by typing `;channels`.')

    @channels.command(name='set')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def channels_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['channels'])
        if result == 1:
            await utils.safe_send(ctx, f'Set the channel logging channel as {ctx.channel.name}')
        elif result == 2:
            await utils.safe_send(ctx,
                               f'Enabled channel logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                               f' logging by typing `;channels`.')

    async def make_channels_embed(self, guild: discord.Guild,
                                  before: Optional[discord.abc.GuildChannel],
                                  after: Optional[discord.abc.GuildChannel]):
        log_channel = self.bot.get_channel(self.bot.db['channels'][str(guild.id)]['channel'])
        author = "(could not find audit log entry)"
        audit_entry = None
        rai_removing_a_block = False

        if before and not after:  # DELETED
            color = 0x9C1313  # red
            action = discord.AuditLogAction.channel_delete
            channel = before
            description = f'🗑️ Channel "**{channel.name}**" ({channel.id}) was `deleted`'

        elif not before and after:  # CREATED
            color = 0x23ddf1  # green
            action = discord.AuditLogAction.channel_create
            channel = after
            description = f'❇️ Channel "**{channel.name}**" ({channel.mention} - {channel.id}) was `created`'
            # above line includes https://emojipedia.org/variation-selector-16/ to specify emoji presentation

        else:  # MODIFIED
            color = 0xff8800  # orange
            action = discord.AuditLogAction.channel_update
            channel = after
            description = f'🛠️ Channel "**`{channel.name}`**" ({channel.mention} - {channel.id}) was `modified`\n'

            if before.position != after.position:
                return  # channel position logs spam the log for many channels in the server

            if before.name != after.name:
                description += f"\nChanged name: `{before.name}` → `{after.name}`"

            if before.permissions_synced != after.permissions_synced:
                description += f"\nPermission sync state changed: " \
                               f"`{before.permissions_synced}` → `{after.permissions_synced}`"

            beforensfw = getattr(before, "nsfw", None)
            afternsfw = getattr(after, "nsfw", None)
            if beforensfw != afternsfw:
                description += f"\nNSFW channel state changed: `{beforensfw}` → `{afternsfw}`"

            beforetopic = getattr(before, "topic", None)
            aftertopic = getattr(after, "topic", None)
            if not beforetopic:
                beforetopic = "[ No Topic Set ]"
            if not aftertopic:
                aftertopic = "[ No Topic Set ]"
            if beforetopic != aftertopic:
                description += f"\nTopic changed: \nBefore:\n`{beforetopic}`\nAfter:\n`{aftertopic}`"

            beforeslow = getattr(before, "slowmode_delay", None)
            afterslow = getattr(after, "slowmode_delay", None)
            if beforeslow != afterslow:
                description += f"Slowmode delay changed: ``{beforeslow}` → `{afterslow}`"

            # PERMISSIONS CHANGE

            modified_overwrites = {}
            settings = {True: "✅", False: "❌", None: "⏺️"}
            blank_overrides = discord.PermissionOverwrite()

            for target in before.overwrites:
                old_overwrite = before.overwrites.get(target, discord.PermissionOverwrite())
                new_overwrite = after.overwrites.get(target, discord.PermissionOverwrite())

                assert isinstance(old_overwrite, discord.PermissionOverwrite), f"old_overwrite: {old_overwrite}, " \
                                                                               f"before: {before}, " \
                                                                               f"after: {after}"
                assert isinstance(new_overwrite, discord.PermissionOverwrite), \
                    f"new_overwrite: {old_overwrite}, before: {before}, after: {after}, " \
                    f"{isinstance(new_overwrite, discord.PermissionOverwrite)}, " \
                    f"{isinstance(new_overwrite, discord.permissions.PermissionOverwrite)}," \
                    f"{type(new_overwrite)}"

                if target not in after.overwrites:  # removed overwrite
                    modified_overwrites[target] = {"before": old_overwrite, "after": blank_overrides}

                else:  # modified overwrite
                    if old_overwrite != new_overwrite:
                        modified_overwrites[target] = {"before": old_overwrite, "after": new_overwrite}

            for target in after.overwrites:
                if target not in before.overwrites:  # created overwrite
                    modified_overwrites[target] = {"before": blank_overrides, "after": after.overwrites[target]}

            if modified_overwrites:
                for ob, ov in modified_overwrites.items():
                    # ob (object) is Role, Member, or Object
                    # ov (overwrites) is a dictionary of {"before": Overwrites, "after": Overwrites}
                    if isinstance(ob, discord.Role):
                        description += f"\nPermissions for role {ob.name} ({ob.mention}) modified:"
                    elif isinstance(ob, discord.Member) or isinstance(ob, discord.User):
                        description += f"\nPermissions for user {str(ob)} ({ob.mention}) modified:"
                    else:
                        description += f"\nPermissions for object {str(ob)} modified:"

                    before_perms: dict[tuple[str, Optional[bool]]] = dict(iter(ov['before']))
                    after_perms: dict[tuple[str, Optional[bool]]] = dict(iter(ov['after']))

                    for perm in before_perms:
                        if before_perms[perm] == after_perms[perm]:
                            continue
                        description += f"\n - `{perm}`: " \
                                       f"{settings[before_perms[perm]]} → {settings[after_perms[perm]]}"

                        # check if it is Rai removing block from user for a channel
                        if perm == 'connect':
                            if before_perms[perm] is False and after_perms[perm] is None:
                                rai_removing_a_block = True

        try:
            audit_entry = None
            async for entry in guild.audit_logs(limit=5, oldest_first=False,
                                                action=action,
                                                after=discord.utils.utcnow() - timedelta(seconds=10)):
                if entry.target.id == channel.id:
                    audit_entry = entry
                    break

            # if it can't find something for channel_update:
            if action == discord.AuditLogAction.channel_update and not audit_entry:
                for action in [discord.AuditLogAction.overwrite_create,
                               discord.AuditLogAction.overwrite_delete,
                               discord.AuditLogAction.overwrite_update]:
                    if audit_entry:
                        break
                    async for entry in guild.audit_logs(limit=5, oldest_first=False,
                                                        action=action,
                                                        after=discord.utils.utcnow() - timedelta(seconds=30)):
                        if entry.created_at > discord.utils.utcnow() - timedelta(seconds=30) and entry.target == after:
                            audit_entry = entry
                            break

        except discord.Forbidden:
            try:
                await log_channel.send('I tried to check the audit log to see who performed the action, '
                                       'but I lack the permission to view the audit log. ')
            except discord.Forbidden:
                pass
            return

        canti = guild.get_member(309878089746219008)
        rai = guild.get_member(270366726737231884)
        if audit_entry:
            if audit_entry.user == canti or \
                    (audit_entry.user == rai and isinstance(channel, (discord.VoiceChannel, discord.StageChannel))):
                return  # canti makes lots of voice channels so exempt those logs
                # and on the sp. serv., Rai temporarily blocks new users from joining voice channels when they try
        else:
            if rai_removing_a_block:
                return  # there is some bug where the bot can't find the entry for this in the audit log

        emb = discord.Embed(
            description=description,
            colour=color,
            timestamp=discord.utils.utcnow(),
        )

        if audit_entry:
            emb.set_footer(text=f"Changed by {str(audit_entry.user)}")

        return emb

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        config = self.bot.db['channels'].get(str(channel.guild.id))
        if not config:
            return
        embed = await self.make_channels_embed(channel.guild, None, channel)
        channel = channel.guild.get_channel(config['channel'])
        if channel and config['enable'] and embed:
            await utils.safe_send(channel, channel.id, embed=embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        config = self.bot.db['channels'].get(str(channel.guild.id))
        if not config:
            return
        embed = await self.make_channels_embed(channel.guild, channel, None)
        channel = channel.guild.get_channel(config['channel'])
        if channel and config['enable'] and embed:
            await utils.safe_send(channel, channel.id, embed=embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        config = self.bot.db['channels'].get(str(after.guild.id))
        if not config:
            return
        embed = await self.make_channels_embed(after.guild, before, after)
        channel = after.guild.get_channel(config['channel'])
        if channel and config['enable'] and embed:
            await utils.safe_send(channel, channel.id, embed=embed)


async def setup(bot):
    await bot.add_cog(Logger(bot))