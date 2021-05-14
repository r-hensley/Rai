import discord
from discord.ext import commands
from .utils import helper_functions as hf
import asyncio
import datetime

import os
dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


class Reports(commands.Cog):
    """Help me"""

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        if ctx.guild:
            return True

    @commands.group(invoke_without_command=True)
    @commands.bot_has_permissions(send_messages=True)
    async def report(self, ctx, *, user=None):
        """Make a report to the mods"""
        print("report", ctx.author.id)
        if isinstance(ctx.channel, discord.DMChannel):
            return
        guild_id = str(ctx.guild.id)
        if guild_id not in self.bot.db['report']:
            await hf.safe_send(ctx, f"This server has not run the setup for the report function yet.  Please type "
                                    f"`;report setup`.")
            return
        config = self.bot.db['report'][guild_id]
        report_room = self.bot.get_channel(config['channel'])

        if user:
            user = await hf.member_converter(ctx, user)
            if not user:
                if not hf.admin_check(ctx):
                    await hf.safe_send(ctx,
                                       "You shouldn't type the report into the channel.  Just type `;report` and a "
                                       "menu will help you.")
                else:
                    await hf.safe_send(ctx,
                                       "I couldn't find that user.  Please try again, or type just `;report` if you "
                                       "want to make your own report")
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
        except discord.NotFound:
            pass

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
            await hf.safe_send(ctx.author, 'Understood.  Have a nice day!')
            return

    @report.command(name='setup')
    @hf.is_admin()
    @commands.bot_has_permissions(send_messages=True)
    async def report_setup(self, ctx):
        """Sets the channel"""
        try:
            mod_channel = self.bot.db['mod_channel'][str(ctx.guild.id)]
            if not mod_channel:
                del(self.bot.db['mod_channel'][str(ctx.guild.id)])
                await hf.safe_send(ctx, "Please set a mod channel by typing `;set_mod_channel` in a channel.")
                return
        except KeyError:
            await hf.safe_send(ctx, "Please set a mod channel by typing `;set_mod_channel` in a channel.")
            return
        perms = ctx.channel.permissions_for(ctx.me)
        if not perms.read_messages or not perms.read_message_history or not perms.manage_roles:
            try:
                await ctx.message.add_reaction('\N{CROSS MARK}')
            except discord.Forbidden:
                pass
            try:
                await hf.safe_send(ctx, "I need permissions for reading messages, reading message history, and "
                                        "managing either channel permissions or server roles.  Please check these")
            except discord.errors.Forbidden:
                await hf.safe_send(ctx.author, f"Rai lacks the permission to send messages in {ctx.channel.mention}.")
            return

        guild_id = str(ctx.guild.id)
        if guild_id in self.bot.db['report']:
            self.bot.db['report'][guild_id]['channel'] = ctx.channel.id
            await hf.safe_send(ctx, f"Successfully set the report room channel to {ctx.channel.mention}.")
        else:
            self.bot.db['report'][guild_id] = {'channel': ctx.channel.id,
                                               'current_user': None,
                                               'waiting_list': [],
                                               'entry_message': None}
            await hf.safe_send(ctx, f"Initial setup for report room complete.  The report room channel has been set to "
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
        try:
            start_message = await ctx.channel.fetch_message(config['entry_message'])
        except discord.NotFound:
            start_message = datetime.utcnow()
        config['current_user'] = None
        config['entry_message'] = None
        await report_room.set_permissions(user, overwrite=None)

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
        await hf.safe_send(ctx, message)

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
            await hf.safe_send(ctx, 'Waiting list cleared')
        else:
            await hf.safe_send(ctx, 'There was no one on the waiting list.')

    @report.command(name="disable")
    @hf.is_admin()
    async def report_disable(self, ctx):
        """Disables the report room module"""
        if str(ctx.guild.id) in self.bot.db['report']:
            del self.bot.db['report'][str(ctx.guild.id)]
            try:
                await hf.safe_send(ctx, "I've disabled the report module in your guild.")
            except discord.Forbidden:
                pass
        else:
            try:
                await hf.safe_send(ctx, "You don't have the report module enabled.")
            except discord.Forbidden:
                pass

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
        await hf.safe_send(ctx,
                           f"The report module has been reset on this server.  Check the permission overrides on the "
                           f"report channel to make sure there are no users left there.")

    @report.command(name="anonymous_ping")
    @hf.is_admin()
    async def report_anonymous_ping(self, ctx):
        """Enable/disable a `@here` ping for if someone makes an anonymous report"""
        try:
            config = self.bot.db['report'][str(ctx.guild.id)]
        except KeyError:
            return
        config['anonymous_ping'] = not config['anonymous_ping']
        if config['anonymous_ping']:
            await hf.safe_send(ctx, "Enabled pinging for anonymous reports.  I'll add a `@here` ping to the next one.")
        else:
            await hf.safe_send(ctx, "Disabled pinging for anonymous reports.")

    @report.command(name="room_ping")
    @hf.is_admin()
    async def report_room_ping(self, ctx):
        """Enable/disable a `@here` ping for if someone enters the report room"""
        try:
            config = self.bot.db['report'][str(ctx.guild.id)]
        except KeyError:
            return
        config['room_ping'] = not config['room_ping']
        if config['room_ping']:
            await hf.safe_send(ctx, "Enabled pinging for when someone enters the report room.  "
                                    "I'll add a `@here` ping to the next one.")
        else:
            await hf.safe_send(ctx, "Disabled pinging for the report room.")

    @staticmethod
    async def report_options(ctx, report_text):
        """;report: Presents a user with the options of making an anonymous report or entering the report room"""

        def check(reaction, user):
            return user == ctx.author and (str(reaction.emoji) in "1⃣2⃣3⃣4⃣")  # 4⃣

        try:
            msg = await hf.safe_send(ctx.author, report_text[0])  # when the user first enters the module
        except discord.errors.Forbidden:
            await hf.safe_send(ctx, f"I'm unable to complete your request, as the user does not have PMs "
                                    f"from server members enabled.")
            ctx.bot.db['report'][str(ctx.guild.id)]['current_user'] = None
            return

        await msg.add_reaction("1⃣")  # Send a report (report room)
        await msg.add_reaction('2⃣')  # Send an anonymous report
        await msg.add_reaction('3⃣')  # Talk to the mods (report room)
        await msg.add_reaction('4⃣')  # cancel

        try:
            reaction, user = await ctx.bot.wait_for('reaction_add', timeout=300.0, check=check)
            return reaction
        except asyncio.TimeoutError:
            await hf.safe_send(ctx.author, "Module timed out.")
            return

    @staticmethod
    async def anonymous_report(ctx, report_text):
        """;report: The code for an anonymous report submission"""
        await hf.safe_send(ctx.author, report_text[1])  # Instructions for the anonymous report

        def check(m):
            return m.author == ctx.author and isinstance(m.channel, discord.channel.DMChannel)

        try:
            msg = await ctx.bot.wait_for('message', timeout=300.0, check=check)
            await hf.safe_send(ctx.author, report_text[2])  # "thank you for the report"
            mod_channel = ctx.bot.get_channel(ctx.bot.db['mod_channel'][str(ctx.guild.id)])
            if not mod_channel:
                await hf.safe_send(ctx, "Unfortunately this server has hidden their mod channel from me, so I "
                                        "can't send your report anymore.")
                return
            initial_msg = 'Received report from a user: \n\n'
            if ctx.bot.db['report'][str(ctx.guild.id)].setdefault('anonymous_ping', False):
                initial_msg = '@here ' + initial_msg
            try:
                await hf.safe_send(mod_channel, initial_msg)
            except AttributeError:
                await hf.safe_send(ctx, "Please tell the admins of that server that they have not properly configured "
                                        "their mod channel, so I have nowhere to send this anonymous report. Sorry.")
            await hf.safe_send(mod_channel, msg.content)
            return
        except asyncio.TimeoutError:
            await hf.safe_send(ctx.author, f"Module timed out.")
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
                await hf.safe_send(mod_channel,
                                   f"{user.mention} ({user.name}) tried to enter the report room, but someone "
                                   f"else is already in it.  Try typing `;report done` in the report room, "
                                   f"and type `;report check_waiting_list` to see who is waiting.")
            except KeyError:
                await report_room.send(f"Note to the mods: I tried to send you a notification about the report room, "
                                       f"but you haven't set a mod channel yet.  Please type `;set_mod_channel` in "
                                       f"your mod channel.")
            return
        if user.id in config['waiting_list']:
            config['waiting_list'].remove(user.id)
        config['current_user'] = user.id
        if report_room.permissions_for(user).read_messages or not config.setdefault('room_ping', False):
            initial_msg = report_text[4][:-5]
        else:
            initial_msg = report_text[4]
        try:
            await report_room.set_permissions(user, read_messages=True)
        except discord.Forbidden:
            await user.send(f"The bot is not properly setup on this server. Please communicate with the mods "
                            f"in another way.")
            await report_room.send(f"WARNING: A user tried to enter the room, but I lacked the permission to edit "
                                   f"this channel to let them in. Please allow me to edit channel permissions.")
            config['current_user'] = None
            return

        if from_mod:
            try:
                await user.send(report_text[6])
            except discord.errors.Forbidden:
                await hf.safe_send(ctx, f"I'm unable to complete your request, as the user does not have PMs "
                                        f"from server members enabled.")
                ctx.bot.db['report'][str(ctx.guild.id)]['current_user'] = None
                return
        else:
            await user.send(report_text[3])  # please go to the report room

        msg = await report_room.send(initial_msg)  # initial msg to mods
        await report_room.send(report_text[8])
        config['entry_message'] = msg.id
        await asyncio.sleep(10)
        await report_room.send(report_text[5])  # full instructions text in report room


def setup(bot):
    bot.add_cog(Reports(bot))
