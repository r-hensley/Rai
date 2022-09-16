import re
import sys
import aiohttp, async_timeout
from datetime import datetime, timezone
import traceback
import discord
from discord.ext import commands, tasks
from bs4 import BeautifulSoup
from .utils import helper_functions as hf

RYRY_SPAM_CHAN = 275879535977955330


class Background(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # self.risk_check
        self.bot.bg_tasks = [self.check_rawmangas, self.check_desync_voice, self.unban_users,
                             self.unmute_users, self.unselfmute_users, self.delete_old_stats_days, self.check_lovehug,
                             self.check_downed_tasks, self.save_db]
        for task in self.bot.bg_tasks:
            if not task.is_running():
                task.start()

    # def cog_unload(self):
    #     for task in self.bot.bg_tasks:
    #         task.cancel()

    async def handle_error(self, error):
        error = getattr(error, 'original', error)
        print('Error in background task:', file=sys.stderr)
        traceback.print_tb(error.__traceback__)
        print(f'{error.__class__.__name__}: {error}', file=sys.stderr)
        channel = self.bot.get_channel(554572239836545074)
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
            await hf.safe_send(ctx, s)
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
                await hf.safe_send(ch, f"{task.coro.__name__} ISN'T RUNNING!")

    @tasks.loop(minutes=10.0)
    async def save_db(self):
        if not self.bot.db:
            print("main database not yet fully loaded, so delaying database saving")
            return
        if not self.bot.stats:
            print("stats database not yet fully loaded, so delaying database saving")
            return

        await hf.dump_json()

    @tasks.loop(minutes=10.0)
    async def risk_check(self):
        config = self.bot.db['risk']
        url = f"https://www.conquerclub.com/game.php?game={config['id']}"
        try:
            with async_timeout.timeout(10):
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        r = resp
                        data = await resp.text()
        except (aiohttp.InvalidURL, aiohttp.ClientConnectorError):
            return f'invalid_url:  Your URL was invalid ({url})'
        if str(r.url) != url:  # the page went down so it redirected to the home page
            return f'invalid_url:  Your URL was invalid ({url})'
        if r.status != 200:
            try:
                return f'html_error: Error {r.status_code}: {r.reason} ({url})'
            except AttributeError:
                return f'html_error: {r.reason} ({url})'
        soup = BeautifulSoup(data, 'html.parser')
        # ben guthrie: 470244907848564738
        # players = [91687077510418432, 459846740313505794, 759136587677564990, 264462341003935756, 760555982618361876,
        #            760991500355239967, 202995638860906496, 266382095906111488, 122584263378993152, 551867033499992086]
        # players = [91687077510418432, 760555982618361876, 122584263378993152, 760991500355239967, 551867033499992086,
        #            521914355219169281, 202995638860906496, 264462341003935756, 459846740313505794, 759136587677564990]
        players = [91687077510418432, 264462341003935756, 759136587677564990, 122584263378993152, 459846740313505794,
                   760555982618361876, 470244907848564738]
        risk_ch = self.bot.get_channel(815485283721674752)

        log = soup.find('div', attrs={'id': "log"}).get_text()
        log = re.sub("2021-..-.. ..:..:.. - ", '\n', log).split('\n')
        if log[-1][-1] == ' ':
            log[-1] = log[-1][:-1]
        try:
            last_event = log.index(config['log'][-1])
        except ValueError:
            last_event = -1
        for event in log[last_event + 1:]:
            for emphasis in ["Gogatron", "Uoktem", "tronk", "drshrub", "snafuuu", "rahuligan", "Ryry013", "dumpyDirac",
                             "supagorilla", "tvbrown", 'davis.zackaria', 'AegonTargaryenVI']:
                event = event.replace(emphasis, f"**{emphasis}**")
            if "reinforced" in event:
                event = f"♻️ {event}"
            elif "troops" in event:
                event = f"👥 {event}"
            elif "assaulted" in event:
                event = f"⚔️ {event}"
            elif "ended the turn" in event:
                event = f"__⏩ {event}__\n⠀"  # invisible non-space character at end of this line
            if event:
                await hf.safe_send(risk_ch, event)
        config['log'] = log[-20:]

        for li in soup.find_all('li'):
            try:
                status = li['class'][0]
                if status == 'status_green':
                    player_index = int(li['id'].split('_')[-1]) - 1
                    player_id = players[player_index]

                    if config['current_player'] == player_index:
                        break
                    else:
                        current_player = config['current_player']
                        if player_index - current_player == 1 or (player_index == 0 and current_player == 6):
                            # the game has advanced by one player, note though that it skips by 2 per turn
                            config['current_player'] = player_index
                        elif player_index == current_player:
                            # the game has not advanced
                            break
                        else:
                            # this means people are playing at a rate of less than five mins per turn (maybe in voice
                            # together), so the bot should wait until a player has spent more than five minutes
                            # without making a move before notifying the user. If there's no change after five mins.,
                            # the above player_index - current_player == 1 condition will trigger.
                            config['current_player'] = player_index - 1
                            break

                    if config['sub'].get(str(player_id), False):
                        player_name = f"<@{player_id}>"
                    else:
                        player_name = risk_ch.guild.get_member(int(player_id)).display_name
                    await hf.safe_send(risk_ch, f"✅ It is {player_name}'s turn! <{url}>")
            except KeyError:
                pass

    @risk_check.error
    async def risk_check_error(self, error):
        await self.handle_error(error)

    @tasks.loop(hours=1.0)
    async def check_rawmangas(self):
        time = discord.utils.utcnow()
        config = self.bot.db['rawmangas']
        for manga in config:
            if time.weekday() != config[manga]['update']:
                continue
            if not 20 < time.hour < 21:
                continue
            for user_id in config[manga]['subscribers']:
                user = self.bot.get_user(user_id)
                await hf.safe_send(user, f"New manga chapter possibly: {manga}/{str(int(config[manga]['last'])+1)}")
            config[manga]['last'] += 1

    @check_rawmangas.error
    async def check_rawmangas_error(self, error):
        await self.handle_error(error)

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
                        except (discord.NotFound, discord.Forbidden):
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
                await hf.safe_send(mod_channel,
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
                    await hf.safe_send(mod_channel,
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
                    if type(unmute_time) == int:
                        unmute_time = datetime.fromtimestamp(unmute_time).replace(tzinfo=timezone.utc)
                    else:
                        unmute_time = datetime.strptime(guild_config[user_id]['time'],
                                                        "%Y/%m/%d %H:%M UTC").replace(tzinfo=timezone.utc)
                except TypeError as e:
                    print("there was a TypeError on _unselfmute", guild_id, user_id, guild_config[user_id]['time'], e)
                    del (guild_config[user_id])
                    continue
                if unmute_time < discord.utils.utcnow():
                    del (guild_config[user_id])
                    unmuted_users.append(user_id)
            if unmuted_users:
                for user_id in unmuted_users:
                    user = self.bot.get_user(int(user_id))
                    try:
                        await hf.safe_send(user, "Your selfmute has expired.")
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

    @tasks.loop(hours=1)
    async def check_lovehug(self):
        return
        # for url in self.bot.db['lovehug']:
        #     result = await self.lovehug_get_chapter(url)
        #     if type(result) == str:
        #         if 'invalid_url' in result:
        #             await hf.safe_send(self.bot.get_channel(TRACEBACKS_CHAN), f"lovehug error for {url}: {result}")
        #         continue
        #     if not result:
        #         return
        #     try:
        #         chapter = f"{url}{result['href']}"
        #     except TypeError:
        #         raise
        #     if chapter == self.bot.db['lovehug'][url]['last']:
        #         continue
        #     for user in self.bot.db['lovehug'][url]['subscribers']:
        #         u = self.bot.get_user(user)
        #         await hf.safe_send(u, f"New chapter: {url}{result['href']}")
        #     self.bot.db['lovehug'][url]['last'] = chapter

    @staticmethod
    async def lovehug_get_chapter(url):
        try:
            with async_timeout.timeout(10):
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        r = resp
                        data = await resp.text()
        except (aiohttp.InvalidURL, aiohttp.ClientConnectorError):
            return f'invalid_url:  Your URL was invalid ({url})'
        if str(r.url) != url:  # the page went down so it redirected to the home page
            return f'invalid_url:  Your URL was invalid ({url})'
        if r.status != 200:
            try:
                return f'html_error: Error {r.status_code}: {r.reason} ({url})'
            except AttributeError:
                return f'html_error: {r.reason} ({url})'
        soup = BeautifulSoup(data, 'html.parser')
        return soup.find('a', attrs={'title': re.compile("Chapter.*")})

    @check_lovehug.error
    async def check_lovehug_error(self, error):
        await self.handle_error(error)


async def setup(bot):
    await bot.add_cog(Background(bot))
