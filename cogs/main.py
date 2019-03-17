import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta
from .utils import helper_functions as hf
import langdetect
import hashlib

import os

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


class Main(commands.Cog):
    """My custom cog that does stuff!"""

    def __init__(self, bot):
        self.bot = bot
        hf.setup(bot)

    @commands.Cog.listener()
    async def on_message(self, msg):
        if msg.author.bot:
            return

        # "Experimental global watch list"
        # if msg.author.id == 202979770235879427:
        #     channel = self.bot.get_channel(374489744974807040)
        #     await channel.send(f"Message by {msg.author.name} in {msg.channel.mention}:\n\n```{msg.content}```")

        """Message as the bot"""
        if isinstance(msg.channel, discord.DMChannel) \
                and msg.author.id == self.bot.owner_id and msg.content[0:3] == 'msg':
            await self.bot.get_channel(int(msg.content[4:22])).send(str(msg.content[22:]))

        if not isinstance(msg.channel, discord.TextChannel):
            print(msg.created_at, msg.author.name)
            return  # stops the rest of the code unless it's in a guild

        """best sex dating"""
        words = ['amazingsexdating', 'bestdatingforall']
        for word in words:
            if word in msg.content:
                await self.bot.get_user(self.bot.owner_id).send(f"best spam sex in {msg.channel.mention}")
                print(self.bot.db['auto_bans'][str(msg.author.guild.id)]['enable'])
                print(datetime.utcnow(), '---', msg.author.joined_at, '-----', datetime.utcnow() - msg.author.joined_at)
        try:
            for word in words:
                if word in msg.content:
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
                ch = self.bot.get_channel(296013414755598346)
                me = self.bot.get_user(202995638860906496)
                fourteen = self.bot.get_user(136444391777763328)
                await ch.send(f"Mods ping from {msg.author.name} in {msg.channel.mention}\n"
                              f"```{msg.content}```")
                pm = f"Spanish server: mods ping from {msg.author.name} in {msg.channel.mention}\n" \
                     f"```{msg.content}```"
                await me.send(pm)
                await fourteen.send(pm)

        """Ping me if someone says my name"""
        cont = str(msg.content)
        if (
                (
                        'ryry' in cont.casefold()
                        or ('ryan' in cont.casefold() and msg.channel.guild != self.bot.spanServ)
                        or 'らいらい' in cont.casefold()
                        or 'ライライ' in cont.casefold()
                ) and
                not msg.author.bot  # checks to see if account is a bot account
        ):  # random sad face
            if 'aryan' in cont.casefold():  # why do people say this so often...
                return
            else:
                await self.bot.spamChan.send(
                    f'<@202995638860906496> **By {msg.author.name} in {msg.channel.mention}** ({msg.channel.name}): '
                    f'\n{msg.content}'
                    f'\n{msg.jump_url}')

        """Self mute"""
        if msg.author.id == self.bot.owner_id and self.bot.selfMute:
            try:
                await msg.delete()
            except discord.errors.NotFound:
                pass

        if msg.guild:
            """super_watch"""
            try:
                if msg.author.id in self.bot.db['super_watch'][str(msg.guild.id)]:
                    channel = self.bot.get_channel(self.bot.db['mod_channel'][str(msg.guild.id)])
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
                                await msg.author.send("You have hardcore enabled but you don't have the proper "
                                                      "learning role.  Please attach either 'Learning Spanish' or "
                                                      "'Learning English' to properly use hardcore mode, or take off "
                                                      "hardcore mode using the reactions in the server rules page")

    @commands.command()
    async def test(self, ctx):
        print(self.bot)
        print(ctx.bot)

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

    @commands.command()
    async def invite(self, ctx):
        """Gives an invite to bring this bot to your server"""
        await ctx.send(discord.utils.oauth_url(self.bot.user.id, permissions=discord.Permissions(permissions=3072)))

    @commands.group(invoke_without_command=True)
    async def report(self, ctx, user: discord.Member = None):
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

        if not user:
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
            f"{ctx.author.name} -  This user has entered the report room.  If they don't "
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

        if user != ctx.author:  # if the mods called in a user
            await report_room.send(f"{user.mention}: Please come to this channel")
            await self.report_room(ctx, config, user, report_text)
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

    @report.command()
    async def setup(self, ctx):
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
        start_message = await ctx.channel.get_message(config['entry_message'])
        config['current_user'] = None
        config['entry_message'] = None
        await hf.dump_json()
        await report_room.set_permissions(user, read_messages=False)

        message_log = 'Start of log:\n'
        async for message in ctx.channel.history(limit=None, after=start_message):
            message_log += f'**__{message.author}:__** {message.content} \n'

        if len(message_log) > 2000:
            list_of_messages = [message_log[i * 2000:(i + 1) * 2000] for i in range((len(message_log) // 2000) + 1)]
            for i in list_of_messages:
                await user.send(i)
        else:
            await user.send(message_log)

        await report_room.send('Session closed, and a log has been sent to the user')

        if config['waiting_list']:
            waiting_list = config['waiting_list']
            for member_id in waiting_list:
                if config['current_user']:
                    break
                member = ctx.guild.get_member(member_id)
                msg = 'The report room is now open.  Try sending `;report` to me again. If you ' \
                      'wish to be removed from the waiting list, please react with the below emoji. (not working)'
                waiting_msg = await member.send(msg)
                await waiting_msg.add_reaction('🚫')
                asyncio.sleep(10)

    @report.command()
    @hf.is_admin()
    async def check_waiting_list(self, ctx):
        guild_id = str(ctx.guild.id)
        if guild_id not in self.bot.db['report']:
            return
        config = self.bot.db['report'][guild_id]

        message = 'List of users on the waiting list: '
        if config['waiting_list']:
            members = [user.name for user in config['waiting_list']]
            message = message + ', '.join(members)
        else:
            message = 'There are no users on the waiting list'
        await ctx.send(message)

    @report.command()
    @hf.is_admin()
    async def clear_waiting_list(self, ctx):
        guild_id = str(ctx.guild.id)
        if guild_id not in self.bot.db['report']:
            return
        config = self.bot.db['report'][guild_id]

        if config['waiting_list']:
            config['waiting_list'] = []
            await ctx.send('Waiting list cleared')
        else:
            await ctx.send('There was no one on the waiting list.')

    @staticmethod
    async def report_options(ctx, report_text):
        """;report: Presents a user with the options of making an anonymous report or entering the report room"""

        def check(reaction, user):
            return user == ctx.author and (str(reaction.emoji) in "1⃣2⃣3⃣4⃣")  # 4⃣

        msg = await ctx.author.send(report_text[0])  # when the user first enters the module

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
        if config['current_user']:  # if someone is in the room already
            config['waiting_list'].append(user.id)
            msg = f"Sorry but someone else is using the room right now.  I'll message you when it's ope" \
                  f"n in the order that I received requests.  You are position " \
                  f"{config['waiting_list'].index(user.id)+1} on the list"
            await user.send(msg)  # someone is in the room, you've been added to waiting list
            await hf.dump_json()
            return
        if user.id in config['waiting_list']:
            config['waiting_list'].remove(user.id)
        config['current_user'] = user.id
        report_room = ctx.bot.get_channel(config['channel'])
        await report_room.set_permissions(user, read_messages=True)

        if from_mod:
            await user.send(report_text[6])
        else:
            await user.send(report_text[3])  # please go to the report room

        msg = await report_room.send(report_text[4])  # initial msg to mods
        await report_room.send(report_text[8])
        config['entry_message'] = msg.id
        await hf.dump_json()
        await asyncio.sleep(10)
        await report_room.send(report_text[5])  # full instructions text in report room

    # @commands.group(invoke_without_command=True)
    # async def report2(self, ctx, user: discord.Member = None):
    #     try:
    #         """Japanese/Spanish server, make an anonymous report to mods"""
    #         if ctx.author not in self.bot.jpServ.members and ctx.author not in self.bot.spanServ.members:
    #             return
    #         try:
    #             if not user and ctx.guild:
    #                 try:
    #                     await ctx.message.delete()
    #                 except discord.errors.NotFound:
    #                     pass
    #         except discord.errors.Forbidden:
    #             print('>>Unable to delete message due to lacking permissions<<')
    #
    #         conversation = ctx.author
    #
    #         if ctx.guild == self.bot.jpServ:
    #             msg1Text = ["Please use the reactions to select your `(Language) Server`:\n"
    #                         "1) (English) English-Japanese Language Exchange\n"
    #                         "2) (日本語）English-Japanese Language Exchange"]
    #         elif ctx.guild == self.bot.spanServ:
    #             msg1Text = None
    #         else:
    #             msg1Text = ["Please use the reactions to select your `(Language) Server`:\n"
    #                         "1) (English) English-Japanese Language Exchange\n"
    #                         "2) (日本語）English-Japanese Language Exchange\n"
    #                         "3) (English) English-Spanish Learning Server"]
    #
    #         msg2Text = ["Welcome to the reporting module.  You're about to make a report to the mods of the "
    #                     "English-Japanese Exchange Server.  Please select one of the following options for your "
    #                     "report.\n\n"
    #                     "1) Send an anonymous report to the mods.\n"
    #                     "2) Request an audience with the mods to have a conversation with them (choose "
    #                     "this if you want a response to your report).\n"
    #                     "3) Cancel the report and leave this menu.",
    #
    #                     "レポート機能へようこそ。あなたは 、English Japanese Language Exchange サーバーのモデレーター"
    #                     "に報告（レポート）しようとしています。レポートをするためには次のいずれかのオプションを"
    #                     "選択してください。\n\n"
    #                     "1) モデレーターに匿名のレポートを送ります\n"
    #                     "2) モデレーターと一緒にこのことについて会話ができるようにリクエストします"
    #                     "（あなたのレポートへの回答を希望する場合はこれを選択します）\n"
    #                     "3) レポートをキャンセルしてこのメ​​ニューを終了します",
    #
    #                     '',
    #
    #                     'Please someone help me make a Spanish translation']
    #         msg2Text[2] = msg2Text[0].replace('English-Japanese Exchange Server', 'English-Spanish Learning Server')
    #
    #         msg3Text = ['Please type your report in one message below.  Make sure to include any relevant information, '
    #                     "such as who the report is about, which channel they did whatever you're reporting about was in, "
    #                     "and other users involved.",
    #
    #                     "レポートは１つのメッセージで以下に書いてください。"
    #                     "レポートの対象者、対象のチャンネル、関係した他のユーザーなど、関連する情報を必ず含めてください。",
    #
    #                     '',
    #
    #                     'Please someone help me make a Spanish translation']
    #         msg3Text[2] = msg3Text[0]
    #
    #         msg4Text = ['Thank you for your report.  The mods have been notified, and your name '
    #                     'will remain anonymous.',
    #
    #                     'レポートはありがとうございます。管理者に匿名に送りました。',
    #
    #                     '',
    #
    #                     'Please someone help me make a Spanish translation']
    #         msg4Text[2] = msg4Text[0]
    #
    #         msg5Text = ['.\n\n\n\n\n__'
    #                     'Please go here__: <#485391894356951050>\n'
    #                     "In ten seconds, I'll send a welcome message there.",
    #
    #                     '.\n\n\n\n\n__'
    #                     'ここに行ってください__：<#485391894356951050>\n'
    #                     'そこに10秒後に歓迎のメッセージを送ります。',
    #
    #                     '.\n\n\n\n\n__'
    #                     'Please go here__: <#491985321664184321>\n'
    #                     "In ten seconds, I'll send a welcome message there.",
    #
    #                     'Please help me translate to Spanish'
    #                     ]
    #
    #         fromMod = None
    #
    #         def check(reaction, user):
    #             return user == ctx.author and (str(reaction.emoji) in "1⃣2⃣3⃣")  # 4⃣
    #
    #         def check2(m):
    #             return m.author == conversation and m.channel == m.author.dm_channel
    #
    #         async def option1(language_requested: int):  # anonymous report
    #             # "please type your report below"
    #             await conversation.send(msg3Text[language_requested])  # 0: Eng      1: Jp       2: Eng         3: Span
    #
    #             # wait for them to type
    #             try:
    #                 reportMessage = await self.bot.wait_for('message', timeout=300.0, check=check2)
    #             except asyncio.TimeoutError:
    #                 await conversation.send('Reporting module closed')
    #                 return
    #
    #             # "thank you for the report"
    #             await conversation.send(msg4Text[language_requested])
    #
    #             # send to spam and eggs
    #             if str(language_requested) in '01':
    #                 await self.bot.get_channel(206230443413078016).send(f'Received report from a user: \n\n')
    #                 await self.bot.get_channel(206230443413078016).send(f'{reportMessage.content}')
    #             elif str(language_requested) in '23':
    #                 await self.bot.get_channel(296013414755598346).send(f'Received report from a user: \n\n')
    #                 await self.bot.get_channel(296013414755598346).send(f'{reportMessage.content}')
    #
    #         async def option2(userIn: discord.Member, language_requested: int,
    #                           report_guild: str):  # get into report room
    #             REPORT_ROOM_ID = int(self.bot.db['report_room'][report_guild])
    #             report_room = self.bot.get_channel(REPORT_ROOM_ID)
    #             if not self.bot.db['current_report_member'][report_guild]:  # if no one is in the room
    #                 if userIn.id in self.bot.db['report_room_waiting_list'][
    #                     report_guild]:  # if user is in the waiting list
    #                     self.bot.db['report_room_waiting_list'][report_guild].remove(
    #                         userIn.id)  # remove from waiting list
    #                 self.bot.db['current_report_member'][report_guild] = userIn.id  # set the current user
    #                 await hf.dump_json()
    #                 await report_room.set_permissions(userIn, read_messages=True)
    #                 if not fromMod:  # set below on "if user:", about 17 lines below
    #                     await userIn.send(msg5Text[language_requested])  # Please go to <#ID> channel
    #
    #                 await report_room.send(f'<@{userIn.id}>')
    #                 await asyncio.sleep(10)
    #
    #                 msg6Text = [f"Welcome to the report room <@{userIn.id}>.  Only the mods can "
    #                             f"read your messages here, so you can now make your report.  When you are finished, "
    #                             f"type `;done` and a log of this conversation will be sent to you.  Please ping one of "
    #                             f"the mods you see online or `@Active Staff` if no one responds to you within a minute.",
    #
    #                             f"レポートルームへようこそ<@{userIn.id}>。あなたのメッセージは"
    #                             "モデレーターだけが読むことができます。では（安心して）レポートを作成してください。"
    #                             "終わったら、`;done`と入力すると、この会話のログが送信されます。もし応答が返ってこなければ、"
    #                             "オンラインのモデレーターまたは`@Active Staff`にpingをしても構いません。",
    #
    #                             f"Welcome to the report room <@{userIn.id}>.  Only the mods can "
    #                             f"read your messages here, so you can now make your report.  When you are finished, "
    #                             f"type `;done` and a log of this conversation will be sent to you.  Please ping one of "
    #                             f"the mods you see online or `@Mods` if no one responds to you within a minute.",
    #
    #                             'Please help me translate to Spanish'
    #                             ]
    #
    #                 report_room_entry_message = await report_room.send(msg6Text[language_requested])
    #                 self.bot.db["report_room_entry_message"][str(report_room.guild.id)] = report_room_entry_message.id
    #
    #             else:
    #                 if str(userIn.id) not in self.bot.db['report_room_waiting_list'][report_guild]:
    #                     self.bot.db['report_room_waiting_list'][report_guild].append(userIn.id)  # add to waiting list
    #                     await hf.dump_json()
    #                 await userIn.send(
    #                     f"Sorry but someone else is using the room right now.  I'll message you when it's ope"
    #                     f"n in the order that I received requests.  You are position "
    #                     f"{self.bot.db['report_room_waiting_list'][report_guild].index(userIn.id)+1} "
    #                     f"on the list")
    #                 if report_guild == '189571157446492161':
    #                     mod_channel = self.bot.get_channel(206230443413078016)  # spam and eggs
    #                 else:
    #                     mod_channel = self.bot.get_channel(296013414755598346)  # sp. mod channel
    #                 await mod_channel.send(
    #                     f'The user {userIn.name} has tried to access the report room, but was put on '
    #                     f'the wait list because someone else is currently using it.')
    #
    #         if user:  # if the mod specified a user
    #             if ctx.channel.permissions_for(ctx.author).administrator:
    #                 fromMod = True  # this will stop the bot from PMing the user
    #                 REPORT_ROOM_ID = int(self.bot.db['report_room'][str(ctx.guild.id)])
    #                 await user.send(f"Your presence has been requested in <#{REPORT_ROOM_ID}>.  There should be a "
    #                                 f"welcome message there explaining what is happening, but you might not see it so "
    #                                 f"it might be a blank channel.  In this channel, only the mods can see your messages, "
    #                                 f"and no other users will ever be able to see what you have typed in the past"
    #                                 f"if they too join the channel.  At the end, a log of the chat will be sent to you")
    #                 if ctx.guild == self.bot.jpServ:
    #                     await option2(user, 0, '189571157446492161')
    #                 elif ctx.guild == self.bot.spanServ:
    #                     await option2(user, 2, '243838819743432704')
    #                 return
    #             else:
    #                 await ctx.message.add_reaction('❌')
    #                 return
    #
    #         async def options_menu():
    #             waiting_list_set = self.bot.db['report_room_waiting_list']
    #             full_waiting_list = waiting_list_set['189571157446492161'] + waiting_list_set['243838819743432704']
    #             if ctx.author.id not in full_waiting_list:
    #                 if ctx.guild == self.bot.jpServ:
    #                     msg1 = await conversation.send(msg1Text[0])  # select langauge and server
    #                     await msg1.add_reaction("1⃣")  # ENG - japanese server
    #                     await msg1.add_reaction('2⃣')  # JP - japanese server
    #                     # await msg1.add_reaction('3⃣')  # ENG - spanish server
    #                     # await msg1.add_reaction('4⃣')  # SP - spanish server
    #                     skip_next_part = False
    #                 elif ctx.guild == self.bot.spanServ:
    #                     skip_next_part = True
    #                     report_guild = "243838819743432704"
    #                     language_requested = 2
    #                 else:
    #                     msg1 = await conversation.send(msg1Text[0])  # select langauge and server
    #                     await msg1.add_reaction("1⃣")  # ENG - japanese server
    #                     await msg1.add_reaction('2⃣')  # JP - japanese server
    #                     await msg1.add_reaction('3⃣')  # ENG - spanish server
    #                     # await msg1.add_reaction('4⃣')  # SP - spanish server
    #                     skip_next_part = False
    #
    #                 if not skip_next_part:
    #                     try:
    #                         reaction, user = await self.bot.wait_for('reaction_add', timeout=300.0, check=check)
    #                     except asyncio.TimeoutError:
    #                         await conversation.send('Reporting module closed')
    #                         return
    #
    #                     language_requested = int(reaction.emoji[0]) - 1
    #                     if reaction.emoji[0] in '12':
    #                         report_guild = "189571157446492161"
    #                     else:  # reacted with 3 or 4
    #                         report_guild = "243838819743432704"
    #
    #                 msg2 = await conversation.send(msg2Text[language_requested])  # introduction to reporting
    #
    #                 await msg2.add_reaction("1⃣")  # anonymous report
    #                 await msg2.add_reaction('2⃣')  # report room
    #                 await msg2.add_reaction('3⃣')  # cancel
    #
    #                 try:
    #                     reaction, user = await self.bot.wait_for('reaction_add', timeout=300.0, check=check)
    #                 except asyncio.TimeoutError:
    #                     await conversation.send('Reporting module closed')
    #                     return
    #
    #                 if str(reaction.emoji) == "1⃣":  # requested to send a single message
    #                     await option1(language_requested)
    #
    #                 if str(reaction.emoji) == '2⃣':  # requested audience with mods
    #                     await option2(ctx.author, language_requested, report_guild)
    #
    #                 if str(reaction.emoji) == '3⃣':  # cancel
    #                     msg7Text = ['Understood.  Have a nice day!',
    #                                 'わかりました。お元気で!',
    #                                 'Understood.  Have a nice day!',
    #                                 'Please help me translate Spanish']
    #                     await conversation.send(msg7Text[language_requested])
    #                     return
    #
    #             else:  # if the user was on the waiting list, put them straight into the room
    #                 if ctx.guild == self.bot.jpServ:
    #                     await option2(ctx.author, 0, '189571157446492161')
    #                 elif ctx.guild == self.bot.spanServ:
    #                     await option2(ctx.author, 2, '243838819743432704')
    #                 else:
    #                     for server_id in waiting_list_set:
    #                         if ctx.author.id in waiting_list_set[server_id]:
    #                             if server_id == '189571157446492161':
    #                                 await option2(ctx.author, 0, server_id)  # learning_english --> japanese server
    #                             else:
    #                                 await option2(ctx.author, 2, server_id)  # learning_english --> spanish server
    #
    #         await options_menu()
    #     except Exception as e:
    #         print('errored out')
    #         me = bot.get_user(self.bot.owner_id)
    #         await me.send("A user tried to use the report module but it failed.\n\n"
    #                       f"Username: {ctx.author.name}\n"
    #                       f"Server: {ctx.guild.name}\n"
    #                       f"Error: {e}")
    #         raise

    # @report2.command()
    # @hf.is_admin()
    # async def check_waiting_list(self, ctx):
    #     if ctx.author not in self.bot.jpServ.members or ctx.author not in self.bot.spanServ.members:
    #         return
    #     message = 'List of users on the waiting list: '
    #     report_guild = str(ctx.guild.id)
    #     members = []
    #     if self.bot.db['report_room_waiting_list'][report_guild]:
    #         for user in self.bot.db['report_room_waiting_list'][str(ctx.guild.id)]:
    #             members.append(user.name)
    #             message = message + ', '.join(members)
    #     else:
    #         message = 'There are no users on the waiting list'
    #     await ctx.send(message)
    #
    # @report2.command()
    # @hf.is_admin()
    # async def clear_waiting_list(self, ctx):
    #     if ctx.author not in self.bot.jpServ.members or ctx.author not in self.bot.spanServ.members:
    #         return
    #     report_guild = str(ctx.guild.id)
    #     if self.bot.db['report_room_waiting_list'][report_guild]:
    #         self.bot.db['report_room_waiting_list'][report_guild] = []
    #         await ctx.send('Waiting list cleared')
    #     else:
    #         await ctx.send('There was no one on the waiting list.')

    # @report2.command()
    # async def done(self, ctx):
    #     """Only usable on Japanese/Spanish servers, finishes a report"""
    #     if ctx.author not in self.bot.jpServ.members and ctx.author not in self.bot.spanServ.members:
    #         return
    #     report_room = self.bot.get_channel(self.bot.db["report_room"][str(ctx.guild.id)])
    #     if ctx.channel == report_room:
    #         report_member = ctx.guild.get_member(self.bot.db["current_report_member"][str(ctx.guild.id)])
    #         await report_room.set_permissions(report_member, overwrite=None)
    #         messages = []
    #         entryMessage = await report_room.get_message(self.bot.db["report_room_entry_message"][str(ctx.guild.id)])
    #         async for message in report_room.history(after=entryMessage):
    #             messages.append(message)
    #         messageLog = 'Start of log:\n'
    #         for i in messages:
    #             messageLog += f'**__{i.author}:__** {i.content} \n'
    #         if len(messageLog) > 2000:
    #             listOfMessages = []
    #             for i in range((len(messageLog) // 2000) + 1):
    #                 listOfMessages.append(messageLog[i * 2000:(i + 1) * 2000])
    #             for i in listOfMessages:
    #                 await report_member.send(i)
    #         else:
    #             await report_member.send(messageLog)
    #         self.bot.db["current_report_member"][str(report_room.guild.id)] = ""
    #         await report_room.send('Session closed, and a log has been sent to the user')
    #         for member_id in self.bot.db["report_room_waiting_list"][str(report_room.guild.id)]:
    #             member = report_room.guild.get_member(member_id)
    #             waiting_msg = await member.send('The report room is now open.  Try sending `;report` to me again.  '
    #                                             'If you wish to be removed from the waiting list, '
    #                                             'please react with the below emoji.')
    #             await waiting_msg.add_reaction('🚫')
    #             asyncio.sleep(10)
    #         await hf.dump_json()

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
                               ';l', ';q', ';queue', ';pause', ';volume', ';1', ';vol', ';np', ';list'])
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
            title = target_message.content
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

        log_channel = self.bot.get_channel(config['log_channel'])
        color = self.get_color_from_name(ctx)  # returns a RGB tuple unique to every username
        emb = discord.Embed(title=f"Question number: `{question_number}`",
                            description=f"Asked by {target_message.author.mention} in {target_message.channel.mention}",
                            color=discord.Color(color),
                            timestamp=datetime.utcnow())
        emb.add_field(name=f"Question:", value=f"{title}\n{target_message.jump_url}")
        if ctx.author != target_message.author:
            emb.set_footer(text=f"Question added by {ctx.author.name}")
        try:
            log_message = await log_channel.send(embed=emb)
        except discord.errors.HTTPException:
            await ctx.send("The question was too long")
            del (config['questions'][question_number])
            return
        config['questions'][str(question_number)]['log_message'] = log_message.id
        number_map = {'1': '1\u20e3', '2': '2\u20e3', '3': '3\u20e3', '4': '4\u20e3', '5': '5\u20e3',
                      '6': '6\u20e3', '7': '7\u20e3', '8': '8\u20e3', '9': '9\u20e3'}
        if question_number < 10:
            await target_message.add_reaction(number_map[str(question_number)])
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
            target_message = await ctx.channel.get_message(int(args[0]))  # this will work if the first arg is an ID
            if len(args) == 1:
                title = target_message.content  # if there was no text after the ID
            else:
                title = ' '.join(args[1:])  # if there was some text after the ID
        except (discord.errors.NotFound, ValueError):  # no ID cited in the args
            target_message = ctx.message  # use the current message as the question link
            title = ' '.join(args)  # turn all of args into the title

        await self.add_question(ctx, target_message, title)

    @question.command()
    @hf.is_admin()
    async def setup(self, ctx):
        """Use this command in your questions channel"""
        config = self.bot.db['questions'].setdefault(str(ctx.guild.id), {})
        if str(ctx.channel.id) in config:
            msg = await ctx.send("This will reset the questions database for this channel.  "
                                 "Do you wish to continue?")
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
                       f"question with `;question new <title>` in this channel.")
        await hf.dump_json()

    @question.command(aliases=['a'])
    async def answer(self, ctx, *, args=''):
        """Marks a question as answered,
        and has an optional answer_id field for if you wish to specify an answer message"""
        config = self.bot.db['questions'][str(ctx.guild.id)][str(ctx.channel.id)]
        questions = config['questions']
        args = args.split(' ')

        answer_message = answer_text = answer_id = None
        if args == ['']:  # if a user just inputs ;q a
            number = None
            for question in questions:
                if ctx.author.id == questions[question]['author']:
                    number = question
                    answer_message = ctx.message
                    break
            if not number:
                await ctx.send(f"Please enter the number of the question you wish to answer, like `;q a 3`.")
                return
        elif len(args) == 1:
            try:
                answer_message = await ctx.channel.get_message(int(args[0]))
                for question in questions:
                    if ctx.author.id == questions[question]['author']:
                        number = question
                        break
            except discord.errors.NotFound:
                number = args[0]
                answer_message = ctx.message  # no optional arguments are passed:   ;q a 1
                answer_text = ''
        else:
            try:
                number = args[0]  # example: ;q a 1 554490627279159341
                answer_id = int(args[1])
            except ValueError:
                number = args[0]  # Supplies text answer:   ;q a 1 blah blah answer goes here
                answer_message = ctx.message
                answer_text = ' '.join(args[1:])

        if answer_id:  # if other message is cited
            if 17 < len(str(answer_id)) < 21:
                try:
                    answer_message = await ctx.channel.get_message(int(answer_id))
                    answer_text = answer_message.content
                except discord.errors.NotFound:
                    await ctx.send(f"A corresponding message to the specified ID was not found.  `;q a <question_id> "
                                   f"<message id>`")
                    return
            else:
                answer_message = ctx.message
                answer_text = ' '.join(answer_message.content.split(' ')[3:])
            
        try:
            question = questions[number]
        except KeyError:
            await ctx.send(f"Invalid question number.  Check the log channel again and input a single number like "
                           f"`;question answer 3`.")
            return

        question_message = await ctx.channel.get_message(questions[number]['question_message'])
        if ctx.author != question_message.author and not hf.admin_check(ctx):
            await ctx.send(f"Only mods or the person who asked the question originally can mark it as answered")
            return

        try:
            log_channel = self.bot.get_channel(config['log_channel'])
            log_message = await log_channel.get_message(question['log_message'])

            emb = log_message.embeds[0]
            if answer_message.author != question_message.author:
                emb.description += f"\nAnswered by {answer_message.author.mention}"
            emb.title = "ANSWERED"
            emb.color = discord.Color.default()
            if not answer_text:
                answer_text = ''
            emb.add_field(name=f"Answer: ",
                          value=answer_text + '\n' + answer_message.jump_url)
            await log_message.edit(embed=emb)
        except discord.errors.NotFound:
            log_message = None
            await ctx.send(f"Message in log channel not found.  Continuing code.")

        try:
            question_message = await ctx.channel.get_message(question['question_message'])
            for reaction in question_message.reactions:
                if reaction.me:
                    await question_message.remove_reaction(reaction.emoji, self.bot.user)
        except discord.errors.NotFound:
            msg = await ctx.send("That question was deleted")
            await log_message.delete()
            await asyncio.sleep(5)
            await msg.delete()
            await ctx.message.delete()

        del(config['questions'][number])
        await hf.dump_json()
        if ctx.message:
            await ctx.message.add_reaction('\u2705')

    @question.command(aliases=['reopen'])
    @hf.is_admin()
    async def open(self, ctx, message_id):
        """Reopens a closed question, point message_id to the log message in the log channel"""
        config = self.bot.db['questions'][str(ctx.guild.id)][str(ctx.channel.id)]
        for question in config['questions']:
            if int(message_id) == config['questions'][question]['question_message']:
                del(config['questions'][question])
        log_channel = self.bot.get_channel(config['log_channel'])
        log_message = await log_channel.get_message(int(message_id))
        emb = log_message.embeds[0]
        emb.description = emb.description.split('\n')[0]
        question_message = await ctx.channel.get_message(int(emb.fields[0].value.split('/')[-1]))
        await self.add_question(ctx, question_message, question_message.content)
        await log_message.delete()
        hf.dump_json()

    @question.command()
    async def list(self, ctx):
        """Shows a list of currently open questions"""
        try:
            config = self.bot.db['questions'][str(ctx.guild.id)][str(ctx.channel.id)]['questions']
        except KeyError:
            await ctx.send(f"This channel is not setup as a questions channel.  Run `;question setup` in the "
                           f"questions channel to start setup.")
            return
        emb = discord.Embed(title=f"List of open questions:")
        for question in config:
            try:
                question_message = await ctx.channel.get_message(config[question]['question_message'])
                question_text = ' '.join(question_message.content.split(' '))
                print(question, question_message.id)
                emb.add_field(name=f"Question `{question}`",
                              value=f"By {question_message.author.mention}\n"
                                    f"{question_text}\n"
                                    f"{question_message.jump_url}")
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
        target_message = await log_channel.get_message(int(log_id))
        if target not in ['asker', 'answerer', 'question', 'title', 'answer']:
            await ctx.send(f"Invalid field specified in the log message.  Please choose a target to edit out of "
                           f"`asker`, `answerer`, `question`, `title`, `answer`")
            return
        emb = target_message.embeds[0]

        if target == 'question':
            try:
                question_id = int(text[0])  # ;q edit 555932038612385798 question 555943517994614784
                question_message = await ctx.channel.get_message(question_id)
                emb.set_field_at(0, name=emb.fields[0].name, value=question_message.jump_url)
            except ValueError:
                question_message = ctx.message  # ;q edit 555932038612385798 question <New question text>
                question_text = ' '.join(question_message.content.split(' ')[3:])
                emb.set_field_at(0, name=emb.fields[0].name, value=f"{question_text}\n{question_message.jump_url}")
        if target == 'title':
            title = ' '.join(text)
            emb.set_field_at(0, name=title, value=emb.fields[0].value)
        if target == 'asker':
            try:
                asker = ctx.guild.get_member(int(text[0]))
            except ValueError:
                await ctx.send(f"To edit the asker, give the user ID of the user.  For example: "
                               f"`;q edit <log_message_id> asker <user_id>`")
                return
            print(emb.description)
            new_description = emb.description.split(' ')
            print(new_description)
            new_description[2] = asker.mention
            print(new_description)
            emb.description = ' '.join(new_description)

        if emb.title == 'ANSWERED':
            if target == 'answerer':
                answerer = ctx.guild.get_member(int(text[0]))
                new_description = emb.description.split('Answered by ')[1] = answerer.mention
                emb.description = 'Answered by '.join(new_description)
            elif target == 'answer':
                try:  # ;q edit <log_message_id> answer <answer_id>
                    answer_message = await ctx.channel.get_message(int(text[0]))
                    emb.set_field_at(1, name=emb.fields[1].name, value=answer_message.jump_url)
                except ValueError:
                    answer_message = ctx.message  # ;q edit <log_message_id> answer <new text>
                    answer_text = 'answer '.join(ctx.message.split('answer ')[1:])
                    emb.set_field_at(1, name=emb.fields[1].name, value=f"{answer_text}\n{answer_message.jump_url}")

        if emb.footer.text:
            emb.set_footer(text=emb.footer.text + f", Edited by {ctx.author.name}")
        else:
            emb.set_footer(text=f"Edited by {ctx.author.name}")
        await target_message.edit(embed=emb)
        await ctx.message.add_reaction('\u2705')


def setup(bot):
    bot.add_cog(Main(bot))
