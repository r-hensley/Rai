import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta
import json
from urllib.parse import urlparse
import re

import os

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


class Main:
    """My custom cog that does stuff!"""

    def __init__(self, bot):
        self.bot = bot
        # credit: https://gist.github.com/dperini/729294
        self._url = re.compile("""
            # protocol identifier
            (?:(?:https?|ftp)://)
            # user:pass authentication
            (?:\S+(?::\S*)?@)?
            (?:
              # IP address exclusion
              # private & local networks
              (?!(?:10|127)(?:\.\d{1,3}){3})
              (?!(?:169\.254|192\.168)(?:\.\d{1,3}){2})
              (?!172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2})
              # IP address dotted notation octets
              # excludes loopback network 0.0.0.0
              # excludes reserved space >= 224.0.0.0
              # excludes network & broacast addresses
              # (first & last IP address of each class)
              (?:[1-9]\d?|1\d\d|2[01]\d|22[0-3])
              (?:\.(?:1?\d{1,2}|2[0-4]\d|25[0-5])){2}
              (?:\.(?:[1-9]\d?|1\d\d|2[0-4]\d|25[0-4]))
            |
              # host name
              (?:(?:[a-z\u00a1-\uffff0-9]-*)*[a-z\u00a1-\uffff0-9]+)
              # domain name
              (?:\.(?:[a-z\u00a1-\uffff0-9]-*)*[a-z\u00a1-\uffff0-9]+)*
              # TLD identifier
              (?:\.(?:[a-z\u00a1-\uffff]{2,}))
              # TLD may end with dot
              \.?
            )
            # port number
            (?::\d{2,5})?
            # resource path
            (?:[/?#]\S*)?
        """, re.VERBOSE | re.I)

        self._emoji = re.compile(r'<a?:[A-Za-z0-9\_]+:[0-9]{17,20}>')

    def dump_json(self):
        with open(f'{dir_path}/database2.json', 'w') as write_file:
            json.dump(self.bot.db, write_file)
            write_file.flush()
            os.fsync(write_file.fileno())
        os.remove(f'{dir_path}/database.json')
        os.rename(f'{dir_path}/database2.json', f'{dir_path}/database.json')



    def is_admin():
        async def pred(ctx):
            return ctx.channel.permissions_for(ctx.author).administrator

        return commands.check(pred)

    async def on_message(self, msg):
        """Message as the bot"""
        if msg.channel == 'Direct Message with Ryry013#9234' \
                and int(msg.author.id) == self.bot.owner_id \
                and str(msg.content[0:3]) == 'msg':
            await self.bot.get_channel(int(msg.content[4:22])).send(str(msg.content[22:]))

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
            await self.bot.spamChan.send(
                '<@202995638860906496> **By {} in <#{}>**: {}'.format(msg.author.name, msg.channel.id, msg.content))

        if msg.author.id == self.bot.owner_id and self.bot.selfMute == True:
            await msg.delete()




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
    async def ping(self, ctx):
        """sends back 'hello'"""
        await ctx.send('hello')

    @commands.command()
    async def invite(self, ctx):
        """Gives an invite to bring this bot to your server"""
        await ctx.send(discord.utils.oauth_url(self.bot.user.id))

    # @commands.command()
    # async def at(self, ctx):
    #     """asyncio test"""
    #     x = False
    #     print(f'Before running the sleep, x should be false: {x}.')
    #     me = self.bot.get_guild(275146036178059265).get_member(self.bot.owner_id)
    #     x = await asyncio.sleep(2, str(me.status) == 'offline')
    #     print(f'I have ran x = await asyncio.sleep(=="offline").  If I\'m offline, x should be True: {x}.')

    # async def on_command_error(self, ctx, error):
    #     """Reduces 'command not found' error to a single line in console"""
    #     #  error = getattr(error, 'original', error)
    #     if isinstance(error, commands.CommandNotFound):
    #         print(error)

    @commands.group(invoke_without_command=True)
    async def report(self, ctx, user: discord.Member = None):
        """Japanese/Spanish server, make an anonymous report to mods"""
        if ctx.author not in self.bot.jpServ.members or ctx.author not in self.bot.spServ.members:
            return
        try:
            if not user:
                await ctx.message.delete()
        except discord.errors.Forbidden:
            print('Unable to delete message due to lacking permissions')

        conversation = ctx.author

        msg1Text = ["Please use the reactions to select your `(Language) Server`:\n"
                    "1) (English) English-Japanese Language Exchange\n"
                    "2) (日本語）English-Japanese Language Exchange\n"
                    "3) (English) English-Spanish Learning Server\n"
                    "4) (Español) English-Spanish Learning Server"]

        msg2Text = ["Welcome to the reporting module.  You're about to make a report to the mods of the "
                    "English-Japanese Exchange Server.  Please select one of the following options for your "
                    "report.\n\n"
                    "1) Send an anonymous report to the mods.\n"
                    "2) Request an audience with the mods to have a conversation with them (choose "
                    "this if you want a response to your report).\n"
                    "3) Cancel the report and leave this menu.",

                    "レポート機能へようこそ。あなたは 、English Japanese Language Exchange サーバーのモデレーター"
                    "に報告（レポート）しようとしています。レポートをするためには次のいずれかのオプションを"
                    "選択してください。\n\n"
                    "1) モデレーターに匿名のレポートを送ります\n"
                    "2) モデレーターと一緒にこのことについて会話ができるようにリクエストします"
                    "（あなたのレポートへの回答を希望する場合はこれを選択します）\n"
                    "3) レポートをキャンセルしてこのメ​​ニューを終了します",

                    '',

                    'Please someone help me make a Spanish translation']
        msg2Text[2] = msg2Text[0].replace('English-Japanese Exchange Server', 'English-Spanish Learning Server')

        msg3Text = ['Please type your report in one message below.  Make sure to include any relevant information, '
                    "such as who the report is about, which channel they did whatever you're reporting about was in, "
                    "and other users involved.",

                    "レポートは１つのメッセージで以下に書いてください。"
                    "レポートの対象者、対象のチャンネル、関係した他のユーザーなど、関連する情報を必ず含めてください。",

                    '',

                    'Please someone help me make a Spanish translation']
        msg3Text[2] = msg3Text[0]

        msg4Text = ['Thank you for your report.  The mods have been notified, and your name '
                    'will remain anonymous.',

                    'レポートはありがとうございます。管理者に匿名に送りました。',

                    '',

                    'Please someone help me make a Spanish translation']
        msg4Text[2] = msg4Text[0]

        msg5Text = ['.\n\n\n\n\n__'
                    'Please go here__: <#485391894356951050>\n'
                    "In ten seconds, I'll send a welcome message there.",

                    '.\n\n\n\n\n__'
                    'ここに行ってください__：<#485391894356951050>\n'
                    'そこに10秒後に歓迎のメッセージを送ります。',

                    '.\n\n\n\n\n__'
                    'Please go here__: <#491985321664184321>\n'
                    "In ten seconds, I'll send a welcome message there.",

                    'Please help me translate to Spanish'
                    ]

        fromMod = None

        def check(reaction, user):
            return user == ctx.author and (str(reaction.emoji) in "1⃣2⃣3⃣4⃣")

        def check2(m):
            return m.author == conversation and m.channel == m.author.dm_channel

        async def option1(language_requested: int):  # anonymous report
            # "please type your report below"
            await conversation.send(msg3Text[language_requested])  # 0: Eng      1: Jp       2: Eng         3: Span

            # wait for them to type
            try:
                reportMessage = await self.bot.wait_for('message', timeout=300.0, check=check2)
            except asyncio.TimeoutError:
                await conversation.send('Reporting module closed')

            # "thank you for the report"
            await conversation.send(msg4Text[language_requested])

            # send to spam and eggs
            if str(language_requested) in '01':
                await self.bot.get_channel(206230443413078016).send(f'Received report from a user: \n\n')
                await self.bot.get_channel(206230443413078016).send(f'{reportMessage.content}')
            elif str(language_requested) in '23':
                await self.bot.get_channel(296013414755598346).send(f'Received report from a user: \n\n')
                await self.bot.get_channel(296013414755598346).send(f'{reportMessage.content}')

        async def option2(userIn: discord.Member, language_requested: int, report_guild: str):  # get into report room
            REPORT_ROOM_ID = int(self.bot.db['report_room'][report_guild])
            report_room = self.bot.get_channel(REPORT_ROOM_ID)
            if not self.bot.db['current_report_member'][report_guild]:  # if no one is in the room
                if userIn.id in self.bot.db['report_room_waiting_list'][report_guild]:  # if user is in the waiting list
                    self.bot.db['report_room_waiting_list'][report_guild].remove(userIn.id)  # remove from waiting list
                self.bot.db['current_report_member'][report_guild] = userIn.id  # set the current user
                self.dump_json()
                await report_room.set_permissions(userIn, read_messages=True)
                if not fromMod:  # set below on "if user:", about 17 lines below
                    await userIn.send(msg5Text[language_requested])  # Please go to <#ID> channel

                await report_room.send(f'<@{userIn.id}>')
                await asyncio.sleep(10)

                msg6Text = [f"Welcome to the report room <@{userIn.id}>.  Only the mods can "
                            f"read your messages here, so you can now make your report.  When you are finished, "
                            f"type `;done` and a log of this conversation will be sent to you.  Please ping one of "
                            f"the mods you see online or `@Active Staff` if no one responds to you within a minute.",

                            f"レポートルームへようこそ<@{userIn.id}>。あなたのメッセージは"
                            "モデレーターだけが読むことができます。では（安心して）レポートを作成してください。"
                            "終わったら、`;done`と入力すると、この会話のログが送信されます。もし応答が返ってこなければ、"
                            "オンラインのモデレーターまたは`@Active Staff`にpingをしても構いません。",

                            f"Welcome to the report room <@{userIn.id}>.  Only the mods can "
                            f"read your messages here, so you can now make your report.  When you are finished, "
                            f"type `;done` and a log of this conversation will be sent to you.  Please ping one of "
                            f"the mods you see online or `@Mods` if no one responds to you within a minute.",

                            'Please help me translate to Spanish'
                            ]

                report_room_entry_message = await report_room.send(msg6Text[language_requested])
                self.bot.db["report_room_entry_message"][str(report_room.guild.id)] = report_room_entry_message.id

            else:
                if str(userIn.id) not in self.bot.db['report_room_waiting_list'][report_guild]:
                    self.bot.db['report_room_waiting_list'][report_guild].append(userIn.id)  # add to waiting list
                    self.dump_json()
                await userIn.send(f"Sorry but someone else is using the room right now.  I'll message you when it's ope"
                                  f"n in the order that I received requests.  You are position "
                                  f"{self.bot.db['report_room_waiting_list'][report_guild].index(userIn.id)+1} "
                                  f"on the list")
                if report_guild == '189571157446492161':
                    mod_channel = self.bot.get_channel(206230443413078016)  # spam and eggs
                else:
                    mod_channel = self.bot.get_channel(296013414755598346)  # sp. mod channel
                await mod_channel.send(f'The user {userIn.name} has tried to access the report room, but was put on '
                                       f'the wait list because someone else is currently using it.')

        if user:  # if the mod specified a user
            fromMod = True  # this will stop the bot from PMing the user
            if ctx.guild == self.bot.jpServ:
                await option2(user, 0, '189571157446492161')
            elif ctx.guild == self.bot.spanServ:
                await option2(user, 2, '243838819743432704')
            return

        async def options_menu():
            waiting_list_set = self.bot.db['report_room_waiting_list']
            full_waiting_list = waiting_list_set['189571157446492161'] + waiting_list_set['243838819743432704']
            if ctx.author.id not in full_waiting_list:
                msg1 = await conversation.send(msg1Text[0])  # select langauge and server
                await msg1.add_reaction("1⃣")  # ENG - japanese server
                await msg1.add_reaction('2⃣')  # JP - japanese server
                await msg1.add_reaction('3⃣')  # ENG - spanish server
                await msg1.add_reaction('4⃣')  # SP - spanish server

                try:
                    reaction, user = await self.bot.wait_for('reaction_add', timeout=300.0, check=check)
                except asyncio.TimeoutError:
                    await conversation.send('Reporting module closed')
                    return

                language_requested = int(reaction.emoji[0]) - 1

                if reaction.emoji[0] in '12':
                    report_guild = "189571157446492161"
                else:  # reacted with 3 or 4
                    report_guild = "243838819743432704"

                msg2 = await conversation.send(msg2Text[language_requested])  # introduction to reporting

                await msg2.add_reaction("1⃣")  # anonymous report
                await msg2.add_reaction('2⃣')  # report room
                await msg2.add_reaction('3⃣')  # cancel

                try:
                    reaction, user = await self.bot.wait_for('reaction_add', timeout=300.0, check=check)
                except asyncio.TimeoutError:
                    await conversation.send('Reporting module closed')
                    return

                if str(reaction.emoji) == "1⃣":  # requested to send a single message
                    await option1(language_requested)

                if str(reaction.emoji) == '2⃣':  # requested audience with mods
                    await option2(ctx.author, language_requested, report_guild)

                if str(reaction.emoji) == '3⃣':  # cancel
                    msg7Text = ['Understood.  Have a nice day!',
                                'わかりました。お元気で!',
                                'Understood.  Have a nice day!',
                                'Please help me translate Spanish']
                    await conversation.send(msg7Text[language_requested])
                    return

            else:  # if the user was on the waiting list, put them straight into the room
                if ctx.guild == self.bot.jpServ:
                    await option2(ctx.author, 0, '189571157446492161')
                elif ctx.guild == self.bot.spanServ:
                    await option2(ctx.author, 2, '243838819743432704')
                else:
                    for server_id in waiting_list_set:
                        if ctx.author.id in waiting_list_set[server_id]:
                            if server_id == '189571157446492161':
                                await option2(ctx.author, 0, server_id)  # english --> japanese server
                            else:
                                await option2(ctx.author, 2, server_id)  # english --> spanish server

        await options_menu()

    @report.command()
    @is_admin()
    async def check_waiting_list(self, ctx):
        if ctx.author not in self.bot.jpServ.members or ctx.author not in self.bot.spServ.members:
            return
        message = 'List of users on the waiting list: '
        report_guild = str(ctx.guild.id)
        members = []
        if self.bot.db['report_room_waiting_list'][report_guild]:
            for user in self.bot.db['report_room_waiting_list'][str(ctx.guild.id)]:
                members.append(user.name)
                message = message + ', '.join(members)
        else:
            message = 'There are no users on the waiting list'
        await ctx.send(message)

    @report.command()
    @is_admin()
    async def clear_waiting_list(self, ctx):
        if ctx.author not in self.bot.jpServ.members or ctx.author not in self.bot.spServ.members:
            return
        report_guild = str(ctx.guild.id)
        if self.bot.db['report_room_waiting_list'][report_guild]:
            self.bot.db['report_room_waiting_list'][report_guild] = []
            await ctx.send('Waiting list cleared')
        else:
            await ctx.send('There was no one on the waiting list.')

    @commands.command()
    async def done(self, ctx):
        """Only usable on Japanese/Spanish servers, finishes a report"""
        if ctx.author not in self.bot.jpServ.members or ctx.author not in self.bot.spServ.members:
            return
        report_room = self.bot.get_channel(self.bot.db["report_room"][str(ctx.guild.id)])
        if ctx.channel == report_room:
            report_member = ctx.guild.get_member(self.bot.db["current_report_member"][str(ctx.guild.id)])
            await report_room.set_permissions(report_member, overwrite=None)
            messages = []
            entryMessage = await report_room.get_message(self.bot.db["report_room_entry_message"][str(ctx.guild.id)])
            async for message in report_room.history(after=entryMessage):
                messages.append(message)
            messageLog = 'Start of log:\n'
            for i in messages:
                messageLog += f'**__{i.author}:__** {i.content} \n'
            if len(messageLog) > 2000:
                listOfMessages = []
                for i in range((len(messageLog) // 2000) + 1):
                    listOfMessages.append(messageLog[i * 2000:(i + 1) * 2000])
                for i in listOfMessages:
                    await report_member.send(i)
            else:
                await report_member.send(messageLog)
            self.bot.db["current_report_member"][str(report_room.guild.id)] = ""
            await report_room.send('Session closed, and a log has been sent to the user')
            for member_id in self.bot.db["report_room_waiting_list"][str(report_room.guild.id)]:
                member = report_room.guild.get_member(member_id)
                waiting_msg = await member.send('The report room is now open.  Try sending `;report` to me again.  '
                                                'If you wish to be removed from the waiting list, '
                                                'please react with the below emoji.')
                await waiting_msg.add_reaction('🚫')
                asyncio.sleep(10)
            self.dump_json()

    # removes people from the waiting list for ;report if they react with '🚫' to a certain message
    async def on_reaction_add(self, reaction, user: discord.User):
        if reaction.emoji == '🚫':
            if reaction.message.channel == user.dm_channel:
                waiting_list_dict = self.bot.db["report_room_waiting_list"]
                was_on_waiting_list = False
                for guild_id in waiting_list_dict:
                    if user.id in waiting_list_dict[guild_id]:
                        self.bot.db["report_room_waiting_list"][guild_id].remove(user.id)
                        self.dump_json()
                        await user.send("Understood.  You've been removed from the waiting list.  Have a nice day.")

                        mod_channel = self.bot.get_channel(self.bot.db["mod_channel"][guild_id])
                        msg_to_mod_channel = f"The user {user.name} was previously on the wait list for the " \
                                             f"report room but just removed themselves."
                        await mod_channel.send(msg_to_mod_channel)
                        was_on_waiting_list = True
                        break
                if not was_on_waiting_list:
                    await user.send("You aren't on the waiting list.")

    @commands.group(invoke_without_command=True)
    async def captcha(self, ctx):
        """Sets up a checkmark requirement to enter a server"""
        await ctx.send('This module sets up a requirement to enter a server based on a user pushing a checkmark.  '
                       '\n1) First, do `;captcha toggle` to setup the module'
                       '\n2) Then, do `;captcha set_channel` in the channel you want to activate it in.'
                       '\n3) Then, do `;captcha set_role <role name>` '
                       'to set the role you wish to remove upon them captchaing.')

    @captcha.command()
    async def toggle(self, ctx):
        guild = str(ctx.guild.id)
        if guild in self.bot.db['captcha']:
            guild_config = self.bot.db['captcha'][guild]
            if guild_config['enable']:
                guild_config['enable'] = False
                await ctx.send('Captcha module disabled')
            else:
                guild_config['enable'] = True
                await ctx.send('Captcha module enabled')
        else:
            self.bot.db['captcha'][guild] = {'enable': True, 'channel': '', 'role': ''}
            await ctx.send('Captcha module setup and enabled.')
        self.dump_json()

    @captcha.command()
    async def set_channel(self, ctx):
        guild = str(ctx.guild.id)
        if guild not in self.bot.db['captcha']:
            await self.toggle
        guild_config = self.bot.db['captcha'][guild]
        guild_config['channel'] = ctx.channel.id
        await ctx.send(f'Captcha channel set to {ctx.channel.name}')
        self.dump_json()

    @captcha.command()
    async def set_role(self, ctx, *, role_input: str =None):
        guild = str(ctx.guild.id)
        if guild not in self.bot.db['captcha']:
            await self.toggle
        guild_config = self.bot.db['captcha'][guild]
        role = discord.utils.find(lambda role: role.name == role_input, ctx.guild.roles)
        if not role:
            await ctx.send('Failed to find a role.  Please type the name of the role after the command, like '
                           '`;captcha set_role New User`')
        else:
            guild_config['role'] = role.id
            await ctx.send(f'Set role to {role.name} ({role.id})')
        self.dump_json()

    @captcha.command()
    async def post_message(self, ctx):
        guild = str(ctx.guild.id)
        if guild in self.bot.db['captcha']:
            guild_config = self.bot.db['captcha'][guild]
            if guild_config['enable']:
                msg = await ctx.send('Please react with the checkmark to enter the server')
                await msg.add_reaction('✅')

    async def on_guild_join(self, guild):
        await self.bot.get_user(202995638860906496).send(f'I have joined {guild.name}!')


def setup(bot):
    bot.add_cog(Main(bot))
