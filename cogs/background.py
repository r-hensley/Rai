import asyncio
import os
import sys
import time

from datetime import datetime, timezone
import traceback
import discord
from discord.ext import commands, tasks
from cogs.utils.BotUtils import bot_utils as utils

RYRY_SPAM_CHAN = 275879535977955330
TRACEBACK_LOGGING_CHANNEL_ID = int(os.getenv("TRACEBACK_LOGGING_CHANNEL"))


class Background(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.bg_tasks = {self.check_desync_voice, self.unban_users,
                             self.unmute_users, self.unselfmute_users, self.delete_old_stats_days,
                             self.check_downed_tasks, self.save_db, self.live_latency, self.fireside_message}
        self.bot.running_tasks = []
        task_names = {task.coro.__name__ for task in self.bot.bg_tasks}
        for task in asyncio.all_tasks():
            # looks like:
            # discord-ext-tasks: Background.save_db
            # discord.py: on_message
            # discord.py: on_command
            # discord-ext-tasks: Background.check_downed_tasks
            # discord-ext-tasks: Background.delete_old_stats_days
            # Task-25755
            # Task-29581
            # discord-ext-tasks: Background.unselfmute_users
            # discord.py: on_message
            # [ ... ]
            name = task.get_name().replace("discord-ext-tasks: Background.", "")
            # now "name" is the same as the name of the coro here in this file (e.g. "save_db")
            if name in task_names:
                task.cancel()
            
        for task in self.bot.bg_tasks:
            if not task.is_running():
                task.start()
                self.bot.running_tasks.append(task)
                
        for task in self.bot.running_tasks:
            # remove tasks that are finished from the list
            if not task.is_running():
                self.bot.running_tasks.remove(task)

    def cog_unload(self):
        for task in self.bot.bg_tasks:
            task.cancel()
            
        for task in self.bot.running_tasks:
            # remove tasks that are finished from the list
            if not task.is_running():
                self.bot.running_tasks.remove(task)

    async def handle_error(self, error):
        error = getattr(error, 'original', error)
        print('Error in background task:', file=sys.stderr)
        traceback.print_tb(error.__traceback__)
        print(f'{error.__class__.__name__}: {error}', file=sys.stderr)
        # get traceback channel ID from env
        channel = self.bot.get_channel(TRACEBACK_LOGGING_CHANNEL_ID)
        exc = ''.join(traceback.format_exception(type(error), error, error.__traceback__, chain=False))
        traceback_text = f'```py\n{exc}\n```'
        message = f'<@202995638860906496> Error in background task:\n{traceback_text}'
        if len(message) < 2000:
            await channel.send(message)
        else:
            await channel.send(message[:2000])
            await channel.send(message[2000:4000])

    @commands.command()
    @commands.is_owner()
    async def checkbg(self, ctx):
        s = ''
        for task in self.bot.bg_tasks:
            if not task.is_running():
                s += f"X: {task.coro.__name__}\n"
        if s:
            await utils.safe_send(ctx, s)
        else:
            try:
                await ctx.message.add_reaction("✅")
            except (discord.Forbidden, discord.NotFound):
                pass

    @tasks.loop(hours=1.0)
    async def check_downed_tasks(self):
        ch = self.bot.get_channel(RYRY_SPAM_CHAN)
        for task in self.bot.bg_tasks:
            if not task.is_running():
                await utils.safe_send(ch, f"{task.coro.__name__} ISN'T RUNNING!")

    @tasks.loop(minutes=10.0)
    async def save_db(self):
        if getattr(self.bot, 'db', None) is not None:
            await utils.dump_json('db')
        else:
            print("main database not yet fully loaded, so skipping db saving")
        
        if getattr(self.bot, 'stats', None) is not None:
            await utils.dump_json('stats')
        else:
            print("stats database not yet fully loaded, so skipping stats saving")
            
        if getattr(self.bot, 'message_queue', None) is not None:
            await utils.dump_json('message_queue')
        else:
            print("message queue not yet fully loaded, so skipping message queue saving")
    
    @tasks.loop(minutes=5.0)
    async def check_desync_voice(self):
        config = self.bot.stats
        for guild_id in list(config):
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                del config[guild_id]
                continue
            ctx = self.bot.ctx
            ctx.guild = guild

            if guild_id not in config:
                continue
            if not config[guild_id]['enable']:
                continue
            guild_config = config[guild_id]
            guild = self.bot.get_guild(int(guild_id))
            try:
                voice_channels = guild.voice_channels
            except AttributeError:
                continue
            users_in_voice = []
            for channel in voice_channels:
                users_in_voice += [str(member.id) for member in channel.members]
            for user_id in list(guild_config['voice']['in_voice']):  # all users in the database
                if user_id not in users_in_voice:  # if not in voice, remove from database
                    member = guild.get_member(int(user_id))
                    if not member:
                        del guild_config['voice']['in_voice'][user_id]
                        return
                    await ctx.invoke(self.bot.get_command("command_out_of_voice"), member)

            for user_id in list(users_in_voice):  # all users in voice
                member = guild.get_member(int(user_id))
                vs = member.voice
                if vs:
                    if vs.deaf or vs.self_deaf or vs.afk:  # deafened or afk but in database, remove
                        await ctx.invoke(self.bot.get_command("command_out_of_voice"), member)
                    if user_id not in guild_config['voice']['in_voice']:  # in voice, not in database, add
                        if vs.channel:
                            await ctx.invoke(self.bot.get_command("command_into_voice"), member, vs)
                else:
                    await ctx.invoke(self.bot.get_command("command_out_of_voice"), member)  # in voice but no vs? remove

    @check_desync_voice.error
    async def check_desync_voice_error(self, error):
        await self.handle_error(error)

    @tasks.loop(minutes=5.0)
    async def unban_users(self):
        config = self.bot.db['bans']
        for guild_id in config:
            unbanned_users: list[str] = []
            guild_config = config[guild_id]
            try:
                mod_channel = self.bot.get_channel(self.bot.db['mod_channel'][guild_id])
            except KeyError:
                mod_channel = None
            if 'timed_bans' in guild_config:
                for member_id in list(guild_config['timed_bans']):
                    member_id: str
                    unban_time = datetime.strptime(
                        guild_config['timed_bans'][member_id], "%Y/%m/%d %H:%M UTC").replace(tzinfo=timezone.utc)
                    if unban_time < discord.utils.utcnow():
                        guild = self.bot.get_guild(int(guild_id))
                        member = discord.Object(id=member_id)
                        try:
                            await guild.unban(member, reason="End of timed ban")
                        except (discord.NotFound, discord.Forbidden, AttributeError):
                            pass
                        finally:
                            del config[guild_id]['timed_bans'][member_id]
                            unbanned_users.append(member_id)
            if mod_channel and unbanned_users:
                text_list = []
                for i in unbanned_users:
                    user = self.bot.get_user(int(i))
                    if not user:
                        try:
                            user = await self.bot.fetch_user(int(i))
                        except (discord.NotFound, discord.HTTPException):
                            continue
                    text_list.append(f"{user.mention} ({user.name})")
                if not text_list:
                    return  # weird scenario where a user was unbanned but it coudldn't find their account afterwards
                await utils.safe_send(mod_channel,
                                   embed=discord.Embed(description=f"I've unbanned {', '.join(text_list)}, as "
                                                                   f"the time for their temporary ban has expired",
                                                       color=discord.Color(int('00ffaa', 16))))

    @unban_users.error
    async def unban_users_error(self, error):
        await self.handle_error(error)

    @tasks.loop(minutes=5.0)
    async def unmute_users(self):
        configs = ['mutes', 'voice_mutes']
        for db_name in configs:
            config = self.bot.db[db_name]
            for guild_id in list(config):
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    del config[guild_id]
                    continue
                ctx = self.bot.ctx
                ctx.guild = guild

                unmuted_users = []
                guild_config = config[guild_id]
                try:
                    mod_channel = self.bot.get_channel(self.bot.db['mod_channel'][guild_id])
                except KeyError:
                    mod_channel = None
                if 'timed_mutes' in guild_config:
                    for member_id in list(guild_config['timed_mutes']):
                        unmute_time = datetime.strptime(
                            guild_config['timed_mutes'][member_id], "%Y/%m/%d %H:%M UTC").replace(tzinfo=timezone.utc)
                        if unmute_time < discord.utils.utcnow():
                            if db_name == 'mutes':
                                result = await ctx.invoke(self.bot.get_command('unmute'), member_id, int(guild_id))
                            else:
                                result = await ctx.invoke(self.bot.get_command('voiceunmute'), member_id, int(guild_id))
                            if result:
                                unmuted_users.append(member_id)
                if unmuted_users and mod_channel:
                    text_list = []
                    for i in unmuted_users:
                        user = self.bot.get_user(int(i))
                        if user:
                            text_list.append(f"{user.mention} ({user.name})")
                        if not user:
                            text_list.append(f"{i}")
                    if mod_channel.guild.id == 243838819743432704:  # spanish server
                        mod_channel = self.bot.get_channel(297877202538594304)  # incidents channel
                    await utils.safe_send(mod_channel,
                                       embed=discord.Embed(description=f"I've unmuted {', '.join(text_list)}, as "
                                                                       f"the time for their temporary mute has expired",
                                                           color=discord.Color(int('00ffaa', 16))))

    @unmute_users.error
    async def unmute_users_error(self, error):
        await self.handle_error(error)

    @tasks.loop(minutes=5.0)
    async def unselfmute_users(self):
        config = self.bot.db['selfmute']
        for guild_id in config:
            unmuted_users = []
            guild_config = config[guild_id]
            for user_id in list(guild_config):
                try:
                    unmute_time = guild_config[user_id]['time']
                    if isinstance(unmute_time, int):
                        unmute_time_obj = datetime.fromtimestamp(unmute_time, tz=timezone.utc)
                    else:
                        unmute_time_obj = datetime.strptime(guild_config[user_id]['time'],
                                                            "%Y/%m/%d %H:%M UTC").replace(tzinfo=timezone.utc)
                except TypeError as e:
                    print("TypeError in unselfmute for", guild_id, user_id, guild_config[user_id]['time'], e)
                    del guild_config[user_id]
                    continue
                if unmute_time_obj < discord.utils.utcnow():
                    del guild_config[user_id]
                    unmuted_users.append(user_id)
            if unmuted_users:
                for user_id in unmuted_users:
                    user = self.bot.get_user(int(user_id))
                    try:
                        await utils.safe_send(user, "Your selfmute has expired.")
                    except discord.Forbidden:
                        pass

    @unselfmute_users.error
    async def unselfmute_users_error(self, error):
        await self.handle_error(error)

    @tasks.loop(hours=24)
    async def delete_old_stats_days(self):
        for server_id in self.bot.stats:
            config = self.bot.stats[server_id]
            for day in list(config['messages']):
                days_ago = (discord.utils.utcnow() - datetime.strptime(day, "%Y%m%d").replace(tzinfo=timezone.utc)).days
                if days_ago > 30:
                    for user_id in config['messages'][day]:
                        for channel_id in config['messages'][day][user_id]:
                            try:
                                int(channel_id)  # skip 'emoji' and 'lang' entries
                            except ValueError:
                                continue
                            if 'member_totals' not in config:
                                config['member_totals'] = {}
                            if user_id in config['member_totals']:
                                config['member_totals'][user_id] += config['messages'][day][user_id][channel_id]
                            else:
                                config['member_totals'][user_id] = config['messages'][day][user_id][channel_id]
                    del config['messages'][day]
            for day in list(config['voice']['total_time']):
                days_ago = (discord.utils.utcnow() - datetime.strptime(day, "%Y%m%d").replace(tzinfo=timezone.utc)).days
                if days_ago > 30:
                    del config['voice']['total_time'][day]

    @delete_old_stats_days.error
    async def delete_old_stats_days_error(self, error):
        await self.handle_error(error)
        
    @tasks.loop(seconds=5)
    async def live_latency(self):
        t1 = time.perf_counter()
        try:
            await self.bot.application_info()
        except (discord.HTTPException, discord.DiscordServerError):
            pass
        t2 = time.perf_counter()
        self.bot.live_latency = t2 - t1

    @tasks.loop(minutes=5)
    async def fireside_message(self):
        fireside_channel_stage: discord.StageChannel = self.bot.get_channel(905992800250773564)
        fireside_channel_text: discord.TextChannel = self.bot.get_channel(905993064479342622)
        if not fireside_channel_stage or not fireside_channel_text:
            return
        oriana = fireside_channel_stage.guild.get_member(581324505331400733)
        if not oriana:
            return

        # check if fireside channel has active event
        try:
            stage_instance = await fireside_channel_stage.fetch_instance()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

        # check if oriana is in the channel
        if oriana not in fireside_channel_stage.members:
            return

        msg = ("Hey everyone! 🔥 Fireside is a space to share your anonymous confessions—let’s keep it wholesome and "
               "kind! 💛 No rudeness, and try to keep things appropriate so we can keep this going. You can find the "
               "confession link in the pinned messages 📌. Enjoy!\n\n"
               "¡Hola a todos! 🔥 Fireside es un espacio para compartir sus confesiones anónimas—mantengámoslo sin "
               "toxicidad y siendo amables! 💛 Nada de groserías y tratemos de que todo sea apropiado para que esto "
               "siga. El enlace para confesar está en los mensajes fijados 📌. ¡Disfruten!")

        await utils.safe_send(fireside_channel_text, msg)


async def setup(bot):
    await bot.add_cog(Background(bot))