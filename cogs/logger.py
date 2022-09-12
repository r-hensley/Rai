import aiohttp.client_exceptions
from cv2 import split
import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta, timezone
from Levenshtein import distance as LDist
import re
from .utils import helper_functions as hf

from typing import Optional, List, Tuple, Dict

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
        self.bot = bot
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
        await hf.safe_send(ctx, embed=emb)

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
            await hf.safe_send(channel, f"Disabled the {module_name} logs due to Rai possibly lacking some permission "
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
            await hf.safe_send(ctx, 'Disabled voice logging for this server')
        elif result == 2:
            await hf.safe_send(ctx, 'Enabled voice logging for this server. Embeds have a secret ID '
                                    'inside of that you can find by searching the user ID with "V" in front (like '
                                    '`V202995638860906496`).')
        elif result == 3:
            await hf.safe_send(ctx, 'You have not yet set a channel for voice logging yet. Run `;voice_logging set`')
        elif result == 4:
            await hf.safe_send(ctx, 'Before doing this, set a channel for logging with `;voice_logging set`.  '
                                    'Then, enable/disable logging by typing `;voice_logging`.')

    @voice.command(name='set')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def voice_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['voice'])
        if result == 1:
            await hf.safe_send(ctx, f'Set the voice logging channel as {ctx.channel.name}')
        elif result == 2:
            await hf.safe_send(ctx, f'Enabled voice logging and set the channel to `{ctx.channel.name}`.  '
                                    f'Enable/disable logging by typing `;voice_logging`. Embeds have a secret ID '
                                    f'inside of that you can find by searching the user ID with "V" in front (like '
                                    f'`V202995638860906496`).')

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                    before: discord.VoiceState,
                                    after: discord.VoiceState):
        guild = str(member.guild.id)
        if guild in self.bot.db['voice']:
            guild_config: dict = self.bot.db['voice'][guild]
            if not guild_config['enable'] or not guild_config['channel']:
                guild_config = {}
        else:
            guild_config = {}

        try:
            await self.bot.wait_for('voice_state_update', timeout=0.5, check=lambda m, b, a: m == member)
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
            description = f"➡️ **{member.name}#{member.discriminator}** has `joined` **#{after.channel.name}**."
            color = 0x3B88C3
            footer_text = "Voice Join"
            if after.channel.guild.id == 243838819743432704:
                # self.bot.db['spvoice'].append(("Join",
                # discord.utils.utcnow().timestamp(),
                # member.id, after.channel.id))
                pass

        # leave voice  DD2E44
        elif before.channel and not after.channel:
            description = f"❌ **{member.name}#{member.discriminator}** has `left` **#{before.channel.name}**."
            color = 0xDD2E44
            footer_text = "Voice Leave"
            if before.channel.guild.id == 243838819743432704:
                # self.bot.db['spvoice'].append(("Leave",
                # discord.utils.utcnow().timestamp(),
                # member.id, before.channel.id))
                pass

        # switch channel 🔄️ 3B88C3
        elif before.channel and after.channel and before.channel != after.channel:
            description = f"🔄 **{member.name}#{member.discriminator}** has `switched` from " \
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
            description = f"📳 **{member.name}#{member.discriminator}** has went LIVE and started streaming."
            color = 0xF4900C
            footer_text = "Stream Start"

        # stop self_stream 🔇 CCD6DD
        elif before.self_stream and not after.self_stream:
            description = f"🔇 **{member.name}#{member.discriminator}** has stopped streaming."
            color = 0xCCD6DD
            footer_text = "Stream Stop"

        # start self_video 📳 F4900C
        elif not before.self_video and after.self_video:
            description = f"**{member.name}#{member.discriminator}** has turned on their camera."
            color = 0xF4900C
            footer_text = "Video Start"

        # stop self_video 🔇 CCD6DD
        elif before.self_video and not after.self_video:
            description = f"🔇 **{member.name}#{member.discriminator}** has turned off their camera."
            color = 0xCCD6DD
            footer_text = "Video Stop"

        if not description:  # just in case some case slipped through
            return

        footer_text = f"V{member.id} - " + footer_text

        emb = discord.Embed(description=description, color=color, timestamp=discord.utils.utcnow())
        emb.set_footer(text=footer_text,
                       icon_url=member.display_avatar.replace(static_format="png").url)

        if after.channel:
            users_in_voice = ""
            needed_two_fields = False
            for user in after.channel.members:
                text_to_add = f"\n- [{str(user)}"
                if user.nick:
                    text_to_add += f" ({user.nick})"
                text_to_add += f"](https://rai/participant-id-is-P{user.id})"
                if len(users_in_voice + text_to_add) < 1024:
                    users_in_voice += text_to_add
                else:
                    emb.add_field(name="Users currently in joined voice channel", value=users_in_voice)
                    users_in_voice = text_to_add
                    needed_two_fields = True

            if needed_two_fields:
                emb.add_field(name="User list (cont.)", value=users_in_voice)
            else:
                emb.add_field(name="Users currently in joined voice channel", value=users_in_voice)

        """Voice logging"""
        if guild_config:
            try:
                await hf.safe_send(self.bot.get_channel(guild_config['channel']), embed=emb)
            except (discord.DiscordServerError, aiohttp.client_exceptions.ClientOSError):
                await asyncio.sleep(3)
                try:
                    await hf.safe_send(self.bot.get_channel(guild_config['channel']), embed=emb)
                except discord.DiscordServerError:
                    pass

        """ Super voice watch"""
        if config:
            b = before.channel
            a = after.channel
            if a and not b:
                if member.id in config['users']:
                    try:
                        await hf.safe_send(channel, member.id, embed=emb)
                    except discord.Forbidden:
                        pass

                forty_eight_hours_in_seconds = 60 * 60 * 48
                if (discord.utils.utcnow() - member.created_at).total_seconds() < forty_eight_hours_in_seconds:
                    emb.description += "\n(Newly created account joining voice):"
                    emb.description += f"\nCreation date: <t:{int(member.created_at.timestamp())}>"
                    emb.description += f"\nJoin date: <t:{int(member.joined_at.timestamp())}>"
                    if hf.calculate_voice_time(member.id, member.guild.id) < 60 * 60:  # 60 mins
                        try:
                            await hf.safe_send(channel, member.id, embed=emb)
                        except discord.Forbidden:
                            pass

                bronox = member.guild.get_member(894817002672259072)
                if bronox:
                    if bronox in a.members:
                        # 'jason' in the database is a timestamp showing the last time a jason alt was banned
                        if member.created_at.timestamp() > self.bot.db['jason']:
                            emb.description += "\n(An account that was created after the last time Jason was banned " \
                                               "has joined a voice channel with Bronox)"
                            try:
                                await hf.safe_send(channel, member.id, embed=emb)
                            except discord.Forbidden:
                                pass

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
        await hf.safe_send(self.bot.get_channel(guild_config['channel']), embed=emb)

    # ############### edits #####################

    @commands.group(invoke_without_command=True, name='edits')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def edit_logging(self, ctx):
        """Logs edited messages"""
        result = await self.module_logging(ctx, self.bot.db['edits'])
        if result == 1:
            await hf.safe_send(ctx, 'Disabled edit logging for this server')
        elif result == 2:
            await hf.safe_send(ctx, 'Enabled edit logging for this server')
        elif result == 3:
            await hf.safe_send(ctx, 'You have not yet set a channel for edit logging yet. Run `;edit_logging set`')
        elif result == 4:
            self.bot.db['edits'][str(ctx.guild.id)]['distance_limit'] = 3
            await hf.safe_send(ctx, 'Before doing this, set a channel for logging with `;edit_logging set`.  '
                                    'Then, enable/disable logging by typing `;edit_logging`.')

    @edit_logging.command(name='set')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def edits_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['edits'])
        if result == 1:
            await hf.safe_send(ctx, f'Set the edit logging channel as {ctx.channel.name}')
        elif result == 2:
            self.bot.db['edits'][str(ctx.guild.id)]['distance_limit'] = 3
            await hf.safe_send(ctx, f'Enabled edit logging and set the channel to `{ctx.channel.name}`.  '
                                    f'Enable/disable logging by typing `;edit_logging`.')

    @edit_logging.command(aliases=['set_distance'])
    async def distance_set(self, ctx, distance_limit: int = 3):
        """Sets the Levenshtein Distance limit for edited messages logs. Anything below this limit won't get counted\
        as an edit (the Levenshtein Distance measures the distance between strings)."""
        guild = str(ctx.guild.id)
        guild_config: dict = self.bot.db['edits'][guild]
        guild_config['distance_limit'] = distance_limit
        await hf.safe_send(ctx, f'Successfully set Levenshtein Distance limit to {distance_limit}.')

    @staticmethod
    def make_edit_embed(before, after, levenshtein_distance):
        author = before.author
        time_dif = round((discord.utils.utcnow() - before.created_at).total_seconds(), 1)
        emb = discord.Embed(
            description=f'**{author.name}#{author.discriminator}** (M{author.id})'
                        f'\n**Message edited after {time_dif} seconds.** [(LD={levenshtein_distance})]'
                        f'(https://en.wikipedia.org/wiki/Levenshtein_distance) - ([Jump URL]({after.jump_url}))',
            colour=0xFF9933,
            timestamp=discord.utils.utcnow()
        )

        if len(before.content) > 0 and len(after.content) > 0:
            if len(before.content) < 1025:
                emb.add_field(name='**Before:**', value=before.content)
            else:
                emb.add_field(name='**Before:** (Part 1):', value=before.content[:1000])
                emb.add_field(name='**Before:** (Part 2):', value=before.content[1000:2000])

            if len(after.content) < 1025:
                emb.add_field(name='**After:**', value=after.content)
            else:
                emb.add_field(name='**After:** (Part 1)', value=after.content[:1000])
                emb.add_field(name='**After:** (Part 2)', value=after.content[1000:2000])

        emb.set_footer(text=f'#{before.channel.name}',
                       icon_url=before.author.display_avatar.replace(static_format="png").url)

        return emb

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
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
                        await hf.safe_send(channel, 'Please set a Levenshtein Distance with `;edit set_distance 3`')
                        return
                    levenshtein_distance = LDist(before.content, after.content)
                    if levenshtein_distance > distance_limit:
                        channel = self.bot.get_channel(guild_config["channel"])
                        try:
                            await hf.safe_send(channel, embed=self.make_edit_embed(before, after,
                                                                                   levenshtein_distance))
                        except discord.Forbidden:
                            await self.module_disable_notification(before.message.guild, guild_config, 'message edits')
        await hf.uhc_check(after)

    # ############### deletes #####################

    @commands.group(invoke_without_command=True)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def deletes(self, ctx):
        """Logs deleted messages"""
        result = await self.module_logging(ctx, self.bot.db['deletes'])
        if result == 1:
            await hf.safe_send(ctx, 'Disabled delete logging for this server')
        elif result == 2:
            await hf.safe_send(ctx, 'Enabled delete logging for this server')
        elif result == 3:
            await hf.safe_send(ctx, 'You have not yet set a channel for delete logging yet. Run `;delete_logging set`')
        elif result == 4:
            await hf.safe_send(ctx, 'Before doing this, set a channel for logging with `;delete_logging set`.  '
                                    'Then, enable/disable logging by typing `;delete_logging`.')

    @deletes.command(name='set')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def deletes_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['deletes'])
        if result == 1:
            await hf.safe_send(ctx, f'Set the delete logging channel as {ctx.channel.name}')
        elif result == 2:
            await hf.safe_send(ctx,
                               f'Enabled delete logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                               f' logging by typing `;delete_logging`.')

    async def make_delete_embed(self, message):
        author = message.author
        time_dif = round((discord.utils.utcnow() - message.created_at).total_seconds(), 1)
        jump_url = ''
        async for msg in message.channel.history(limit=1, before=message):
            jump_url = msg.jump_url
        emb = discord.Embed(
            description=f'**{author.name}#{author.discriminator}** (M{author.id})'
                        f'\n**Message deleted after {time_dif} seconds.** ([Jump URL]({jump_url}))',
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

        return emb

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if ';report' in message.content:
            return  # for keeping anonymous reports anonymous
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
            log_message = await hf.safe_send(channel, embed=await self.make_delete_embed(message))
            await hf.send_attachments_to_thread_on_message(log_message, message)
        except discord.Forbidden:
            await self.module_disable_notification(message.guild, guild_config, 'message deletes')

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
            emb = hf.red_embed(text)
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
            emb = hf.red_embed(text)

        try:
            await hf.safe_send(channel, embed=emb, file=file)
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
            await hf.safe_send(ctx, 'Disabled join logging for this server')
        elif result == 2:
            try:
                invites = await ctx.guild.invites()
                server_config['invites'] = await self.make_invites_dict(ctx.guild, invites)
                server_config['invites_enable'] = True
                await hf.safe_send(ctx,
                                   'Enabled join logging + invite tracking for this server (type `;joins invites` to '
                                   'disable invite tracking)')
            except discord.Forbidden:
                await hf.safe_send(ctx, "I've enabled join tracking, but I lack permissions to get invite codes.  "
                                        "If you want invite tracking too, give me `Manage Server` and then type "
                                        f"`{ctx.message.content} invites` to enable invite tracking for future joins.")
                server_config['invites_enable'] = False

        elif result == 3:
            await hf.safe_send(ctx,
                               'You have not yet set a channel for join logging yet. Run `;joins set`')
        elif result == 4:
            await hf.safe_send(ctx, 'Before doing this, set a channel for logging with `;joins set`.  '
                                    'Then, enable/disable logging by typing `;joins`.')

    @joins.command(name='set')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def joins_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['joins'])
        server_config = self.bot.db['joins'][str(ctx.guild.id)]
        if result == 1:
            await hf.safe_send(ctx, f'Set the join logging channel as {ctx.channel.name}')
        elif result == 2:
            try:
                invites = await ctx.guild.invites()
                server_config['invites'] = await self.make_invites_dict(ctx.guild, invites)
                server_config['invites_enable'] = True
                await hf.safe_send(ctx,
                                   f'Enabled join logging + invite tracking / set the channel to `{ctx.channel.name}`.'
                                   f'  Enable/disable logging by typing `;joins`.')
            except discord.Forbidden:
                await hf.safe_send(ctx, "I've enabled join logging, but I lack permissions to get invite codes.  "
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
                await hf.safe_send(ctx, f"Set invite tracking to `{server_config['invites_enable']}`")
            except KeyError:
                server_config['invites_enable'] = True
                await hf.safe_send(ctx, 'Enabled invites tracking')
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
            description=f":inbox_tray: **[{member.name}#{member.discriminator}](https://rai/user-id-is-J{member.id})** "
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
                field_value += f" by {invite.inviter.name}#{invite.inviter.discriminator} " \
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
                await hf.safe_send(ctx, f'Set welcome message posting to {x}')
            except KeyError:
                config['enable'] = True
                x = config['enable']
                await hf.safe_send(ctx, f'Set welcome message posting to {x}')
        else:
            self.bot.db['welcome_message'][guild] = {}
            config = self.bot.db['welcome_message'][guild]
            config['enable'] = True
            x = config['enable']
            await hf.safe_send(ctx, f'Set welcome message posting to {x}')

    @welcome_message.command()
    async def set_message(self, ctx, *, message: str = None):
        if not message:
            text = ('Please put your welcome message after the command invocation.  For example: \n'
                    '```;welcome_message set_message Welcome to the server `$NAME$`! Please read the rules```\n'
                    "Valid flags to use are: \n$NAME$ = The user's name in text\n`$USERMENTION$` = Mentions "
                    "the user\n`$SERVER$` = The name of the server")
            await hf.safe_send(ctx, text)
        else:
            try:
                config = self.bot.db['welcome_message'][str(ctx.guild.id)]
            except KeyError:
                await hf.safe_send(ctx, "Run `;welcome_message` first to setup the module")
                return
            config['message'] = message
            await hf.safe_send(ctx, f"Set welcome message to ```{message}```")

    @welcome_message.command()
    async def set_channel(self, ctx):
        try:
            config = self.bot.db['welcome_message'][str(ctx.guild.id)]
        except KeyError:
            await ctx.invoke(self.welcome_message)
            config = self.bot.db['welcome_message'][str(ctx.guild.id)]
        config['channel'] = ctx.channel.id
        await hf.safe_send(ctx, f"Set welcome message channel to {ctx.channel.mention}")

    @welcome_message.command()
    async def show_message(self, ctx):
        config = self.bot.db['welcome_message'][str(ctx.guild.id)]
        await hf.safe_send(ctx, "```" + config['message'] + "```")

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
        """auto role"""

        async def auto_role():
            if member.guild.id == SPAN_SERV_ID:
                category_roles = [member.guild.get_role(802629332425375794),
                                  member.guild.get_role(802657919400804412),
                                  member.guild.get_role(1002681814734880899)]

                for role in category_roles.copy():
                    if not role:
                        category_roles.remove(role)

                if (discord.utils.utcnow() - member.created_at) > timedelta(weeks=2):
                    try:
                        await member.add_roles(*category_roles)
                    except (discord.Forbidden, discord.HTTPException):
                        pass

        await auto_role()

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
                    await hf.safe_send(_welcome_channel, message)
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
                    await hf.safe_send(log_channel, "I tried to post a join notification but I lack the permission to"
                                                    " post embeds. Please give me the permission to embed links.")
                except discord.Forbidden:
                    del server_config
                return
            if server_config['invites_enable'] and not member.guild.me.guild_permissions.manage_guild:
                disable_message = "Invite tracking is currently enabled, but Discord requries the `Manage Server` " \
                                  "permission to view invite links. Please give Rai this persmission then type " \
                                  "`;joins invites` to reenable the tracking of invite links."
                await hf.safe_send(log_channel, disable_message)
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
                    if member.guild.id == SPAN_SERV_ID:
                        # Category roles
                        list_of_readd_roles.append(member.guild.get_role(802629332425375794))
                        list_of_readd_roles.append(member.guild.get_role(802657919400804412))
                        list_of_readd_roles.append(member.guild.get_role(1002681814734880899))
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
            log_message = await hf.safe_send(log_channel, member.id, embed=x)

            # Logging join info for modlog pulls
            recorded_info = {}
            if log_message:
                recorded_info['jump_url'] = log_message.jump_url

            if used_invite:
                recorded_info['invite'] = getattr(used_invite[0], "code", None)
                # invite_creator = getattr(used_invite[0].inviter, "id", None)

            server_config.setdefault('join_history', {})[str(member.id)] = recorded_info

            # Special Japanese server invite management
            if guild_id == str(JP_SERV_ID) and used_invite:
                jpJHO = self.bot.get_channel(JP_SERV_JHO_ID)
                # check if they joined from a Japanese site or other
                # the following links are specifically the ones we've used to advertise on japanese sites
                japanese_links = ['6DXjBs5', 'WcBF7XZ', 'jzfhS2', 'w6muGjF', 'TxdPsSm', 'MF9XF89', 'RJrcSb3']
                JHO_msg = f"Welcome {member.name}!"
                for link in used_invite:
                    if type(link) == str:
                        continue
                    if link.code in japanese_links:
                        JHO_msg = f'{member.name}さん、サーバーへようこそ！'
                        break
                if list_of_readd_roles:
                    JHO_msg += " I've readded your previous roles to you!"
                    await asyncio.sleep(2)
                    new_user_role = member.guild.get_role(249695630606336000)
                    if new_user_role in member.roles:
                        await member.remove_roles(new_user_role)
                try:
                    await hf.safe_send(jpJHO, JHO_msg)
                except (discord.Forbidden, discord.HTTPException):
                    pass

                if member.id == ABELIAN_ID:  # secret entry for Abelian
                    async for message in jpJHO.history(limit=10):
                        if message.author.id == 159985870458322944:
                            await message.delete()
                            break
                    try:
                        def check(m):
                            return m.author.id == 299335689558949888 and m.channel == jpJHO
                        msg = await self.bot.wait_for('message', timeout=10.0, check=check)
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
                    await hf.safe_send(channel,
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
                        await hf.safe_send(bans_channel, embed=hf.red_embed("WARNING: I tried to ban a user for being "
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
            emb = hf.red_embed(f"WARNING: The user **{str(member)}** ({member.id}) has joined **{member.guild.name}**"
                               f"\n\nThey were banned before on the following servers:\n")
            emb.color = 0x8013E0

            for entry in config:
                banned_guild = self.bot.get_guild(entry[0])
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
                            await hf.safe_send(mod_channel, f"{member.mention}\n{pings} (@here)", embed=emb)
                            sent_to_mod_channel = True
                        except (discord.Forbidden, discord.HTTPException):
                            pass

                if config:  # this will be False if the last entry in config was deleted above from the NotFound error
                    if sent_to_mod_channel:
                        msg = f"{member.mention}"
                    else:
                        msg = f"{member.mention}\n{pings}"
                    await hf.safe_send(bans_channel, msg, embed=emb)

                else:
                    del (self.bot.db['banlogs'][str(member.id)])  # cleanup

            hf.add_to_modlog(None, [member, member.guild], 'Log', emb.description, False, None)

    # ############### leaves #####################

    @commands.group(invoke_without_command=True, name='leaves')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def leaves(self, ctx):
        """Logs leaves + shows list of roles at time of leave"""
        result = await self.module_logging(ctx, self.bot.db['leaves'])
        if result == 1:
            await hf.safe_send(ctx, 'Disabled leave logging for this server')
        elif result == 2:
            await hf.safe_send(ctx, 'Enabled leave logging for this server')
        elif result == 3:
            await hf.safe_send(ctx, 'You have not yet set a channel for leave logging yet. Run `;leave_logging set`')
        elif result == 4:
            await hf.safe_send(ctx, 'Before doing this, set a channel for logging with `;leave_logging set`.  '
                                    'Then, enable/disable logging by typing `;leave_logging`.')

    @leaves.command(name='set')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def leaves_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['leaves'])
        if result == 1:
            await hf.safe_send(ctx, f'Set the leave logging channel as `{ctx.channel.name}`')
        elif result == 2:
            await hf.safe_send(ctx,
                               f'Enabled leave logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                               f' logging by typing `;leave_logging`.')

    @staticmethod
    def make_leave_embed(member):
        emb = discord.Embed(
            description=''
                        f":outbox_tray: **[{member.name}#{member.discriminator}](https://rai/user-id-is-J{member.id})**"
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
                    await hf.safe_send(channel, member.id, embed=self.make_leave_embed(member))
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
                            role.id in [249695630606336000, member.guild.id, 645021058184773643,
                                        802629332425375794, 802657919400804412, 1002681814734880899,  # category roles
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
                    await hf.safe_send(channel, embed=emb)

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
            await hf.safe_send(ctx, 'Disabled nickname logging for this server')
        elif result == 2:
            await hf.safe_send(ctx, 'Enabled nickname logging for this server')
        elif result == 3:
            await hf.safe_send(ctx,
                               'You have not yet set a channel for nickname logging yet. Run `;nickname_logging set`')
        elif result == 4:
            await hf.safe_send(ctx, 'Before doing this, set a channel for logging with `;nickname_logging set`.  '
                                    'Then, enable/disable logging by typing `;nickname_logging`.')

    @nicknames.command(name='set')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def nicknames_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['nicknames'])
        if result == 1:
            await hf.safe_send(ctx, f'Set the nickname logging channel as `{ctx.channel.name}`')
        elif result == 2:
            await hf.safe_send(ctx,
                               f'Enabled nickname logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                               f' logging by typing `;nickname_logging`.')

    @staticmethod
    def make_nickname_embed(before, after):
        emb = discord.Embed(timestamp=discord.utils.utcnow())
        emb.set_footer(
            text=f'{after.name}#{before.discriminator} (N{before.id})',
            icon_url=before.display_avatar.replace(static_format="png").url
        )
        return emb

    @commands.Cog.listener()
    async def on_user_update(self, before, after):
        if before.name == after.name:
            return

        for g in self.bot.guilds:
            guild = str(g.id)
            if before not in g.members:
                continue  # don't worry about guilds without this member
            if not self.bot.db['nicknames'].get(guild, {'enable': False})['enable']:
                continue  # if the guild doesn't have username changes enabled

            channel = self.bot.get_channel(self.bot.db['nicknames'][guild]['channel'])
            if not channel:
                continue

            emb = self.make_nickname_embed(before, after)
            emb.description = f"**{before.name}#{before.discriminator}**'s username was set to " \
                              f"**{after.name}#{after.discriminator}**"
            emb.colour = 0xFF8800
            try:
                await hf.safe_send(channel, embed=emb)
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_member_update(self: commands.Cog, before: discord.Member, after: discord.Member):
        # ######### Nicknames #############
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
                emb.description = f"**{before.nick}**'s nickname was **removed**"
            elif not before.nick and after.nick:  # nickname added
                emb.description = f"**{before.name}#{before.discriminator}**'s nickname was set to **{after.nick}**"
            elif before.nick and after.nick:  # nickname changed
                emb.description = f"**{before.nick}**'s nickname was changed to **{after.nick}**"
            try:
                await hf.safe_send(channel, embed=emb)
            except discord.Forbidden:
                pass

        await check_nickname_change()

        # ######### Timeouts #############
        async def check_timeouts():
            if not (self.bot.db['modlog'].get(str(before.guild.id), None)):
                return  # guild has not setup modlog

            if not (not before.is_timed_out() and after.is_timed_out()):
                return  # event is not a timeout event

            guild = before.guild
            attempts = 0
            time_left = None
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
                        time_left = (after.timed_out_until - discord.utils.utcnow()).total_seconds()
                        reason = entry.reason

                        if reason:
                            if "SELFMUTE" in reason and len(split(reason)) == 1:  # for RAI_SELFMUTE or CIRI_SELFMUTE":
                                return

                        if time_left < 70:  # 60 SEC
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
                await asyncio.sleep(15)

            if not time_left:
                return  # No matching entries found

            emb = hf.red_embed("")
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

            try:
                await hf.safe_send(after, embed=emb)
            except discord.Forbidden:
                try:
                    await hf.safe_send(author, "Notification: I was unable to notify the user of the timeout due to "
                                               "their privacy settings.", embed=emb)
                except (discord.Forbidden, discord.HTTPException):
                    pass

            emb.set_footer(text=f"Muted by {author.name} ({author.id})")
            modlog_channel = self.bot.get_channel(self.bot.db['modlog'][str(guild.id)]['channel'])
            if modlog_channel:
                notif_msg = await hf.safe_send(modlog_channel, str(after.id), embed=emb)
                ctx = await self.bot.get_context(notif_msg)
                hf.add_to_modlog(ctx, after, 'Timeout', reason, False, timeout_length_str)
            else:
                hf.add_to_modlog(None, [after, after.guild], 'Timeout', reason, False, timeout_length_str)

        await check_timeouts()

        # ######### Role change #############
        async def check_role_change():
            if after.guild.id != SPAN_SERV_ID:
                return

            category_roles = [after.guild.get_role(802629332425375794),
                              after.guild.get_role(802657919400804412),
                              after.guild.get_role(1002681814734880899)]
            native_lang_roles = [after.guild.get_role(243853718758359040),  # eng native
                                 after.guild.get_role(243854128424550401),  # sp native
                                 after.guild.get_role(247020385730691073)]  # other native

            lang_role_change = False
            for role in native_lang_roles:
                if role not in before.roles and role in after.roles:
                    lang_role_change = True
                    break

            if lang_role_change:
                try:
                    await after.add_roles(*category_roles)
                except (discord.Forbidden, discord.HTTPException):
                    pass

        await check_role_change()

    # ############### reaction removals #####################

    @commands.group(invoke_without_command=True, name='reactions')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def reactions(self, ctx):
        """Logs deleted reactions"""
        result = await self.module_logging(ctx, self.bot.db['reactions'])
        if result == 1:
            await hf.safe_send(ctx, 'Disabled reaction logging for this server')
        elif result == 2:
            await hf.safe_send(ctx, 'Enabled reaction logging for this server')
        elif result == 3:
            await hf.safe_send(ctx,
                               'You have not yet set a channel for reaction logging yet. Run `;reaction_logging set`')
        elif result == 4:
            await hf.safe_send(ctx, 'Before doing this, set a channel for logging with `;reaction_logging set`.  '
                                    'Then, enable/disable logging by typing `;reaction_logging`.')

    @reactions.command(name='set')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def reactions_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['reactions'])
        if result == 1:
            await hf.safe_send(ctx, f'Set the reaction logging channel as {ctx.channel.name}')
        elif result == 2:
            await hf.safe_send(ctx,
                               f'Enabled reaction logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                               f' logging by typing `;reaction_logging`.')

    @staticmethod
    def make_reaction_embed(emoji, member, message, message_id, channel):
        jump_url = f"https://discord.com/channels/{channel.guild.id}/{channel.id}/{message_id}"
        emb = discord.Embed(
            description=f"**{member.name}#{member.discriminator}** (R{member.id}) "
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
            await hf.safe_send(log_channel,
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
            await hf.safe_send(ctx,
                               "I lack the permission to either view audit logs or embed links.  Please try again.")
            return
        result = await self.module_logging(ctx, self.bot.db['bans'])
        if result == 1:
            await hf.safe_send(ctx, 'Disabled ban logging for this server')
        elif result == 2:
            await hf.safe_send(ctx, 'Enabled ban logging for this server')
        elif result == 3:
            await hf.safe_send(ctx, 'You have not yet set a channel for ban logging yet. Run `;ban_logging set`')
        elif result == 4:
            await hf.safe_send(ctx, 'Before doing this, set a channel for logging with `;ban_logging set`.  '
                                    'Then, enable/disable logging by typing `;ban_logging`.')

    @bans.command(name='set', short_name='set')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def bans_set(self, ctx):
        self.short_name = 'set'
        result = await self.module_set(ctx, self.bot.db['bans'])
        if result == 1:
            await hf.safe_send(ctx, f'Set the ban logging channel as {ctx.channel.name}')
        elif result == 2:
            await hf.safe_send(ctx, f'Enabled ban logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                                    f' logging by typing `;ban_logging`.')

    async def make_ban_embed(self, guild, member):
        ban_entry = None
        reason = "(could not find audit log entry)"
        by = None

        # ################## NORMAL BAN EMBED #########################

        await asyncio.sleep(3)
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
            await asyncio.sleep(15)
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
            emb.description += f'❌ **{member.name}#{member.discriminator}** was `banned` ({member.id})\n\n' \
                               f'{reason}'
        else:
            emb.description += f'❌ **{member.name}#{member.discriminator}** was `banned` ({member.id})\n\n'
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
                           r'(\(.*?\)\n?\*\*Reason:\*\* |Reason: |)(?P<reason>.*)', reason)
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

        messages_in_guild = hf.count_messages(member, guild)
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
                await hf.safe_send(channel, member.id, embed=ban_emb)

            if 'crosspost' in guild_config and member.id not in self.bot.db['bansub']['ignore']:
                # ⁣ is a flag to *skip* crossposting
                # "⠀" is flag to specially *enable* crossposting for one  ban
                if (guild_config['crosspost'] and not ban_emb.description.startswith('⁣')) or \
                        (ban_emb.description.startswith('⠀')):
                    bans_channel = self.bot.get_channel(BANS_CHANNEL_ID)
                    crosspost_msg = await bans_channel.send(member.mention, embed=crosspost_emb)
                    mod_channel = self.bot.get_channel(self.bot.db['mod_channel'].get(guild, 0))
                    if mod_channel:
                        try:
                            await hf.safe_send(mod_channel, f"@here {member.mention}", embed=crosspost_emb)
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
            description=f'❕ **{user.name}#{user.discriminator}** was `unbanned` ({user.id})',
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
                        emb.color = 0xFFFFFE  # for some reason, FFFFFF defaults to black, and FFFFFE is fine
                        emb.description.replace('\n', '~~\n')
                        emb.description = f"UNBANNED {discord.utils.utcnow().strftime('%y/%m/%d %H:%M:%S UTC')}\n" \
                                          f"~~{emb.description}~~"
                        await crosspost_msg.edit(embed=emb)

        if guild_id in self.bot.db['bans']:
            guild_config: dict = self.bot.db['bans'][guild_id]
            if guild_config['enable']:
                channel = self.bot.get_channel(guild_config["channel"])
                try:
                    await hf.safe_send(channel, embed=self.make_unban_embed(user))
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
            await hf.safe_send(ctx, 'Disabled kick logging for this server')
        elif result == 2:
            await hf.safe_send(ctx, 'Enabled kick logging for this server')
        elif result == 3:
            await hf.safe_send(ctx, 'You have not yet set a channel for kick logging yet. Run `;kick_logging set`')
        elif result == 4:
            await hf.safe_send(ctx, 'Before doing this, set a channel for logging with `;kick_logging set`.  '
                                    'Then, enable/disable logging by typing `;kick_logging`.')

    @kicks.command(name='set')
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def kicks_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['kicks'])
        if result == 1:
            await hf.safe_send(ctx, f'Set the kick logging channel as {ctx.channel.name}')
        elif result == 2:
            await hf.safe_send(ctx, f'Enabled kick logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
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
                description=f'❌ **{member.name}#{member.discriminator}** was `kicked` ({member.id})\n\n'
                            f'*by* {kick_entry.user.mention}\n**Reason**: {reason}',
                colour=0x4C4C4C,
                timestamp=discord.utils.utcnow()
            )
            emb.set_footer(text='User Kicked',
                           icon_url=member.display_avatar.replace(static_format="png").url)
            return emb


async def setup(bot):
    await bot.add_cog(Logger(bot))
