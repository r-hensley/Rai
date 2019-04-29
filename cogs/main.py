import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta, date
from .utils import helper_functions as hf
import langdetect
import hashlib

import os

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def blacklist_check():
    async def pred(ctx):
        if ctx.author in ctx.bot.get_guild(257984339025985546).members:
            if ctx.guild.id == 257984339025985546 or hf.admin_check(ctx):
                return True

    return commands.check(pred)


class Main(commands.Cog):
    """My custom cog that does stuff!"""

    def __init__(self, bot):
        self.bot = bot
        hf.setup(bot)

    @commands.command()
    async def new_help(self, ctx):
        x = self.bot.commands
        msg_dict = {}
        emb = discord.Embed(title='Help', description="Type `;help <command>` for more info on any command or category")
        for command in x:
            if await command.can_run(ctx) and not command.hidden:
                if command.cog_name in msg_dict:
                    msg_dict[command.cog_name].append(command)
                else:
                    msg_dict[command.cog_name] = [command]
        for cog in msg_dict:
            str = ''
            for command in msg_dict[cog]:
                if command.short_doc:
                    str += f"⠀⠀**{command.name}**\n{command.short_doc}\n"
                else:
                    str += f"⠀⠀**{command.name}**\n"
            emb.add_field(name=f"⁣\n__{command.cog_name}__",
                          value=str, inline=False)
        await ctx.send(embed=emb)

    @commands.command(hidden=True)
    async def _unban_users(self, ctx):
        config = self.bot.db['bans']
        to_delete = []
        for guild_id in config:
            guild_config = config[guild_id]
            if 'timed_bans' in guild_config:
                for member_id in guild_config['timed_bans']:
                    unban_time = datetime.strptime(guild_config['timed_bans'][member_id], "%Y/%m/%d %H:%M UTC")
                    if unban_time < datetime.utcnow():
                        guild = self.bot.get_guild(int(guild_id))
                        member = discord.Object(id=member_id)
                        try:
                            await guild.unban(member, reason="End of timed ban")
                            to_delete.append((guild_id, 'timed_bans', member_id))
                        except discord.NotFound:
                            pass
        if to_delete:
            for i in to_delete:
                del config[i[0]][i[1]][i[2]]
            await hf.dump_json()

    @commands.Cog.listener()
    async def on_message(self, msg):
        if msg.author.bot:
            return

        # "Experimental global watch list"
        # if msg.author.id == 202979770235879427:
        #     channel = self.bot.get_channel(374489744974807040)
        #     await channel.send(f"Message by {msg.author.name} in {msg.channel.mention}:\n\n```{msg.content}```")

        """Replace tatsumaki/nadeko serverinfo posts"""
        if msg.content in ['t!serverinfo', 't!server', 't!sinfo', '.serverinfo', '.sinfo']:
            if msg.guild.id in [189571157446492161, 243838819743432704, 275146036178059265]:
                new_ctx = await self.bot.get_context(msg)
                await new_ctx.invoke(self.serverinfo)

        """Message as the bot"""
        if isinstance(msg.channel, discord.DMChannel) \
                and msg.author.id == self.bot.owner_id and msg.content[0:3] == 'msg':
            await self.bot.get_channel(int(msg.content[4:22])).send(str(msg.content[22:]))

        if not isinstance(msg.channel, discord.TextChannel):
            print(msg.created_at, msg.author.name)
            return  # stops the rest of the code unless it's in a guild

        """chinese server banned words"""
        words = ['动态网自由门', '天安門', '天安门', '法輪功', '李洪志', 'Free Tibet', 'Tiananmen Square',
                 '反右派鬥爭', 'The Anti-Rightist Struggle', '大躍進政策', 'The Great Leap Forward', '文化大革命',
                 '人權', 'Human Rights', '民運', 'Democratization', '自由', 'Freedom', '獨立', 'Independence']
        if msg.guild.id in [266695661670367232, 494502230385491978, 320439136236601344, 275146036178059265]:
            word_count = 0
            for word in words:
                if word in msg.content:
                    word_count += 1
                if word_count == 5:
                    mod_channel = self.bot.get_channel(self.bot.db['mod_channel'][str(msg.guild.id)])
                    log_channel = self.bot.get_channel(self.bot.db['bans'][str(msg.guild.id)]['channel'])
                    if datetime.utcnow() - msg.author.joined_at < timedelta(minutes=60):
                        print('1')
                        try:
                            await msg.delete()
                        except discord.Forbidden:
                            print('2')
                            await mod_channel.send(f"Rai is lacking the permission to delete messages for the Chinese "
                                                   f"spam message.")

                        # await msg.author.send("That message doesn't do anything to Chinese computers.  It doesn't "
                        #                       "get their internet shut down or get them arrested or anything.  "
                        #                       "It's just annoying, so please stop trying it.")
                        try:
                            await msg.author.ban(reason=f"*by* Rai\n"
                                                        f"**Reason: **Automatic ban: Chinese banned words spam")
                        except discord.Forbidden:
                            await mod_channel.send(f"I tried to ban someone for the Chinese spam message, but I lack "
                                                   f"the permission to ban users.")

                        await log_channel.send(f"Banned {msg.author.name} for the banned words spam message."
                                               f"\nMessage was posted in {msg.channel.mention}.  Message:"
                                               f"\n```{msg.content}"[:1850] + '```')

                        break
                    else:

                        await mod_channel.send(f"Warning: {msg.author.name} may have said the banned words spam message"
                                               f"\nMessage was posted in {msg.channel.mention}.  Message:"
                                               f"\n```{msg.content}"[:1995] + '```')
                        break

        """best sex dating"""
        words = ['amazingsexdating', 'bestdatingforall']
        try:
            for word in words:
                if word in msg.content:
                    await self.bot.get_user(self.bot.owner_id).send(f"best spam sex in {msg.channel.mention}")
                    print(self.bot.db['auto_bans'][str(msg.author.guild.id)]['enable'])
                    print(datetime.utcnow(), '---', msg.author.joined_at, '-----',
                          datetime.utcnow() - msg.author.joined_at)
                    if self.bot.db['auto_bans'][str(msg.author.guild.id)]['enable'] and \
                            datetime.utcnow() - msg.author.joined_at < timedelta(minutes=10):
                        print('>>sex dating!!!!!!!!!!<<')
                        if msg.author.id in [202995638860906496, 414873201349361664]:
                            print(">>This code would've banned but I stopped it<<")
                            return
                        await msg.author.ban(reason=f'For posting a {word} link',
                                             delete_message_days=1)
                        self.bot.db['global_blacklist']['blacklist'].append(msg.author.id)
                        channel = self.bot.get_channel(533863928263082014)
                        await channel.send(
                            f"❌ Automatically added `{msg.author.name} ({msg.author.id}`) to the blacklist for "
                            f"posting a {word} spam link")
                        message = f"Banned a user for posting a {word} link." \
                                  f"\nID: {msg.author.id}" \
                                  f"\nServer: {msg.author.guild.name}" \
                                  f"\nName: {msg.author.name} {msg.author.mention}"
                        await self.bot.get_channel(329576845949534208).send(message)
                        await hf.dump_json()
        except KeyError as e:
            print('>>passed for key error on amazingsexdating: ' + e + '<<')
            pass
        except AttributeError as e:
            print('>>passed for attributeerror in amazingsexdating: ' + e + '<<')
            pass

        """mods ping on spanish server"""
        if msg.guild.id == 243838819743432704:
            if '<@&258806166770024449>' in msg.content:
                ch = self.bot.get_channel(563448201139716136)
                me = self.bot.get_user(202995638860906496)
                fourteen = self.bot.get_user(136444391777763328)
                em = discord.Embed(title=f"Mods Ping",
                                   description=f"From {msg.author.mention} ({msg.author.name}) "
                                               f"in {msg.channel.mention}",
                                   color=discord.Color(int('FFAA00', 16)),
                                   timestamp=datetime.utcnow())
                em.add_field(name="Content", value=f"{msg.content}\n⁣".replace('<@&258806166770024449>', ''))
                await ch.send(embed=em)
                await me.send(embed=em)
                await fourteen.send(embed=em)

        """Ping me if someone says my name"""
        cont = str(msg.content)
        if (
                (
                        'ryry' in cont.casefold()
                        or ('ryan' in cont.casefold() and msg.channel.guild != self.bot.spanServ)
                        or 'らいらい' in cont.casefold()
                        or 'ライライ' in cont.casefold()
                ) and
                (not msg.author.bot or msg.author.id == 202995638860906496)  # checks to see if account is a bot account
        ):  # random sad face
            if 'aryan' in cont.casefold():  # why do people say this so often...
                return
            else:
                await self.bot.spamChan.send(
                    f'**By {msg.author.name} in {msg.channel.mention}** ({msg.channel.name}): '
                    f'\n{msg.content}'
                    f'\n{msg.jump_url} <@202995638860906496>')

        """Self mute"""
        if msg.author.id == self.bot.owner_id and self.bot.selfMute:
            try:
                await msg.delete()
            except discord.errors.NotFound:
                pass

        if msg.guild:
            """super_watch"""
            try:
                if msg.author.id in self.bot.db['super_watch'][str(msg.guild.id)]['users']:
                    channel = self.bot.get_channel(self.bot.db['super_watch'][str(msg.guild.id)]['channel'])
                    await channel.send(
                        f"<#{msg.channel.id}> Message from super_watch user {msg.author.name}: "
                        f"\n{msg.content}")
            except KeyError:
                pass

            # """Message counting"""
            # try:
            #     if msg.guild.id in [243838819743432704, 189571157446492161]:
            #         try:
            #             self.bot.msg_count += 1
            #         except AttributeError:
            #             self.bot.msg_count = 1
            #         try:
            #             self.bot.messages[str(msg.guild.id)][msg.created_at.strftime("%Y%m%d")]. \
            #                 append([msg.author.id, msg.channel.id])
            #         except KeyError:
            #             self.bot.messages[str(msg.guild.id)][msg.created_at.strftime("%Y%m%d")] = \
            #                 [msg.author.id, msg.channel.id]
            #         if self.bot.msg_count % 100 == 0:
            #             self.dump_messages()
            # except AttributeError:
            #     pass

            """Ultra Hardcore"""
            await hf.uhc_check(msg)

            """Chinese server hardcore mode"""
            if msg.guild.id == 266695661670367232:
                if '*' not in msg.content and msg.channel.id not in self.bot.db['hardcore']["266695661670367232"][
                    'ignore']:
                    if len(msg.content) > 3:
                        try:
                            ROLE_ID = self.bot.db['hardcore'][str(msg.guild.id)]['role']
                            role = msg.guild.get_role(ROLE_ID)
                        except KeyError:
                            return
                        except AttributeError:
                            return
                        if role in msg.author.roles:
                            learning_eng = msg.guild.get_role(266778623631949826)
                            ratio = hf.jpenratio(msg)
                            if ratio is not None:
                                if learning_eng in msg.author.roles:
                                    if ratio < .55:
                                        try:
                                            await msg.delete()
                                        except discord.errors.NotFound:
                                            pass
                                        if len(msg.content) > 30:
                                            await hf.long_deleted_msg_notification(msg)
                                else:
                                    if ratio > .45:
                                        try:
                                            await msg.delete()
                                        except discord.errors.NotFound:
                                            pass
                                        if len(msg.content) > 60:
                                            await hf.long_deleted_msg_notification(msg)

            """Spanish server hardcore"""
            if msg.guild.id == 243838819743432704 and '*' not in msg.content and len(msg.content):
                if msg.content[0] != '=' and len(msg.content) > 3:
                    if msg.channel.id not in self.bot.db['hardcore']['243838819743432704']['ignore']:
                        role = msg.guild.get_role(526089127611990046)
                        if role in msg.author.roles:
                            learning_eng = msg.guild.get_role(247021017740869632)
                            learning_sp = msg.guild.get_role(297415063302832128)
                            if learning_eng in msg.author.roles:  # learning English, delete all Spanish
                                try:
                                    lang_res = langdetect.detect_langs(hf.rem_emoji_url(msg))[0]
                                    if lang_res.lang == 'es' and lang_res.prob > 0.97:
                                        try:
                                            await msg.delete()
                                        except discord.errors.NotFound:
                                            pass
                                        if len(msg.content) > 30:
                                            await hf.long_deleted_msg_notification(msg)
                                except langdetect.lang_detect_exception.LangDetectException:
                                    pass
                            elif learning_sp in msg.author.roles:  # learning Spanish, delete all English
                                try:
                                    lang_res = langdetect.detect_langs(hf.rem_emoji_url(msg))[0]
                                    if lang_res.lang == 'en' and lang_res.prob > 0.97:
                                        try:
                                            await msg.delete()
                                        except discord.errors.NotFound:
                                            pass
                                        if len(msg.content) > 30:
                                            await hf.long_deleted_msg_notification(msg)
                                except langdetect.lang_detect_exception.LangDetectException:
                                    pass
                            else:
                                try:
                                    await msg.author.send("You have hardcore enabled but you don't have the proper "
                                                          "learning role.  Please attach either 'Learning Spanish' or "
                                                          "'Learning English' to properly use hardcore mode, or take "
                                                          "off hardcore mode using the reactions in the server rules "
                                                          "page")
                                except discord.errors.Forbidden:
                                    pass

    @commands.command()
    async def kawaii(self, ctx):
        """Try it"""
        await ctx.send('https://i.imgur.com/hRBicd2.png')

    @commands.command(aliases=['git'])
    async def github(self, ctx):
        """Gives my github page"""
        await ctx.send('https://github.com/ryry013/Rai')

    @commands.command()
    async def punch(self, ctx, user: discord.Member = None):
        """A punch command I made as a test"""
        if not user:
            user = ctx.author
        await ctx.send("ONE PUNCH! And " + user.mention + " is out! ლ(ಠ益ಠლ)")

    @commands.command()
    async def ping(self, ctx, x=4):
        """sends back 'hello'"""
        await ctx.send(str(round(self.bot.latency, x)) + 's')
        await self.bot.testChan.send('hello')

    @commands.command()
    async def invite(self, ctx):
        """Gives an invite to bring this bot to your server"""
        await ctx.send(discord.utils.oauth_url(self.bot.user.id, permissions=discord.Permissions(permissions=3072)))

    @commands.group(invoke_without_command=True)
    async def report(self, ctx, user=None):
        """Make a report to the mods"""
        if isinstance(ctx.channel, discord.DMChannel):
            return
        guild_id = str(ctx.guild.id)
        if guild_id not in self.bot.db['report']:
            await ctx.send(f"This server has not run the setup for the report function yet.  Please type "
                           f"`;report setup`.")
            return
        config = self.bot.db['report'][guild_id]
        report_room = self.bot.get_channel(config['channel'])

        if user:
            user = await hf.member_converter(ctx, user)
            if not user:
                await ctx.send("I couldn't find that user.  Please try again, or type just `;report` if you want to"
                           " make your own report")
                return
        else:
            user = ctx.author

        report_text = [
            # [0]: when the user first enters the module
            f"Welcome to the reporting module.  You're about to make a report to the mods of the "
            f"{ctx.guild.name} server.  Please select one of the following options for your report.\n\n"
            f"1) Send a report to the mods.\n"
            f"2) Send an anonymous report to the mods.\n"
            f"3) Talk with the mods.\n"
            f"4) Cancel",

            # [1]: user chooses option 1: anonymous report
            "Please type your report in one message below.  Make sure to include any relevant information, such as "
            "who the report is about, which channel they did whatever you're reporting about was in, and any "
            "other users involved.",

            # [2]: finishes anonymous report
            "Thank you for your report.  The mods have been notified, and your name is anonymous.",

            # [3]: user chooses option 2: report room
            f".\n\n\n\n\n__Please go here__: {report_room.mention}\n"
            f"In ten seconds, I'll send a welcome message there.",

            # [4]: initial ping to mods in report room
            f"{user.name} - This user has entered the report room.  If they don't "
            f"come to this channel in the next ten seconds, they will not be able to "
            f"see the following message and might be confused as to what's happening. @here",

            # [5]: entry message in report room
            f"Welcome to the report room {user.mention}.  Only the mods can read your messages here, so you"
            f" can now make your report.  When you are finished, type `;report done` and a log of this conversation "
            f"will be sent to you.  Please ping one of the mods you see online or if no one responds to you.",

            # [6]: a mod requesting a user in the report room
            f"Your presence has been requested in {report_room.mention}.  There should be a "
            f"welcome message there explaining what is happening, but you might not see it so "
            f"it might be a blank channel.  "
            f"\n\n\n  Please go here within 10 seconds of this message: {report_room.mention}.  "
            f"\n\n\n  If you missed the 10 second window, that's ok.  The channel will be blank, but it's about "
            f"this: in this channel, only the mods can see your messages, and no other users will "
            f"ever be able to see what you have typed in the past if they too join the "
            f"channel.  At the end, a log of the chat will be sent to you.",

            # [7]: message to the mods that someone is on the waitlist
            f'The user {user.mention} has tried to access the report room, but was put on '
            f'the wait list because someone else is currently using it.',

            # [8]: initial ping to user
            f'Please come to this channel {user.mention}'
        ]

        if user != ctx.author and hf.admin_check(ctx):  # if the mods called in a user
            await self.report_room(ctx, config, user, report_text, True)
            return

        try:
            await ctx.message.delete()
        except discord.errors.Forbidden:
            await report_room.send(f"I tried to delete the invocation for a ;report in {ctx.channel.mention} but I "
                                   f"lacked the `Manage Messages` permission so I could not.  Please delete"
                                   f"the `;report` message that the user sent to maintain their privacy.")

        reaction = await self.report_options(ctx, report_text)  # presents users with options for what they want to do
        if not reaction:
            return

        if str(reaction.emoji) == "1⃣":  # Send a report
            await self.report_room(ctx, config, ctx.author, report_text)

        if str(reaction.emoji) == '2⃣':  # Send an anonymous report
            await self.anonymous_report(ctx, report_text)

        if str(reaction.emoji) == "3⃣":  # Talk to the mods
            await self.report_room(ctx, config, ctx.author, report_text)

        if str(reaction.emoji) == '4⃣':  # Cancel
            await ctx.author.send('Understood.  Have a nice day!')
            return

    @report.command(name='setup')
    @hf.is_admin()
    async def report_setup(self, ctx):
        """Sets the channel"""
        perms = ctx.channel.permissions_for(ctx.me)
        if not perms.read_messages or not perms.read_message_history or not perms.manage_roles:
            await ctx.message.add_reaction('\N{CROSS MARK}')
            try:
                await ctx.send("I need permissions for reading messages, reading message history, and "
                               "managing either channel permissions or server roles.  Please check these")
            except discord.errors.Forbidden:
                await ctx.author.send(f"Rai lacks the permission to send messages in {ctx.channel.mention}.")
            return

        guild_id = str(ctx.guild.id)
        if guild_id in self.bot.db['report']:
            self.bot.db['report'][guild_id]['channel'] = ctx.channel.id
            await hf.dump_json()
            await ctx.send(f"Successfully set the report room channel to {ctx.channel.mention}.")
        else:
            self.bot.db['report'][guild_id] = {'channel': ctx.channel.id,
                                               'current_user': None,
                                               'waiting_list': [],
                                               'entry_message': None}
            await hf.dump_json()
            await ctx.send(f"Initial setup for report room complete.  The report room channel has been set to "
                           f"{ctx.channel.mention}.")

    @report.command()
    async def done(self, ctx):
        """Use this when a report is finished in the report room"""
        try:
            config = self.bot.db['report'][str(ctx.guild.id)]
            report_room = ctx.bot.get_channel(config['channel'])
        except KeyError:
            return
        if not config['current_user']:
            return
        if ctx.channel != report_room:
            return

        user = ctx.guild.get_member(config['current_user'])
        start_message = await ctx.channel.fetch_message(config['entry_message'])
        config['current_user'] = None
        config['entry_message'] = None
        await hf.dump_json()
        await report_room.set_permissions(user, read_messages=False)

        message_log = 'Start of log:\n'
        async for message in ctx.channel.history(limit=None, after=start_message):
            next_line = f'**__{message.author}:__** {message.content} \n'
            if len(message_log + next_line) > 2000:
                await user.send(message_log)
                message_log = next_line
            else:
                message_log += next_line
        await user.send(message_log)

        await report_room.send('Session closed, and a log has been sent to the user')

        if config['waiting_list']:
            waiting_list = config['waiting_list']
            for member_id in waiting_list:
                if config['current_user']:
                    break
                member = ctx.guild.get_member(member_id)
                msg = 'The report room is now open.  Try sending `;report` to me again. If you ' \
                      'wish to be removed from the waiting list, please react with the below emoji.'
                waiting_msg = await member.send(msg)
                await waiting_msg.add_reaction('🚫')
                asyncio.sleep(10)

    @report.command()
    @hf.is_admin()
    async def check_waiting_list(self, ctx):
        """Checks who is on the waiting list for the report room"""
        guild_id = str(ctx.guild.id)
        if guild_id not in self.bot.db['report']:
            return
        config = self.bot.db['report'][guild_id]

        message = 'List of users on the waiting list: '
        if config['waiting_list']:
            members = [ctx.guild.get_member(user).mention for user in config['waiting_list']]
            message = message + ', '.join(members)
        else:
            message = 'There are no users on the waiting list'
        await ctx.send(message)

    @report.command()
    @hf.is_admin()
    async def clear_waiting_list(self, ctx):
        """Clears the waiting list for the report room"""
        guild_id = str(ctx.guild.id)
        if guild_id not in self.bot.db['report']:
            return
        config = self.bot.db['report'][guild_id]

        if config['waiting_list']:
            config['waiting_list'] = []
            hf.dump_json()
            await ctx.send('Waiting list cleared')
        else:
            await ctx.send('There was no one on the waiting list.')

    @report.command(name="reset")
    @hf.is_admin()
    async def report_reset(self, ctx):
        """Manually reset the report module in case of some bug"""
        try:
            config = self.bot.db['report'][str(ctx.guild.id)]
        except KeyError:
            return
        config['current_user'] = config['entry_message'] = None
        config['waiting_list'] = []
        hf.dump_json()
        await ctx.send(f"The report module has been reset on this server.  Check the permission overrides on the "
                       f"report channel to make sure there are no users left there.")

    @staticmethod
    async def report_options(ctx, report_text):
        """;report: Presents a user with the options of making an anonymous report or entering the report room"""

        def check(reaction, user):
            return user == ctx.author and (str(reaction.emoji) in "1⃣2⃣3⃣4⃣")  # 4⃣

        try:
            msg = await ctx.author.send(report_text[0])  # when the user first enters the module
        except discord.errors.Forbidden:
            await ctx.send(f"I'm unable to complete your request, as the user does not have PMs "
                           f"from server members enabled.")
            ctx.bot.db['report'][str(ctx.guild.id)]['current_user'] = None
            hf.dump_json()
            return

        await msg.add_reaction("1⃣")  # Send a report (report room)
        await msg.add_reaction('2⃣')  # Send an anonymous report
        await msg.add_reaction('3⃣')  # Talk to the mods (report room)
        await msg.add_reaction('4⃣')  # cancel

        try:
            reaction, user = await ctx.bot.wait_for('reaction_add', timeout=300.0, check=check)
            return reaction
        except asyncio.TimeoutError:
            await ctx.author.send("Module timed out.")
            return

    @staticmethod
    async def anonymous_report(ctx, report_text):
        """;report: The code for an anonymous report submission"""
        await ctx.author.send(report_text[1])  # Instructions for the anonymous report

        def check(m):
            return m.author == ctx.author and isinstance(m.channel, discord.channel.DMChannel)

        try:
            msg = await ctx.bot.wait_for('message', timeout=300.0, check=check)
            await ctx.author.send(report_text[2])  # "thank you for the report"
            mod_channel = ctx.bot.get_channel(ctx.bot.db['mod_channel'][str(ctx.guild.id)])
            await mod_channel.send('Received report from a user: \n\n')
            await mod_channel.send(msg.content)
            return
        except asyncio.TimeoutError:
            await ctx.author.send(f"Module timed out.")
            return

    @staticmethod
    async def report_room(ctx, config, user, report_text, from_mod=False):
        report_room = ctx.bot.get_channel(config['channel'])
        if config['current_user']:  # if someone is in the room already
            config['waiting_list'].append(user.id)
            msg = f"Sorry but someone else is using the room right now.  I'll message you when it's ope" \
                  f"n in the order that I received requests.  You are position " \
                  f"{config['waiting_list'].index(user.id)+1} on the list"
            await user.send(msg)  # someone is in the room, you've been added to waiting list
            try:
                mod_channel = ctx.guild.get_channel(ctx.cog.bot.db['mod_channel'][str(ctx.guild.id)])
                await mod_channel.send(f"{user.mention} ({user.name}) tried to enter the report room, but someone "
                                       f"else is already in it.  Try typing `;report done` in the report room, "
                                       f"and type `;report check_waiting_list` to see who is waiting.")
            except KeyError:
                await report_room.send(f"Note to the mods: I tried to send you a notification about the report room, "
                                       f"but you haven't set a mod channel yet.  Please type `;set_mod_channel` in "
                                       f"your mod channel.")
            await hf.dump_json()
            return
        if user.id in config['waiting_list']:
            config['waiting_list'].remove(user.id)
        config['current_user'] = user.id
        if report_room.permissions_for(user).read_messages:
            initial_msg = report_text[4][:-5] + "(Deleted `@here` ping because it seems like you're " \
                                                "just testing the room)"
        else:
            initial_msg = report_text[4]
        await report_room.set_permissions(user, read_messages=True)

        if from_mod:
            try:
                await user.send(report_text[6])
            except discord.errors.Forbidden:
                await ctx.send(f"I'm unable to complete your request, as the user does not have PMs "
                               f"from server members enabled.")
                ctx.bot.db['report'][str(ctx.guild.id)]['current_user'] = None
                hf.dump_json()
                return
        else:
            await user.send(report_text[3])  # please go to the report room

        msg = await report_room.send(initial_msg)  # initial msg to mods
        await report_room.send(report_text[8])
        config['entry_message'] = msg.id
        await hf.dump_json()
        await asyncio.sleep(10)
        await report_room.send(report_text[5])  # full instructions text in report room

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user: discord.Member):
        """removes people from the waiting list for ;report if they react with '🚫' to a certain message"""
        if reaction.emoji == '🚫':
            if reaction.message.channel == user.dm_channel:
                config = self.bot.db['report']
                for guild_id in config:
                    if user.id in config[guild_id]['waiting_list']:
                        config[guild_id]['waiting_list'].remove(user.id)
                        await user.send("Understood.  You've been removed from the waiting list.  Have a nice day.")

                        mod_channel = self.bot.get_channel(self.bot.db["mod_channel"][guild_id])
                        msg_to_mod_channel = f"The user {user.name} was previously on the wait list for the " \
                                             f"report room but just removed themselves."
                        await mod_channel.send(msg_to_mod_channel)
                        await hf.dump_json()
                        return
                await user.send("You aren't on the waiting list.")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.emoji.name == '✅':  # captcha
            if str(payload.guild_id) in self.bot.db['captcha']:
                config = self.bot.db['captcha'][str(payload.guild_id)]
                if config['enable']:
                    guild = self.bot.get_guild(payload.guild_id)
                    role = guild.get_role(config['role'])
                    if payload.message_id == config['message']:
                        try:
                            await guild.get_member(payload.user_id).add_roles(role)
                            return
                        except discord.errors.Forbidden:
                            await self.bot.get_user(202995638860906496).send(
                                'on_raw_reaction_add: Lacking `Manage Roles` permission'
                                f' <#{payload.guild_id}>')

        if payload.guild_id == 266695661670367232:  # chinese
            if payload.emoji.name in '🔥📝🖋🗣🎙':
                roles = {'🔥': 496659040177487872,
                         '📝': 509446402016018454,
                         '🗣': 266713757030285313,
                         '🖋': 344126772138475540,
                         '🎙': 454893059080060930}
                server = 0
            else:
                return
        elif payload.guild_id == 243838819743432704:  # spanish/english
            if payload.emoji.name in '🎨🐱🐶🎮table👪🎥🎵❗👚💻📔✏🔥📆':
                roles = {'🎨': 401930364316024852,
                         '🐱': 254791516659122176,
                         '🐶': 349800774886359040,
                         '🎮': 343617472743604235,
                         '👪': 402148856629821460,
                         '🎥': 354480160986103808,
                         '🎵': 263643288731385856,
                         '👚': 376200559063072769,
                         '💻': 401930404908630038,
                         '❗': 243859335892041728,
                         '📔': 286000427512758272,
                         '✏': 382752872095285248,
                         '🔥': 526089127611990046,
                         'table': 396080550802096128,
                         '📆': 555478189363822600}
                server = 1
            else:
                return
        else:
            return

        guild = self.bot.get_guild(payload.guild_id)
        user = guild.get_member(payload.user_id)
        if not user.bot:
            try:
                config = self.bot.db['roles'][str(payload.guild_id)]
            except KeyError:
                return
            if server == 0:
                if payload.message_id != config['message']:
                    return
            elif server == 1:
                if payload.message_id != config['message1'] and payload.message_id != config['message2']:
                    return
            role = guild.get_role(roles[payload.emoji.name])
            try:
                await user.add_roles(role)
            except discord.errors.Forbidden:
                self.bot.get_user(202995638860906496).send(
                    'on_raw_reaction_add: Lacking `Manage Roles` permission'
                    f'<#{payload.guild_id}>')

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if not payload.guild_id:
            return
        if payload.guild_id == 266695661670367232:  # chinese
            if payload.emoji.name in '🔥📝🖋🗣🎙':
                roles = {'🔥': 496659040177487872,
                         '📝': 509446402016018454,
                         '🗣': 266713757030285313,
                         '🖋': 344126772138475540,
                         '🎙': 454893059080060930}
                server = 0
            else:
                return
        elif payload.guild_id == 243838819743432704:  # spanish/english
            if payload.emoji.name in '🎨🐱🐶🎮table👪🎥🎵❗👚💻📔✏🔥📆':
                roles = {'🎨': 401930364316024852,
                         '🐱': 254791516659122176,
                         '🐶': 349800774886359040,
                         '🎮': 343617472743604235,
                         '👪': 402148856629821460,
                         '🎥': 354480160986103808,
                         '🎵': 263643288731385856,
                         '👚': 376200559063072769,
                         '💻': 401930404908630038,
                         '❗': 243859335892041728,
                         '📔': 286000427512758272,
                         '✏': 382752872095285248,
                         '🔥': 526089127611990046,
                         'table': 396080550802096128,
                         '📆': 555478189363822600}
                server = 1
            else:
                return
        else:
            return
        guild = self.bot.get_guild(payload.guild_id)
        user = guild.get_member(payload.user_id)
        if not user.bot:
            try:
                config = self.bot.db['roles'][str(payload.guild_id)]
            except KeyError:
                return
            if server == 0:
                if payload.message_id != config['message']:
                    return
            elif server == 1:
                if payload.message_id != config['message1'] and payload.message_id != config['message2']:
                    return
            role = guild.get_role(roles[payload.emoji.name])
            try:
                await user.remove_roles(role)
            except discord.errors.Forbidden:
                self.bot.get_user(202995638860906496).send(
                    'on_raw_reaction_remove: Lacking `Manage Roles` permission'
                    f'<#{payload.guild_id}>')

    @commands.command()
    async def pencil(self, ctx):
        if ctx.author.nick:
            try:
                await ctx.author.edit(nick=ctx.author.nick + '📝')
                await ctx.send("I've added 📝 to your name.  This means you wish to be corrected in your sentences")
            except discord.errors.Forbidden:
                await ctx.send("I lack the permissions to change your nickname")
            except discord.errors.HTTPException:
                await ctx.message.add_reaction('💢')
        else:
            try:
                await ctx.author.edit(nick=ctx.author.name + '📝')
                await ctx.send("I've added 📝 to your name.  This means you wish to be corrected in your sentences")
            except discord.errors.Forbidden:
                await ctx.send("I lack the permissions to change your nickname")

    @commands.command()
    async def eraser(self, ctx):
        if ctx.author.nick:
            try:
                await ctx.author.edit(nick=ctx.author.nick[:-1])
                await ctx.message.add_reaction('◀')
            except discord.errors.Forbidden:
                await ctx.send("I lack the permissions to change your nickname")
        else:
            await ctx.author.edit(nick=ctx.author.name[:-1])
            await ctx.message.add_reaction('◀')

    @commands.command(aliases=['ryry'])
    async def ryan(self, ctx):
        """Posts a link to the help docs server for my bot"""
        await ctx.send("You can find some shitty docs for how to use my bot here: "
                       "https://github.com/ryry013/Rai/blob/master/README.md \n"
                       "You can ask questions and find some further details here: https://discord.gg/7k5MMpr")

    @commands.command(aliases=[';p', ';s', ';play', ';skip', '_;', '-;', ')', '__;', '___;', ';leave', ';join',
                               ';l', ';q', ';queue', ';pause', ';volume', ';1', ';vol', ';np', ';list'], hidden=True)
    async def ignore_commands_list(self, ctx):
        pass

    @commands.command(aliases=['cl', 'checklanguage'])
    async def check_language(self, ctx, *, msg: str = None):
        """Shows what's happening behind the scenes for hardcore mode.  Will try to detec the language that your
        message was typed in, and display the results.  Note that this is non-deterministic code, which means
        repeated results of the same exact message might give different results every time."""
        stripped_msg = hf.rem_emoji_url(msg)
        try:
            lang_result = langdetect.detect_langs(stripped_msg)
        except langdetect.lang_detect_exception.LangDetectException:
            lang_result = "There was an error detecting the languages"
        str = f"Your message:```{msg}```" \
              f"The message I see (no custom emojis or urls): ```{stripped_msg}```" \
              f"The language I detect: ```{lang_result}```" \
              f"If the first language is above 0.97 of your native language, your message would be deleted"

        await ctx.send(str)

    def get_color_from_name(self, ctx):
        config = self.bot.db['questions'][str(ctx.channel.guild.id)]
        channel_list = sorted([int(channel) for channel in config])
        index = channel_list.index(ctx.channel.id) % 6
        # colors = ['00ff00', 'ff9900', '4db8ff', 'ff0000', 'ff00ff', 'ffff00'] below line is in hex
        colors = [65280, 16750848, 5093631, 16711680, 16711935, 16776960]
        return colors[index]

    async def add_question(self, ctx, target_message, title=None):
        try:
            config = self.bot.db['questions'][str(ctx.guild.id)][str(ctx.channel.id)]
        except KeyError:
            await ctx.send(f"This channel is not setup as a questions channel.  Run `;question setup` in the "
                           f"questions channel to start setup.")
            return
        if not title:
            title = target_message.content[:900]
        # for channel in self.bot.db['questions'][str(ctx.guild.id)]:
        # for question in self.bot.db['questions'][str(ctx.guild.id)][channel]:
        # question = self.bot.db['questions'][str(ctx.guild.id)][channel][question]
        # if (datetime.today() - datetime.strptime(question['date'], "%Y/%m/%d")).days >= 3:
        # log_channel = self.bot.get_channel(self.bot.db['questions']['channel']['log_channel'])
        # await log_channel.send(f"Closed question for being older than three days and unanswered")

        question_number = 1
        while str(question_number) in config['questions']:
            question_number += 1
        if question_number > 9:
            await ctx.send(f"Note, I've reached the maximum amount of open questions for reactions.  Try "
                           f"running `;q list` and clearing out some old questions.")
        config['questions'][str(question_number)] = {}
        config['questions'][str(question_number)]['title'] = title
        config['questions'][str(question_number)]['question_message'] = target_message.id
        config['questions'][str(question_number)]['author'] = target_message.author.id
        config['questions'][str(question_number)]['command_caller'] = ctx.author.id
        config['questions'][str(question_number)]['date'] = date.today().strftime("%Y/%m/%d")

        log_channel = self.bot.get_channel(config['log_channel'])
        color = self.get_color_from_name(ctx)  # returns a RGB tuple unique to every username
        splice_len = 1024 - len(target_message.jump_url)
        emb = discord.Embed(title=f"Question number: `{question_number}`",
                            description=f"Asked by {target_message.author.mention} ({target_message.author.name}) "
                                        f"in {target_message.channel.mention}",
                            color=discord.Color(color),
                            timestamp=datetime.utcnow())
        if len(title) > splice_len:
            emb.add_field(name=f"Question:", value=f"{title[:splice_len]}...\n{target_message.jump_url}")
        else:
            emb.add_field(name=f"Question:", value=f"{title}\n{target_message.jump_url}")
        if ctx.author != target_message.author:
            emb.set_footer(text=f"Question added by {ctx.author.name}")
        try:
            log_message = await log_channel.send(embed=emb)
        except discord.errors.HTTPException:
            await ctx.send("The question was too long")
            del (config['questions'][str(question_number)])
            return
        config['questions'][str(question_number)]['log_message'] = log_message.id
        number_map = {'1': '1\u20e3', '2': '2\u20e3', '3': '3\u20e3', '4': '4\u20e3', '5': '5\u20e3',
                      '6': '6\u20e3', '7': '7\u20e3', '8': '8\u20e3', '9': '9\u20e3'}
        if question_number < 10:
            try:
                await target_message.add_reaction(number_map[str(question_number)])
            except discord.errors.Forbidden:
                await ctx.send(f"I lack the ability to add reactions, please give me this permission")
        await hf.dump_json()

    @commands.group(invoke_without_command=True, aliases=['q'])
    async def question(self, ctx, *, args):
        """A module for asking questions, put the title of your quesiton like `;question <title>`"""
        args = args.split(' ')
        if not args:
            msg = f"This is a module to help you ask your questions.  To ask a question, decide a title for your " \
                  f"question and type `;question <title>`.  For example, if your question is about the meaning " \
                  f"of a word in a sentence, you could format the command like `;question Meaning of <word> " \
                  f"in <sentence>`. Put that command in the questions channel and you're good to go!  " \
                  f"(Alias: `;q <title>`)"
            await ctx.send(msg)
            return

        try:  # there is definitely some text in the arguments
            target_message = await ctx.channel.fetch_message(int(args[0]))  # this will work if the first arg is an ID
            if len(args) == 1:
                title = target_message.content  # if there was no text after the ID
            else:
                title = ' '.join(args[1:])  # if there was some text after the ID
        except (discord.errors.NotFound, ValueError):  # no ID cited in the args
            target_message = ctx.message  # use the current message as the question link
            title = ' '.join(args)  # turn all of args into the title

        await self.add_question(ctx, target_message, title)

    @question.command(name='setup')
    @hf.is_admin()
    async def question_setup(self, ctx):
        """Use this command in your questions channel"""
        config = self.bot.db['questions'].setdefault(str(ctx.guild.id), {})
        if str(ctx.channel.id) in config:
            msg = await ctx.send("This will reset the questions database for this channel.  "
                                 "Do you wish to continue?  Type `y` to continue.")
            try:
                await self.bot.wait_for('message', timeout=15.0, check=lambda m: m.content == 'y' and
                                                                                 m.author == ctx.author)
            except asyncio.TimeoutError:
                await msg.edit(content="Canceled...", delete_after=10.0)
                return
        msg_1 = await ctx.send(f"Questions channel set as {ctx.channel.mention}.  In the way I just linked this "
                               f"channel, please give me a link to the log channel you wish to use for this channel.")
        try:
            msg_2 = await self.bot.wait_for('message', timeout=20.0, check=lambda m: m.author == ctx.author)
        except asyncio.TimeoutError:
            await msg_1.edit(content="Canceled...", delete_after=10.0)
            return

        try:
            log_channel_id = int(msg_2.content.split('<#')[1][:-1])
            log_channel = self.bot.get_channel(log_channel_id)
            if not log_channel:
                raise NameError
        except (IndexError, NameError):
            await ctx.send(f"Invalid channel specified.  Please start over and specify a link to a channel "
                           f"(should highlight blue)")
            return
        config[str(ctx.channel.id)] = {'questions': {},
                                       'log_channel': log_channel_id}
        await ctx.send(f"Set the log channel as {log_channel.mention}.  Setup complete.  Try starting your first "
                       f"question with `;question <title>` in this channel.")
        await hf.dump_json()

    @question.command(aliases=['a'])
    async def answer(self, ctx, *, args=''):
        """Marks a question as answered, format: `;q a <question_id 0-9> [answer_id]`
        and has an optional answer_id field for if you wish to specify an answer message"""
        try:
            config = self.bot.db['questions'][str(ctx.guild.id)][str(ctx.channel.id)]
        except KeyError:
            await ctx.send(f"This channel is not setup as a questions channel.  Please make sure you mark your "
                           f"question as 'answered' in the channel you asked it in.")
            return
        questions = config['questions']
        args = args.split(' ')

        async def self_answer_shortcut():
            for question_number in questions:
                if ctx.author.id == questions[question_number]['author']:
                    return int(question_number)
            await ctx.send(f"Only the asker of the question can omit stating the question ID.  You "
                           f"must specify which question  you're trying to answer: `;q a <question id>`.  "
                           f"For example, `;q a 3`.")
            return

        answer_message = answer_text = answer_id = None
        if args == ['']:  # if a user just inputs ;q a
            number = await self_answer_shortcut()
            answer_message = ctx.message
            answer_text = ''
            if not number:
                await ctx.send(f"Please enter the number of the question you wish to answer, like `;q a 3`.")
                return

        elif len(args) == 1:  # 1) ;q a <question ID>     2) ;q a <word>      3) ;q a <message ID>
            try:  # arg is a number
                single_arg = int(args[0])
            except ValueError:  # arg is a single text word
                number = await self_answer_shortcut()
                answer_message = ctx.message
                answer_text = args[0]
            else:
                if len(str(single_arg)) <= 2:  # ;q a <question ID>
                    number = args[0]
                    answer_message = ctx.message
                    answer_text = ctx.message.content
                elif 17 <= len(str(single_arg)) <= 21:  # ;q a <message ID>
                    try:
                        answer_message = await ctx.channel.fetch_message(single_arg)
                    except discord.errors.NotFound:
                        await ctx.send(f"I thought `{single_arg}` was a message ID but I couldn't find that "
                                       f"message in this channel.")
                        return
                    answer_text = answer_message.content[:900]
                    number = await self_answer_shortcut()
                else:  # ;q a <single word>
                    number = await self_answer_shortcut()
                    answer_message = ctx.message
                    answer_text = str(single_arg)

        else:  # args is more than one word
            number = args[0]
            try:  # example: ;q a 1 554490627279159341
                if 17 < len(args[1]) < 21:
                    answer_message = await ctx.channel.fetch_message(int(args[1]))
                    answer_text = answer_message.content[:900]
                else:
                    raise TypeError
            except (ValueError, TypeError):  # Supplies text answer:   ;q a 1 blah blah answer goes here
                answer_message = ctx.message
                answer_text = ' '.join(args[1:])
            except discord.errors.NotFound:
                await ctx.send(f"A corresponding message to the specified ID was not found.  `;q a <question_id> "
                               f"<message id>`")
                return

        try:
            number = str(number)
            question = questions[number]
        except KeyError:
            await ctx.send(f"Invalid question number.  Check the log channel again and input a single number like "
                           f"`;question answer 3`.  Also, make sure you're answering in the right channel.")
            return
        except Exception:
            await ctx.send(f"You've done *something* wrong... (´・ω・`)")
            raise

        try:
            log_channel = self.bot.get_channel(config['log_channel'])
            log_message = await log_channel.fetch_message(question['log_message'])
        except discord.errors.NotFound:
            log_message = None
            await ctx.send(f"Message in log channel not found.  Continuing code.")

        try:
            question_message = await ctx.channel.fetch_message(question['question_message'])
            if ctx.author.id not in [question_message.author.id, question['command_caller']] \
                    and not hf.admin_check(ctx):
                await ctx.send(f"Only mods or the person who asked/started the question "
                               f"originally can mark it as answered.")
                return
        except discord.errors.NotFound:
            if log_message:
                await log_message.delete()
            del questions[number]
            msg = await ctx.send(f"Original question message not found.  Closing question")
            await asyncio.sleep(5)
            await msg.delete()
            await ctx.message.delete()
            await hf.dump_json()
            return

        if log_message:
            emb = log_message.embeds[0]
            if answer_message.author != question_message.author:
                emb.description += f"\nAnswered by {answer_message.author.mention} ({answer_message.author.name})"
            emb.title = "ANSWERED"
            emb.color = discord.Color.default()
            if not answer_text:
                answer_text = ''
            emb.add_field(name=f"Answer: ",
                          value=answer_text + '\n' + answer_message.jump_url)
            await log_message.edit(embed=emb)

        try:
            question_message = await ctx.channel.fetch_message(question['question_message'])
            for reaction in question_message.reactions:
                if reaction.me:
                    try:
                        await question_message.remove_reaction(reaction.emoji, self.bot.user)
                    except discord.errors.Forbidden:
                        await ctx.send(f"I lack the ability to add reactions, please give me this permission")
        except discord.errors.NotFound:
            msg = await ctx.send("That question was deleted")
            await log_message.delete()
            await asyncio.sleep(5)
            await msg.delete()
            await ctx.message.delete()

        del (config['questions'][number])
        await hf.dump_json()
        if ctx.message:
            try:
                await ctx.message.add_reaction('\u2705')
            except discord.errors.Forbidden:
                await ctx.send(f"I lack the ability to add reactions, please give me this permission")

    @question.command(aliases=['reopen', 'bump'])
    @hf.is_admin()
    async def open(self, ctx, message_id):
        """Reopens a closed question, point message_id to the log message in the log channel"""
        config = self.bot.db['questions'][str(ctx.guild.id)][str(ctx.channel.id)]
        for question in config['questions']:
            if int(message_id) == config['questions'][question]['log_message']:
                question = config['questions'][question]
                break
        log_channel = self.bot.get_channel(config['log_channel'])
        try:
            log_message = await log_channel.fetch_message(int(message_id))
        except discord.errors.NotFound:
            await ctx.send(f"Specified log message not found")
            return
        emb = log_message.embeds[0]
        if emb.title == 'ANSWERED':
            emb.description = emb.description.split('\n')[0]
            try:
                question_message = await ctx.channel.fetch_message(int(emb.fields[0].value.split('/')[-1]))
            except discord.errors.NotFound:
                await ctx.send(f"The message for the original question was not found")
                return
            await self.add_question(ctx, question_message, question_message.content)
        else:
            new_log_message = await log_channel.send(embed=emb)
            question['log_message'] = new_log_message.id
        await log_message.delete()
        await hf.dump_json()

    @question.command()
    async def list(self, ctx):
        """Shows a list of currently open questions"""
        try:
            config = self.bot.db['questions'][str(ctx.guild.id)]
        except KeyError:
            await ctx.send(f"There are no questions channels on this server.  Run `;question setup` in the "
                           f"questions channel to start setup.")
            return
        emb = discord.Embed(title=f"List of open questions:")
        for channel in config:
            channel_config = config[str(channel)]['questions']
            for question in channel_config:
                try:
                    question_channel = self.bot.get_channel(int(channel))
                    question_message = await question_channel.fetch_message(channel_config[question]['question_message'])
                    question_text = ' '.join(question_message.content.split(' '))
                    text_splice = 1024 - len(question_message.jump_url) - \
                                  len(f"By {question_message.author.mention}\n\n")
                    value_text = f"By {question_message.author.mention} in {question_message.channel.mention}\n" \
                                 f"{question_text[:text_splice]}\n" \
                                 f"{question_message.jump_url}"
                    emb.add_field(name=f"Question `{question}`",
                                  value=value_text)
                except discord.errors.NotFound:
                    emb.add_field(name=f"Question `{question}`",
                                  value="original message not found")
        await ctx.send(embed=emb)

    @question.command(aliases=['edit'])
    @hf.is_admin()
    async def change(self, ctx, log_id, target, *text):
        """Edit either the asker, answerer, question, title, or answer of a question log in the log channel"""
        config = self.bot.db['questions'][str(ctx.guild.id)][str(ctx.channel.id)]
        log_channel = self.bot.get_channel(config['log_channel'])
        target_message = await log_channel.fetch_message(int(log_id))
        if target not in ['asker', 'answerer', 'question', 'title', 'answer']:
            await ctx.send(f"Invalid field specified in the log message.  Please choose a target to edit out of "
                           f"`asker`, `answerer`, `question`, `title`, `answer`")
            return
        emb = target_message.embeds[0]

        if target == 'question':
            try:
                question_id = int(text[0])  # ;q edit 555932038612385798 question 555943517994614784
                question_message = await ctx.channel.fetch_message(question_id)
                emb.set_field_at(0, name=emb.fields[0].name, value=f"{question_message.content[:900]}\n"
                                                                   f"{question_message.jump_url})")
            except ValueError:
                question_message = ctx.message  # ;q edit 555932038612385798 question <New question text>
                question_text = ' '.join(question_message.content.split(' ')[3:])
                emb.set_field_at(0, name=emb.fields[0].name, value=f"{question_text}\n{question_message.jump_url}")
        if target == 'title':
            title = ' '.join(text)
            jump_url = emb.fields[0].split('\n')[-1]
            emb.set_field_at(0, name=emb.fields[0].name, value=f"{title}\n{jump_url}")
        if target == 'asker':
            try:
                asker = ctx.guild.get_member(int(text[0]))
            except ValueError:
                await ctx.send(f"To edit the asker, give the user ID of the user.  For example: "
                               f"`;q edit <log_message_id> asker <user_id>`")
                return
            new_description = emb.description.split(' ')
            new_description[2] = f"{asker.mention} ({asker.name})"
            del new_description[3]
            emb.description = ' '.join(new_description)

        if emb.title == 'ANSWERED':
            if target == 'answerer':
                answerer = ctx.guild.get_member(int(text[0]))
                new_description = emb.description.split('Answered by ')[1] = answerer.mention
                emb.description = 'Answered by '.join(new_description)
            elif target == 'answer':
                try:  # ;q edit <log_message_id> answer <answer_id>
                    answer_message = await ctx.channel.fetch_message(int(text[0]))
                    emb.set_field_at(1, name=emb.fields[1].name, value=answer_message.jump_url)
                except ValueError:
                    answer_message = ctx.message  # ;q edit <log_message_id> answer <new text>
                    answer_text = 'answer '.join(ctx.message.split('answer ')[1:])
                    emb.set_field_at(1, name=emb.fields[1].name, value=f"{answer_text[:900]}\n"
                                                                       f"{answer_message.jump_url}")

        if emb.footer.text:
            emb.set_footer(text=emb.footer.text + f", Edited by {ctx.author.name}")
        else:
            emb.set_footer(text=f"Edited by {ctx.author.name}")
        await target_message.edit(embed=emb)
        try:
            await ctx.message.add_reaction('\u2705')
        except discord.errors.Forbidden:
            await ctx.send(f"I lack the ability to add reactions, please give me this permission")

    @commands.command()
    async def jisho(self, ctx, *, text):
        """Provides a link to a Jisho search"""
        await ctx.message.delete()
        await ctx.send(f"Try finding the meaning to the word you're looking for here: https://jisho.org/search/{text}")

    @commands.command(aliases=['server', 'info', 'sinfo'])
    @commands.cooldown(1, 30, type=commands.BucketType.channel)
    async def serverinfo(self, ctx):
        """Shows info about this server"""
        guild = ctx.guild
        if not guild:
            await ctx.send(f"{ctx.channel}.  Is that what you were looking for?  (Why are you trying to call info "
                           f"on 'this server' in a DM?)")
            return
        em = discord.Embed(title=f"**{guild.name}**",
                           description=f"**ID:** {guild.id}",
                           timestamp=guild.created_at,
                           colour=discord.Colour(0x877AD6))
        em.set_thumbnail(url=guild.icon_url)
        em.add_field(name="Region", value=guild.region)
        em.add_field(name="Channels", value=f"{len(guild.text_channels)} text / {len(guild.voice_channels)} voice")
        em.add_field(name="Verification Level", value=guild.verification_level)
        em.add_field(name="Guild created on (UTC)", value=guild.created_at.strftime("%Y/%m/%d %H:%M:%S"))

        if guild.afk_channel:
            em.add_field(name="Voice AFK Timeout",
                         value=f"{guild.afk_timeout//60} mins → {guild.afk_channel.mention}")

        if guild.explicit_content_filter != "disabled":
            em.add_field(name="Explicit Content Filter", value=guild.explicit_content_filter)

        if guild.id not in [189571157446492161, 243838819743432704]:
            em.add_field(name="Server owner", value=f"{guild.owner.name}#{guild.owner.discriminator}")

        list_of_members = guild.members
        if len(list_of_members) < 20000:
            role_count = {}
            for member in list_of_members:
                for role in member.roles:
                    if role.name in role_count:
                        role_count[role.name] += 1
                    else:
                        role_count[role.name] = 1
            sorted_list = sorted(list(role_count.items()), key=lambda x: x[1], reverse=True)
            top_five_roles = ''
            counter = 0
            for role in sorted_list[1:7]:
                counter += 1
                top_five_roles += f"{role[0]}: {role[1]}\n"
                #if counter == 3:
                #    top_five_roles += '\n'
            top_five_roles = top_five_roles[:-1]
            em.add_field(name=f"Top 6 roles (out of {len(guild.roles)})", value=top_five_roles)
        else:
            em.add_field(name="Roles", value=str(len(guild.roles)))

        how_long_ago = datetime.utcnow() - guild.created_at
        days = how_long_ago.days
        years = days // 365
        bef_str = ''
        if years:
            bef_str = f"{years} years, "
        months = (days - 365*years) // 30.416666666666668
        if months:
            bef_str += f"{int(months)} months, "
        days = days - 365*years - round(30.416666666666668*months)
        bef_str += f"{days} days"
        em.set_footer(text=f"Guild created {bef_str} ago on:")
        if len(em.fields)%2 == 0:
            two = em.fields[-2]
            em.add_field(name=two.name, value=two.value)
            em.remove_field(-3)
        await ctx.send(embed=em)

    @commands.group(invoke_without_command=True, aliases=['gb', 'gbl', 'blacklist'], hidden=True)
    @blacklist_check()
    async def global_blacklist(self, ctx):
        """A global blacklist for banning spammers, requires three votes from mods from three different servers"""
        config = hf.database_toggle(ctx, self.bot.db['global_blacklist'])
        if config['enable']:
            if not ctx.me.guild_permissions.ban_members:
                await ctx.send('I lack the permission to ban members.  Please fix that before enabling this module')
                hf.database_toggle(ctx, self.bot.db['global_blacklist'])
                return
            await ctx.send("Enabled the global blacklist on this server.  Anyone voted into the blacklist by three "
                           "mods and joining your server will be automatically banned.  "
                           "Type `;global_blacklist residency` to claim your residency on a server.")
        else:
            await ctx.send("Disabled the global blacklist.  Anyone on the blacklist will be able to join  your server.")
        await hf.dump_json()

    @global_blacklist.command()
    @blacklist_check()
    async def residency(self, ctx):
        """Claims your residency on a server"""
        config = self.bot.db['global_blacklist']['residency']

        if str(ctx.author.id) in config:
            server = self.bot.get_guild(config[str(ctx.author.id)])
            await ctx.send(f"You've already claimed residency on {server.name}.  You can not change this without "
                           f"talking to Ryan.")
            return

        await ctx.send("For the purpose of maintaining fairness in a ban, you're about to claim your mod residency to "
                       f"`{ctx.guild.name}`.  This can not be changed without talking to Ryan.  "
                       f"Do you wish to continue?\n\nType `yes` or `no` (case insensitive).")
        msg = await self.bot.wait_for('message',
                                      timeout=25.0,
                                      check=lambda m: m.author == ctx.author and m.channel == ctx.channel)

        if msg.content.casefold() == 'yes':  # register
            config[str(ctx.author.id)] = ctx.guild.id
            await ctx.send(f"Registered your residency to `{ctx.guild.name}`.  Type `;global_blacklist add <ID>` to "
                           f"vote on a user for the blacklist")

        elif msg.content.casefold() == 'no':  # cancel
            await ctx.send("Understood.  Exiting module.")

        else:  # invalid response
            await ctx.send("Invalid response")
        await hf.dump_json()

    @global_blacklist.command(aliases=['vote'], name="add")
    @blacklist_check()
    async def blacklist_add(self, ctx, user, *, reason: str = None):
        channel = self.bot.get_channel(533863928263082014)
        config = self.bot.db['global_blacklist']
        target_user = self.bot.get_user(int(user))

        async def post_vote_notification(num_of_votes):
            await ctx.message.add_reaction('✅')
            if target_user:
                message = f"📥 There are now **{num_of_votes}** vote(s) for `{target_user.name} " \
                          f"({user}`) (voted for by {ctx.author.name})"
            else:
                message = f"📥 There are now **{num_of_votes}** vote(s) for `{user}`." \
                          f" (voted for by {ctx.author.name})."
            if reason:
                message += "\nExtra info: {reason}"
            await channel.send(message)

        async def post_ban_notification():
            await ctx.message.add_reaction('✅')
            if target_user:
                message = f"`❌ {target_user.name} ({user}`) has received their final vote from {ctx.author.name}" \
                          f" and been added to the blacklist."
            else:
                message = f"`❌ `{user}` has received their final vote from {ctx.author.name}" \
                          f" and been added to the blacklist."
            await channel.send(message)

        if user in config['votes']:  # already been voted on before
            votes_list = config['votes'][user]  # a list of guild ids that have voted for adding to the blacklist
        else:
            if user not in config['blacklist']:
                votes_list = config['votes'][user] = []  # no votes yet, so an empty list
            else:
                await ctx.send("This user is already on the blacklist")
                return

        try:  # the guild ID that the person trying to add a vote belongs to
            residency = self.bot.db['global_blacklist']['residency'][str(ctx.author.id)]  # a guild id
        except KeyError:
            await ctx.send("Please claim residency on a server first with `;global_blacklist residency`")
            return

        if residency in votes_list:  # ctx.author's server already voted
            await ctx.send(f"Someone from your server `({self.bot.get_guild(residency).name})` has already voted")
        else:  # can take a vote
            votes_list.append(residency)
            num_of_votes = len(config['votes'][user])
            if num_of_votes == 3:
                config['blacklist'].append(int(user))  # adds the user id to the blacklist
                del (config['votes'][user])
                await post_ban_notification()
            else:
                await post_vote_notification(num_of_votes)

        await hf.dump_json()

    @global_blacklist.command(name='list')
    @blacklist_check()
    async def blacklist_list(self, ctx):
        """Lists the users with residencies on each server"""
        users_str = ''
        users_dict = {}
        config = self.bot.db['global_blacklist']['residency']
        for user_id in config:
            user = self.bot.get_user(int(user_id))
            guild = self.bot.get_guild(config[user_id])
            if guild in users_dict:
                users_dict[guild].append(user)
            else:
                users_dict[guild] = [user]
        for guild in users_dict:
            try:
                users_str += f"**{guild.name}:** {', '.join([user.name for user in users_dict[guild]])}\n"
            except AttributeError:
                pass
        emb = discord.Embed(title="Global blacklist residencies", description="Listed below is a breakdown of who "
                                                                              "holds residencies in which servers.\n\n")
        emb.description += users_str
        await ctx.send(embed=emb)


def setup(bot):
    bot.add_cog(Main(bot))
