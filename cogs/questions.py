import re
import os
import json
import asyncio, aiohttp
from datetime import date, timedelta
from typing import Optional
from urllib.parse import quote

import discord
from discord.ext import commands
from bs4 import BeautifulSoup
from Levenshtein import distance as LDist

from .utils import helper_functions as hf
from cogs.utils.BotUtils import bot_utils as utils

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


async def find_and_unarchive_thread(ctx):
    for channel in ctx.guild.text_channels:
        try:
            async for thread in channel.archived_threads(limit=15):
                if thread.id == ctx.bot.db['questions'][str(ctx.guild.id)][str(ctx.channel.id)]['log_channel']:
                    try:
                        thread = await thread.edit(archived=False)
                    except discord.Forbidden:
                        await utils.safe_send(ctx, "I need to unarchive the questions log channel but I lacked the "
                                                f"permission to do that. Please unarchive this thread: "
                                                f"{thread.mention}.")
                        return
                    return thread
        except discord.Forbidden:
            pass  # The bot tried to look for archived threads in a channel it doesn't have `read_message_history`


class Questions(commands.Cog):
    """Help"""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_thread_join(self, thread: discord.Thread):
        try:
            channel_config = self.bot.db['questions'][str(thread.guild.id)][str(thread.parent.id)]
            questions = channel_config['questions']
            if not channel_config.get('threads', False):
                return
        except KeyError:
            return
        except AttributeError:  # probably thread.parent doesn't exist
            return

        if not hasattr(self.bot, "recently_joined_threads"):
            self.bot.recently_joined_threads = []

        if thread not in self.bot.recently_joined_threads:
            self.bot.recently_joined_threads.append(thread.id)
        else:
            return

        for question in questions:
            if thread.id == questions[question].get('thread', 0):
                return  # a question for this thread already exists
        if thread.id == channel_config['log_channel']:
            return  # the opened thread was the log channel being unarchived

        try:
            opening_message = await thread.parent.fetch_message(thread.id)
        except discord.NotFound:
            return
        ctx = await self.bot.get_context(opening_message)
        try:
            await self.question(ctx, args=opening_message.content)  # open a question
            try:
                self.bot.recently_joined_threads.remove(thread.id)
            except ValueError:
                pass
        except Exception:
            try:
                self.bot.recently_joined_threads.remove(thread.id)
            except ValueError:
                pass
            raise

    # @commands.Cog.listener()
    # async def on_thread_update(self, before: discord.Thread, after: discord.Thread):
    #     try:
    #         channel_config = self.bot.db['questions'][str(after.guild.id)][str(after.parent.id)]
    #         questions = channel_config['questions']
    #     except KeyError:
    #         return
    #
    #     if not channel_config.get('threads', False):
    #         return
    #
    #     is_question = False
    #     for question in questions:
    #         if questions[question].get('thread', 0) == after.id:
    #             is_question = True
    #             break
    #     if not is_question:
    #         return  # this thread is not associated with a question
    #
    #     # a thread was archived, reopen it if it simply closed due to the auto-archiving date
    #     if not before.archived and after.archived:
    #         human_closed = False  # True if a human manually archvied the thread
    #         async for entry in after.guild.audit_logs(limit=5, oldest_first=False,
    #                                                   action=discord.AuditLogAction.thread_update,
    #                                                   after=discord.utils.utcnow() - timedelta(seconds=10)):
    #             if entry.created_at > discord.utils.utcnow() - timedelta(seconds=10) and entry.target.id == after.id:
    #                 if entry.user.bot:
    #                     return
    #                 if entry.after.archived:
    #                     human_closed = True
    #                 break
    #
    #         if human_closed:  # a user manually archived the thread ==> close the question
    #             try:
    #                 last_message = [message async for message in after.history(limit=1)]  # returns a list of length 1
    #                 last_message = last_message[0]  # get the first message in it
    #                 if not last_message:
    #                     raise discord.NotFound
    #             except (IndexError, discord.NotFound):
    #                 return
    #             ctx = await self.bot.get_context(last_message)  # just need a random ctx
    #             ctx.message.author = ctx.guild.me  # to get permissions right
    #             ctx.message.content = ";q a"
    #             await self.answer(ctx, args="")  # close the question
    #
    #         else:  # the thread was auto-archived, reopen it
    #             try:
    #                 after = await after.edit(archived=False)
    #             except discord.Forbidden:
    #                 pass
    #
    #     # a thread was unarchived, open a question for it
    #     elif before.archived and not after.archived:
    #         for question in questions:
    #             if after.id == questions[question].get('thread', 0):
    #                 return  # a question for this thread already exists
    #         if after.id == channel_config['log_channel']:
    #             return  # the opened thread was the log channel being unarchived
    #         opening_message = await after.parent.fetch_message(after.id)
    #         ctx = await self.bot.get_context(opening_message)
    #         await self.question(ctx, args=opening_message.content)  # open the question

    def get_color_from_name(self, ctx):
        config = self.bot.db['questions'][str(ctx.channel.guild.id)]
        channel_list = sorted([int(channel) for channel in config])
        index = channel_list.index(ctx.channel.id) % 6
        # colors = ['00ff00', 'ff9900', '4db8ff', 'ff0000', 'ff00ff', 'ffff00'] below line is in hex
        colors = [65280, 16750848, 5093631, 16711680, 16711935, 16776960]
        return colors[index]

    async def add_question(self, ctx: commands.Context, target_message: discord.Message, title=None):
        try:
            config: dict = self.bot.db['questions'][str(ctx.guild.id)][str(ctx.channel.id)]
        except KeyError:
            try:
                await utils.safe_send(ctx,
                                   f"This channel is not setup as a questions channel.  Run `;question setup` in the "
                                   f"questions channel to start setup.")
            except discord.Forbidden:
                await utils.safe_send(ctx.author, "Rai lacks permissions to send messages in that channel")
                return
            return
        if not title:
            title = target_message.content

        # assign lowest available question index
        question_number = 1
        while str(question_number) in config['questions']:
            question_number += 1

        # allow burdbot to make questions in a certain channel
        if ctx.author.id == 720900750724825138 and ctx.channel.id == 620997764524015647:
            # burdbot submitted a question to AOTW_feedback
            if ctx.message.attachments:
                try:
                    actual_user_id = int(ctx.message.attachments[0].filename.split('-')[0])
                    actual_user = ctx.guild.get_member(actual_user_id)
                    if not actual_user:
                        raise ValueError
                    ctx.author = actual_user
                    target_message.author = actual_user
                except ValueError:
                    pass

        # if threads enabled in "config", create a thread for the channel
        if config.setdefault('threads', False):
            try:
                content = target_message.content.replace(";question", ";q")
                thread_title = f"[{question_number}] " + content.replace(';q ', '').split('\n')[0][:95]
                if not hasattr(self.bot, "recently_joined_threads"):
                    self.bot.recently_joined_threads = []
                if target_message.id not in self.bot.recently_joined_threads:
                    self.bot.recently_joined_threads.append(target_message.id)
                else:
                    return

                try:
                    thread = await target_message.create_thread(name=thread_title)
                except discord.HTTPException:
                    thread = ctx.guild.get_thread(target_message.id)

                await utils.safe_send(thread, "I've opened a thread corresponding to this question. Closing the thread "
                                           "will close the question, or you can type `;q a` inside this channel. "
                                           "If you give me permission to manage threads, I will automatically "
                                           "reopen this thread if it is autoarchived until someone "
                                           "closes the question.")

                try:
                    self.bot.recently_joined_threads.remove(thread.id)
                except ValueError:
                    pass

                thread_id = thread.id
            except discord.Forbidden:
                await utils.safe_send(ctx, "You've enabled thread support for this channel but I don't have the "
                                        "permission to create threads in this channel. Please fix this or rerun "
                                        "`;q setup` and choose to disable thread support.")
                return
        else:
            thread_id = None

        # begin filling in the database entry
        config['questions'][str(question_number)] = {}
        config['questions'][str(question_number)]['title'] = title
        config['questions'][str(question_number)]['question_message'] = target_message.id
        config['questions'][str(question_number)]['author'] = target_message.author.id
        config['questions'][str(question_number)]['command_caller'] = ctx.author.id
        config['questions'][str(question_number)]['date'] = date.today().strftime("%Y/%m/%d")
        config['questions'][str(question_number)]['thread'] = thread_id

        # assign a unique color to questions from each channel for logs with multiple channels
        color = self.get_color_from_name(ctx)  # returns a RGB tuple unique to every channel

        # begin creating question log embed
        emb = discord.Embed(title=f"Question number: `{question_number}`",
                            description=f"Asked by {target_message.author.mention} ({target_message.author.name}) "
                                        f"in {target_message.channel.mention}",
                            color=discord.Color(color),
                            timestamp=discord.utils.utcnow())

        # add question information to log embed
        if thread_id:
            thread_link = f"https://discord.com/channels/{ctx.guild.id}/{thread_id}/"
            jump_links = f"[Original Question]({target_message.jump_url})\n[Thread Link]({thread_link})"
        else:
            jump_links = f"[Original Question]({target_message.jump_url})"
        if len(f"{title}\n") > (1024 - len(target_message.jump_url)):
            emb.add_field(name=f"Question:", value=title[:1024])
            if title[1024:]:
                emb.add_field(name=f"Question (cont.):", value=f"{title[1023:]}\n")

            emb.add_field(name=f"Jump Link to Question:", value=jump_links)
        else:
            emb.add_field(name=f"Question:", value=f"{title[:1023 - len(jump_links)]}\n{jump_links}")
        if ctx.author != target_message.author:
            emb.set_footer(text=f"Question added by {ctx.author.name}")

        # update ;q list at bottom of log channel
        log_channel = ctx.guild.get_channel_or_thread(config['log_channel'])

        if not log_channel:
            log_channel = await find_and_unarchive_thread(ctx)

        if isinstance(log_channel, discord.Thread):
            # The above find_and_unarchive_thread() function should attempt to unarchive the thread too, so this
            # code is potentially repetitive. Note also if a bot lacks `Manage Threads` permission,
            # it's possible thread.edit(archived=False) may work a first time, but it'll fail when you try
            # a second time to unarchive a thread that is already unarchived. If the bot has `Manage Threads`,
            # then you can try again to unarchive the already-unarchived thread, it'll just pass by
            # with no action/error
            if log_channel.archived:
                try:
                    log_channel = await log_channel.edit(archived=False)
                except discord.Forbidden:
                    try:
                        await utils.safe_send(ctx, "The questions log thread associated with this channel is **archived** "
                                                "and I don't have permission to unarchive it. Please either unarchive "
                                                f"the log channel thread {log_channel.mention} or give me the "
                                                f"permission to `Manage Threads` in that channel.")
                    except (discord.HTTPException, discord.Forbidden):
                        pass
                    return

        try:
            log_message = await utils.safe_send(log_channel, embed=emb)
        except discord.Forbidden:
            await utils.safe_send(ctx, "I lack the ability to send messages in the log channel.")
            return

        try:
            await self._delete_log(ctx)
            await self._post_log(ctx)
            config['questions'][str(question_number)]['log_message'] = log_message.id
        except discord.HTTPException as err:
            if err.status == 400:
                await utils.safe_send(ctx, "The question was too long, or the embed is too big.")
            elif err.status == 403:
                await utils.safe_send(ctx, "I didn't have permissions to post in that channel")
            else:
                raise
            del (config['questions'][str(question_number)])
            return

        # react with question ID on user message if ID is less than 10
        number_map = {'1': '1\N{combining enclosing keycap}', '2': '2\N{combining enclosing keycap}',
                      '3': '3\N{combining enclosing keycap}', '4': '4\N{combining enclosing keycap}',
                      '5': '5\N{combining enclosing keycap}', '6': '6\N{combining enclosing keycap}',
                      '7': '7\N{combining enclosing keycap}', '8': '8\N{combining enclosing keycap}',
                      '9': '9\N{combining enclosing keycap}', '10': '\N{keycap ten}'}
        if question_number < 11:
            # I have NO idea why this is necessary, but sometimes during this function,
            # the target_message variable randomly gets its channel changed to the thread...
            # Once it's the thread, doing add_reaction becomes impossible
            if isinstance(target_message.channel, discord.Thread):
                target_message = await target_message.channel.parent.fetch_message(target_message.id)

            try:
                await target_message.add_reaction(number_map[str(question_number)])
            except discord.Forbidden:
                await utils.safe_send(ctx, f"I lack the ability to add reactions, please give me this permission")
            except discord.NotFound:  # emoji specified not found
                await ctx.send("I can't find that emoji.")
                # noinspection PyTypeChecker
                await ctx.invoke(self.answer, args=str(question_number))
                return

        # If someone creates a question for someone else, notify that user
        if target_message.author != ctx.author:
            msg_text = f"Hello, someone has marked one of your questions using my questions log feature.  It is now " \
                       f"logged in <#{config['log_channel']}>.  This will" \
                       f" help make sure you receive an answer.  When someone answers your question, please type " \
                       f"`;q a` to mark the question as answered.  Thanks!"
            try:
                await utils.safe_send(target_message.author, msg_text)
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.group(invoke_without_command=True, aliases=['q'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @commands.guild_only()
    async def question(self, ctx, *, args=None):
        """A module for asking questions, put the title of your quesiton like `;question <title>`"""
        if not args:
            msg = f"Type `;q <question text>` to make a question, or do `;help q`. For now, here's the questions list:"
            await utils.safe_send(ctx, msg)
            await ctx.invoke(self.question_list)
            return
        args = args.split(' ')

        if len(args) == 2:  # in case someone accidentally writes ;q 1 a instead of ;q a 1
            try:
                index = int(args[0])
                if args[1] != 'a':
                    raise ValueError
            except ValueError:
                pass
            else:
                await ctx.invoke(self.answer, args=args[0])
                return

        try:  # there is definitely some text in the arguments
            target_message = await ctx.channel.fetch_message(int(args[0]))  # this will work if the first arg is an ID
            await ctx.message.add_reaction('⤴')
            if len(args) == 1:
                title = target_message.content  # if there was no text after the ID
            else:
                title = ' '.join(args[1:])  # if there was some text after the ID
        except (discord.NotFound, ValueError):  # no ID cited in the args
            target_message = ctx.message  # use the current message as the question link
            title = ' '.join(args)  # turn all of args into the title

        await self.add_question(ctx, target_message, title)

    @question.command(name='setup')
    @hf.is_admin()
    async def question_setup(self, ctx):
        """Use this command in your questions channel"""
        config = self.bot.db['questions'].setdefault(str(ctx.guild.id), {})
        if str(ctx.channel.id) in config:
            msg = await utils.safe_send(ctx, "This will reset the questions database for this channel.  "
                                          "Do you wish to continue?  Type `y` to continue.")
            try:
                await self.bot.wait_for('message', timeout=15.0, check=lambda m: m.content == 'y' and
                                                                                 m.author == ctx.author)
            except asyncio.TimeoutError:
                await msg.edit(content="Canceled...", delete_after=10.0)
                return
        msg_1 = await utils.safe_send(ctx,
                                   f"Questions channel set as {ctx.channel.mention}.  In the way I just linked this "
                                   f"channel, please give me a link to the log channel "
                                   f"you wish to use for this channel.")
        try:
            msg_2 = await self.bot.wait_for('message', timeout=20.0, check=lambda m: m.author == ctx.author)
        except asyncio.TimeoutError:
            await msg_1.edit(content="Canceled...", delete_after=10.0)
            return

        try:
            log_channel_id = int(msg_2.content.split('<#')[1][:-1])
            log_channel = ctx.guild.get_channel_or_thread(log_channel_id)
            if not log_channel:
                raise NameError
        except (IndexError, NameError):
            await utils.safe_send(ctx, f"Invalid channel specified.  Please start over and specify a link to a channel "
                                    f"(should highlight blue)")
            return

        msg_3 = await utils.safe_send(ctx,
                                   f"Set the log channel as {log_channel.mention}.\n\n"
                                   f"Do you wish to integrate the questions "
                                   f"module with Discord threads? [Yes/No]")
        try:
            def check(m):
                return (m.author == ctx.author) and \
                       (m.channel == ctx.channel) and \
                       (m.content.casefold() in ['yes', 'no'])

            msg_4 = await self.bot.wait_for('message', timeout=20.0, check=check)
        except asyncio.TimeoutError:
            await msg_3.edit(content="Question has timed out. Please restart the command.", delete_after=10.0)
            return

        if msg_4.content.casefold() == "yes":
            threads = True
        elif msg_4.content.casefold() == "no":
            threads = False
        else:
            return

        config[str(ctx.channel.id)] = {'questions': {},
                                       'log_channel': log_channel_id,
                                       "threads": threads}

        await utils.safe_send(ctx, "Setup complete. Try starting your first "
                                "question with `;question <title>` in this channel.")

    @question.command(aliases=['a'])
    async def answer(self, ctx, *, args=''):
        """Marks a question as answered, format: `;q a <question_id 0-9> [answer_id]`
        and has an optional answer_id field for if you wish to specify an answer message"""
        if isinstance(ctx.channel, discord.Thread):
            question_channel = ctx.channel.parent
        else:
            question_channel = ctx.channel

        # get database configuration for this channel
        try:
            config = self.bot.db['questions'][str(ctx.guild.id)][str(question_channel.id)]
        except KeyError:
            await utils.safe_send(ctx,
                               f"This channel is not setup as a questions channel.  Please make sure you mark your "
                               f"question as 'answered' in the channel you asked it in.")
            return
        except AttributeError:  # NoneType object has no attribute 'id' (used in a DM)
            return
        questions = config['questions']
        args = args.split(' ')

        # code for the ";q a" shortcut
        async def self_answer_shortcut():
            for question_number in questions:
                if ctx.author.id == questions[question_number]['author']:
                    return int(question_number)  # question author can use just ";q a"
                if questions[question_number].get('thread', 0) == ctx.channel.id:
                    return int(question_number)  # mods can also use it in a thread

            # if the code gets here, it never returned anywhere above
            await utils.safe_send(ctx, f"I can't find a question to close (maybe your question was "
                                    f"already marked as answered?) If you're trying to close someone else's question, "
                                    f"only the original asker can close a question by typing `;q a`. "
                                    f"Others must specify which question "
                                    f"they're trying to answer using `;q a <question id>`.  "
                                    f"For example, `;q a 3`.")
            raise NameError

        if args == ['']:  # if a user just inputs ;q a
            try:
                number = await self_answer_shortcut()
            except NameError:
                # Error message is already sent to user in above function
                return
            answer_message = ctx.message
            answer_text = ''
            if not number:
                await utils.safe_send(ctx, f"Please enter the number of the question you wish to answer, like `;q a 3`.")
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
                    except discord.NotFound:
                        await utils.safe_send(ctx, f"I thought `{single_arg}` was a message ID but I couldn't find that "
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
            except discord.NotFound:
                await utils.safe_send(ctx,
                                   f"A corresponding message to the specified ID was not found.  `;q a <question_id> "
                                   f"<message id>`")
                return

        # Set question number and question
        try:
            number = str(number)  # the question number
            question = questions[number]  # question config
        except KeyError:
            await utils.safe_send(ctx,
                               f"Invalid question number.  Check the log channel again and input a single number like "
                               f"`;question answer 3`.  Also, make sure you're answering in the right channel.")
            return
        except Exception:
            await utils.safe_send(ctx, f"You've done *something* wrong... (´・ω・`)")
            raise

        try:
            # First, try to get thread normally
            log_channel = ctx.guild.get_channel_or_thread(config['log_channel'])

            # If that doesn't work, try to find the thread in all the archived threads per channel
            if not log_channel:
                log_channel = await find_and_unarchive_thread(ctx)

            # If it still doesn't work, give up.
            if not log_channel:
                await utils.safe_send(ctx, "I couldn't find the log channel for this questions channel. Please reset "
                                        "the questions module here.\n\nIf your log channel is a thread, check if the "
                                        f"thread is archived: <#{config['log_channel']}>")
                return

            log_message = await log_channel.fetch_message(question['log_message'])
        except discord.NotFound:
            log_message = None
            await utils.safe_send(ctx, f"Message in log channel not found.  Continuing code.")
        except KeyError:
            log_message = None
            await utils.safe_send(ctx, "Sorry I think this question got a bit bugged out. I'm going to close it.")

        try:
            question_message = await question_channel.fetch_message(question['question_message'])
            if ctx.author.id not in [question_message.author.id, question['command_caller'], self.bot.user.id] \
                    and not hf.submod_check(ctx) and ctx.author.id not in \
                    self.bot.db['channel_mods'].get(str(ctx.guild.id), {}).get(str(question_channel.id), []):
                await utils.safe_send(ctx, f"Only mods or the person who asked/started the question "
                                        f"originally can mark it as answered.")
                return
        except discord.NotFound:
            if log_message:
                await log_message.delete()
            msg = ""
            author = ctx.guild.get_member(question["author"])
            if author:
                msg = f"Original question message for question {number} by {str(author)} not found. Closing question."
            else:
                msg = f"Original question message for question {number} not found. Closing question."
            del questions[number]
            msg = await utils.safe_send(ctx, msg)
            await asyncio.sleep(5)

            try:
                await msg.delete()
            except discord.NotFound:
                pass

            try:
                await ctx.message.delete()
            except discord.NotFound:
                pass

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
                          value=answer_text + '\n' + f"[Jump URL]({answer_message.jump_url})")
            if isinstance(log_message.channel, discord.Thread):
                if log_message.channel.archived:
                    try:
                        log_message = await log_message.channel.edit(archived=False)
                    except discord.Forbidden:
                        await utils.safe_send(ctx, "The questions log thread associated with this channel is **archived** "
                                                "and I don't have permission to unarchive it. Please either unarchive "
                                                f"the log channel thread {log_message.channel.mention} or give me the "
                                                f"permission to `Manage Threads` in that channel.")
                        return
            await log_message.edit(embed=emb)

        try:
            question_message = await question_channel.fetch_message(question['question_message'])
        except discord.NotFound:
            msg = await utils.safe_send(ctx, "That question was deleted")
            await log_message.delete()
            await asyncio.sleep(5)
            await msg.delete()
            await ctx.message.delete()
        else:
            for reaction in question_message.reactions:
                if reaction.me:
                    try:
                        await question_message.remove_reaction(reaction.emoji, self.bot.user)

                    except discord.Forbidden:
                        await utils.safe_send(ctx, f"I lack the ability to add reactions, please give me this permission")

        # add thumbs up reaction before archiving thread
        if ctx.message:
            try:
                await ctx.message.add_reaction('\u2705')
            except discord.Forbidden:
                await utils.safe_send(ctx, f"I lack the ability to add reactions, please give me this permission")
            except (discord.NotFound, discord.HTTPException):
                pass

        # archive the thread attached to the message if it exists
        thread = ctx.guild.get_thread(question_message.id)
        if thread:
            try:
                thread = await thread.edit(archived=True, auto_archive_duration=60)
            except (discord.Forbidden, discord.HTTPException):
                pass

        try:
            del (config['questions'][number])
        except KeyError:
            pass

        await self._delete_log(ctx)
        await self._post_log(ctx)

    @question.command(aliases=['reopen', 'bump'])
    @hf.is_admin()
    async def open(self, ctx, message_id):
        """Reopens a closed question, point message_id to the log message in the log channel"""
        if isinstance(ctx.channel, discord.Thread):
            question_channel = ctx.channel.parent
        else:
            question_channel = ctx.channel

        config = self.bot.db['questions'][str(ctx.guild.id)][str(question_channel.id)]

        question = None
        for question in config['questions']:
            if int(message_id) == config['questions'][question]['log_message']:
                question = config['questions'][question]
                break
        if not question:
            return

        log_channel = ctx.guild.get_channel_or_thread(config['log_channel'])
        try:
            log_message = await log_channel.fetch_message(int(message_id))
        except discord.NotFound:
            await utils.safe_send(ctx, f"Specified log message not found")
            return
        emb = log_message.embeds[0]
        if emb.title == 'ANSWERED':
            emb.description = emb.description.split('\n')[0]
            try:
                question_message = await question_channel.fetch_message(int(emb.fields[0].value.split('/')[-1]))
            except discord.NotFound:
                await utils.safe_send(ctx, f"The message for the original question was not found")
                return
            await self.add_question(ctx, question_message, question_message.content)
        else:
            new_log_message = await utils.safe_send(log_channel, embed=emb)
            question['log_message'] = new_log_message.id
        await log_message.delete()

    @question.command(name='list')
    async def question_list(self, ctx, target_channel=None):
        """Shows a list of currently open questions"""
        question_channel = ctx.channel
        if isinstance(ctx.channel, discord.Thread):
            if not isinstance(ctx.channel.parent, discord.ForumChannel):  # bug if someone calls ;q from inside forum
                question_channel = ctx.channel.parent

        if not target_channel:
            target_channel = question_channel
        try:
            config = self.bot.db['questions'][str(ctx.guild.id)]
        except KeyError:
            await utils.safe_send(target_channel, f"There are no questions channels on this server.  Run `;question"
                                               f" setup` in the questions channel to start setup.")
            return

        # getting the main log channel
        if str(question_channel.id) in config:
            log_channel_id = config[str(question_channel.id)]['log_channel']  # main question channels
        elif str(ctx.guild.id) in config:
            log_channel_id = config[str(ctx.guild.id)]['log_channel']  # a default log channel for "all other chan."
        else:
            log_channel_id = None
            for q_chan in config:
                if config[q_chan]['log_channel'] == question_channel.id:
                    log_channel_id = question_channel.id  # if you call from a log channel instead of a question channel
                    break
            if not log_channel_id:
                await utils.safe_send(target_channel, "This channel is not setup as a questions channel.")
                return

        first = True
        deleted_questions = []
        # the ⁣ are invisble tags to help the _list_update function find this embed
        emb = discord.Embed(title=f"⁣List⁣ of open questions (sorted by channel then date):", color=0x707070)
        for channel in config:
            if config[channel]['log_channel'] != log_channel_id:
                continue
            channel_config = config[str(channel)]['questions']
            question_channel = ctx.guild.get_channel_or_thread(int(channel))
            if not question_channel:
                continue
            if first:
                first = False
                emb.description = f"**__#{question_channel.name}__**"
            else:
                if channel_config:
                    emb.add_field(name=f"⁣**__{'　' * 30}__**⁣",
                                  value=f'**__#{question_channel.name}__**', inline=False)

            for question in channel_config.copy():
                try:
                    if question not in channel_config:  # race conditions failing
                        await utils.safe_send(ctx, "Seems you're maybe trying things too fast. Try again.")
                        return
                    q_config = channel_config[question]
                    question_message = await question_channel.fetch_message(q_config['question_message'])
                    question_text = ' '.join(question_message.content.split(' '))

                    if question_message.channel.id == 620997764524015647:
                        if question_message.author.id == 720900750724825138:
                            if question_message.attachments:
                                try:
                                    actual_user_id = int(question_message.attachments[0].filename.split('-')[0])
                                    actual_user = ctx.guild.get_member(actual_user_id)
                                    if not actual_user:
                                        raise ValueError
                                    question_message.author = actual_user
                                except ValueError:
                                    pass

                    value_text = f"By {question_message.author.mention} in {question_message.channel.mention}\n"

                    if q_config.get('responses', None):
                        log_message = ctx.guild.get_channel_or_thread(log_channel_id)
                        try:
                            log_message = await log_message.fetch_message(q_config['log_message'])
                        except discord.Forbidden:
                            await utils.safe_send(ctx, f"I Lack the ability to see messages or message history in "
                                                    f"{log_message.mention}.")
                            return
                        value_text += f"__[Responses: {len(q_config['responses'])}]({log_message.jump_url})__\n"

                    thread_id = q_config.get("thread", None)
                    if thread_id:
                        thread_link = f"https://discord.com/channels/{ctx.guild.id}/{thread_id}/"
                        jump_links = f"[Original Question]({question_message.jump_url})\n[Thread Link]({thread_link})"
                    else:
                        jump_links = f"[Original Question]({question_message.jump_url})"
                    value_text += f"⁣⁣⁣⁣\n{jump_links}"
                    text_splice = 800 - len(value_text)
                    if len(question_text) > text_splice:
                        question_text = question_text[:-3] + '...'
                    value_text = value_text.replace("⁣⁣⁣⁣", question_text[:text_splice]).replace(";q ", "")
                    emb.add_field(name=f"Question `{question}`", value=value_text)
                except discord.NotFound:
                    deleted_questions.append(question)
                    continue
                    # await ctx.invoke(self.answer, args=question)
                    # # del(channel_config[question])
                    # continue
                    # emb.add_field(name=f"Question `{question}`",
                    #               value="original message not found")
        await utils.safe_send(target_channel, embed=emb)

        for question in deleted_questions:
            # author = ctx.guild.get_member(question_data[1]['author'])
            await ctx.invoke(self.answer, args=question)

    @question.command()
    @hf.is_admin()
    async def edit(self, ctx, log_id, target, *text):
        """
        Edit either the asker, answerer, question, title, or answer of a question log in the log channel

        Usage: `;q edit <log_id> <asker|answerer|question|title|answer> <new data>`.

        Example: `;q edit 2 question  What is the difference between が and は`.
        """
        config = self.bot.db['questions'][str(ctx.guild.id)][str(ctx.channel.id)]
        log_channel = ctx.guild.get_channel_or_thread(config['log_channel'])
        if not log_channel:
            log_channel = await find_and_unarchive_thread(ctx)
        target_message = await log_channel.fetch_message(int(log_id))
        if target not in ['asker', 'answerer', 'question', 'title', 'answer']:
            await utils.safe_send(ctx,
                               f"Invalid field specified in the log message.  Please choose a target to edit out of "
                               f"`asker`, `answerer`, `question`, `title`, `answer`")
            return
        emb = target_message.embeds[0]

        if target == 'question':
            try:
                question_id = int(text[0])  # ;q edit 555932038612385798 question 555943517994614784
                question_message = await ctx.channel.fetch_message(question_id)
                emb.set_field_at(0, name=emb.fields[0].name, value=f"{question_message.content[:900]}\n"
                                                                   f"[Jump URL]({question_message.jump_url}))")
            except ValueError:
                question_message = ctx.message  # ;q edit 555932038612385798 question <New question text>
                question_text = ' '.join(question_message.content.split(' ')[3:])
                emb.set_field_at(0, name=emb.fields[0].name,
                                 value=f"{question_text}\n[Jump URL]({question_message.jump_url})")
        if target == 'title':
            title = ' '.join(text)
            jump_url = emb.fields[0].split('\n')[-1]
            emb.set_field_at(0, name=emb.fields[0].name, value=f"{title}\n[Jump URL]({jump_url})")
        if target == 'asker':
            try:
                asker = ctx.guild.get_member(int(text[0]))
            except ValueError:
                await utils.safe_send(ctx, f"To edit the asker, give the user ID of the user.  For example: "
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
                    emb.set_field_at(1, name=emb.fields[1].name, value=f"[Jump URL]({answer_message.jump_url})")
                except ValueError:
                    answer_message = ctx.message  # ;q edit <log_message_id> answer <new text>
                    answer_text = 'answer '.join(ctx.message.split('answer ')[1:])
                    emb.set_field_at(1, name=emb.fields[1].name, value=f"{answer_text[:900]}\n"
                                                                       f"[Jump URL]({answer_message.jump_url})")

        if emb.footer.text:
            emb.set_footer(text=emb.footer.text + f", Edited by {ctx.author.name}")
        else:
            emb.set_footer(text=f"Edited by {ctx.author.name}")
        await target_message.edit(embed=emb)
        try:
            await ctx.message.add_reaction('\u2705')
        except discord.Forbidden:
            await utils.safe_send(ctx, f"I lack the ability to add reactions, please give me this permission")

    # 'questions'
    #   >id of guild
    #     > id of question channel
    #           > 'log_channel'
    #           > 'questions'
    #                 > 1
    #                       > title, question_message, author, command_caller, date, log_message(id)
    #                 > 2
    #                       > title, question_message, author, command_caller, date, log_message

    @commands.command(hidden=True)
    async def resp(self, ctx, index, *, response):
        """Alias for `;q resp`"""
        x = self.bot.get_command('question respond')
        if await x.can_run(ctx):
            await ctx.invoke(x, index, response=response)

    @question.command(aliases=['resp', 'r'])
    async def respond(self, ctx, index, *, response):
        """Respond to a question in the question log and log your response. You must do this in the channel \
        that the question was originally logged in. Example: `;q resp 3 I think this is correct`."""
        if isinstance(ctx.channel, discord.Thread):
            question_channel = ctx.channel.parent
        else:
            question_channel = ctx.channel

        try:
            config = self.bot.db['questions'][str(ctx.guild.id)][str(question_channel.id)]
        except KeyError:
            return
        if not response:
            await utils.safe_send(ctx, "You need to type something for your response.")
            return
        if len(response.split()) == 1:  # refers to a question ID of your response in the same channel
            try:
                msg = await ctx.channel.fetch_message(int(response))
                await ctx.message.add_reaction('⤴')
                ctx.message = msg
                ctx.author = msg.author
                response = msg.content
            except (discord.NotFound, ValueError):
                pass
        if index not in config['questions']:
            await utils.safe_send(ctx, "Invalid question index. Make sure you're typing this command in the channel "
                                    "the question was originally made in.")
            return

        log_channel = ctx.guild.get_channel_or_thread(config['log_channel'])
        if not log_channel:
            # If that doesn't work, try to find the thread in all the archived threads per channel
            log_channel = await find_and_unarchive_thread(ctx)

            # If after that log_channel is still None, end function
            if not log_channel:
                await utils.safe_send(ctx, "The original log channel can't be found (type `;q setup`)")
                return
        try:
            log_message = await log_channel.fetch_message(config['questions'][index]['log_message'])
        except discord.NotFound:
            await utils.safe_send(ctx, "The original question log message could not be found. Type `;q a <index>` to "
                                    "close the question and clear it.")
            return

        emb: discord.Embed = log_message.embeds[0]
        value_text = f"⁣⁣⁣\n[Jump URL]({ctx.message.jump_url})"
        emb.add_field(name=f"Response by {str(ctx.author)}",
                      value=value_text.replace('⁣⁣⁣', response[:1024 - len(value_text)]))
        await log_message.edit(embed=emb)
        config['questions'][index].setdefault('responses', []).append(ctx.message.jump_url)
        await self._delete_log(ctx)
        await self._post_log(ctx)
        await ctx.message.add_reaction('✅')

    async def _delete_log(self, ctx):
        """Internal command for deleting the last message in log channel if it is `;q list` result"""
        if isinstance(ctx.channel, discord.Thread):
            question_channel = ctx.channel.parent
        else:
            question_channel = ctx.channel

        try:
            config = self.bot.db['questions'][str(ctx.guild.id)][str(question_channel.id)]
        except KeyError:
            return

        log_channel = ctx.guild.get_channel_or_thread(config['log_channel'])

        if not log_channel:
            log_channel = await find_and_unarchive_thread(ctx)

        if not log_channel:
            await utils.safe_send(ctx, "The original log channel was not found. Please run `;q setup`.")
            return
        try:
            last_message = None
            async for msg in log_channel.history(limit=5).filter(lambda m: m.author == m.guild.me and m.embeds):
                last_message = msg
                break
            if last_message.embeds[0].title.startswith('⁣List⁣'):
                try:
                    await last_message.delete()  # replace the last message in the channel (it should be a log)
                except discord.NotFound:
                    pass
        except (TypeError, AttributeError, discord.Forbidden):
            return

    async def _post_log(self, ctx):
        """Internal command for updating the list at the bottom of question log channels"""
        if isinstance(ctx.channel, discord.Thread):
            question_channel = ctx.channel.parent
        else:
            question_channel = ctx.channel

        try:
            config = self.bot.db['questions'][str(ctx.guild.id)][str(question_channel.id)]
        except KeyError:
            return

        log_channel = ctx.guild.get_channel_or_thread(config['log_channel'])

        # If the channel/thread isn't found, check archived threads
        if not log_channel:
            log_channel = await find_and_unarchive_thread(ctx)

        # If still no log_channel found after searching archived threads...
        if not log_channel:
            await utils.safe_send(ctx, "The original log channel was not found. Please run `;q setup`.")
            return

        await ctx.invoke(self.question_list, log_channel)

    # ###################################################
    #
    # Commands for Japanese questions channel
    #
    # #####################################################

    @commands.command(aliases=['tk', 'taekim', 'gram', 'g'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @commands.cooldown(1, 5, type=commands.BucketType.user)
    async def grammar(self, ctx, *, search_term=None):
        """Searches for grammar articles.  Use: `;grammar <search term>`.  To specify a certain website, put
        it in the beginning of your search term from one of the following options:
        `[taekim-complete, taekim-grammar, taekim, maggie, japanesetest4you, imabi, jlptsensei, ejlx]`. \n
        Aliases = `[tk, t, taekim, gram, g, imabi]`"""
        if not search_term:
            await utils.safe_send(ctx, ctx.command.help)
            return

        # ### Check if you specify a certain site ###
        sites = {'taekim-grammar': 'www.guidetojapanese.org/learn/grammar/',
                 'taekim-complete': 'www.guidetojapanese.org/learn/complete/',
                 'taekim': "www.guidetojapanese.org/learn/grammar/",
                 'maggie': 'maggiesensei.com/',
                 'japanesetest4you': 'https://japanesetest4you.com/',
                 'imabi': 'https://www.imabi.net/',
                 'jlptsensei': 'https://jlptsensei.com/',
                 'ejlx': 'https://ejlx.blogspot.com/',
                 'se': 'https://japanese.stackexchange.com/'}
        space_split = search_term.split()
        if space_split[0] in sites:
            site = sites[space_split[0]]
            search_term = ' '.join(space_split[1:])
        else:
            site = None
        if not search_term:
            await utils.safe_send(ctx, "Please enter a search term. Check the help for this command")
            return

        # ### Call the search ###
        engine_id = '013657184909367434363:djogpwlkrc0'
        with open(f'{dir_path}/gcse_api.txt', 'r') as read_file:
            url = f'https://www.googleapis.com/customsearch/v1' \
                  f'?q={search_term}' \
                  f'&cx={engine_id}' \
                  f'&key={read_file.read()}'
        if site:
            url += f"&siteSearch={site}"

        data = await utils.aiohttp_get(ctx, url)

        jr = json.loads(data)
        if 'items' in jr:
            results = jr['items']
        else:
            await utils.safe_send(ctx, embed=utils.red_embed("No results found."))
            return
        search_term = jr['queries']['request'][0]['searchTerms']

        def format_title(title, url):
            if url.startswith('https://japanesetest4you.com/'):
                try:
                    return title.split(' Grammar: ')[1].split(' – Japanesetest4you.com')[0]
                except IndexError:
                    return title
            if url.startswith('http://maggiesensei.com/'):
                return title.split(' – Maggie Sensei')[0]
            if url.startswith('https://www.imabi.net/'):
                return title
            if url.startswith('http://www.guidetojapanese.org/learn/grammar/'):
                return title.split(' – Learn Japanese')[0]
            if url.startswith('http://www.guidetojapanese.org/learn/complete/'):
                return title
            if url.startswith('https://jlptsensei.com/'):
                if " Grammar: " in title:
                    return ''.join(title.split(' Grammar: ')[1:]).split(' - Learn Japanese')[0]
                else:
                    return title
            return title

        def format_url(url):
            if url.startswith('https://japanesetest4you.com/'):
                return f"[Japanesetest4you]({url})"
            if url.startswith('http://maggiesensei.com/'):
                return f"[Maggie Sensei]({url})"
            if url.startswith('https://www.imabi.net/'):
                return f"[Imabi]({url})"
            if url.startswith('http://www.guidetojapanese.org/learn/grammar/'):
                return f"[Tae Kim Grammar Guide]({url})"
            if url.startswith('http://www.guidetojapanese.org/learn/complete/'):
                return f"[Tae Kim Complete Guide]({url})"
            if url.startswith('https://jlptsensei.com/'):
                return f"[JLPT Sensei]({url})"
            return url

        def make_embed(page):
            search_url = f"https://cse.google.com/cse?cx=013657184909367434363:djogpwlkrc0" \
                         f"&q={search_term.replace(' ', '%20').replace('　', '%E3%80%80')}"
            emb = utils.green_embed(f"Search for {search_term} ー [(see full results)]({search_url})")
            for result in results[page * 3:(page + 1) * 3]:
                title = result['title']
                url = result['link']
                snippet = result['snippet'].replace('\n', '')
                if ' ... ' in snippet:
                    snippet = snippet.split(' ... ')[1]
                for word in search_term.split():
                    final_snippet = ''
                    for snippet_word in snippet.split():
                        if not snippet_word.startswith('**') and word in snippet_word:
                            final_snippet += f"**{snippet_word}** "
                        else:
                            final_snippet += f"{snippet_word} "
                    snippet = final_snippet
                emb.description += f"\n\n**{format_title(title, url)}**\n{format_url(url)}\n{snippet}"
            return emb

        page = 0
        msg = await utils.safe_send(ctx, embed=make_embed(0))
        await msg.add_reaction('⬅')
        await msg.add_reaction('➡')

        def check(reaction, user):
            if ((str(reaction.emoji) == '⬅' and page != 0) or
                (str(reaction.emoji) == '➡' and page != len(results) // 3)) and user == ctx.author and \
                    reaction.message.id == msg.id:
                return True

        while True:
            try:
                reaction, user = await ctx.bot.wait_for('reaction_add', timeout=30.0, check=check)
            except asyncio.TimeoutError:
                try:
                    await msg.clear_reactions()
                except (discord.Forbidden, discord.NotFound):
                    pass
                return

            if str(reaction.emoji) == '⬅':
                page -= 1
            if str(reaction.emoji) == '➡':
                page += 1
            await msg.edit(embed=make_embed(page))
            try:
                await reaction.remove(user)
            except discord.Forbidden:
                pass

    @commands.command(aliases=['se'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @commands.cooldown(1, 5, type=commands.BucketType.user)
    async def stackexchange(self, ctx, *, search_term=None):
        """Searches stackexchange.  Use: `;se <search term>`."""
        if not search_term:
            await utils.safe_send(ctx, ctx.command.help)
            return

        # ### Call the search ###
        engine_id = 'ddde7b27ce4758ac8'
        with open(f'{dir_path}/gcse_api.txt', 'r') as read_file:
            url = f'https://www.googleapis.com/customsearch/v1' \
                  f'?q={search_term}' \
                  f'&cx={engine_id}' \
                  f'&key={read_file.read()}'

        data = await utils.aiohttp_get(ctx, url)

        jr = json.loads(data)
        if 'items' in jr:
            results = jr['items']
        else:
            await utils.safe_send(ctx, embed=utils.red_embed("No results found."))
            return
        search_term = jr['queries']['request'][0]['searchTerms']

        def make_embed(page):
            emb = utils.green_embed(f"Search for {search_term} ー [(See full results)](https://cse.google.com/cse?cx="
                                 f"ddde7b27ce4758ac8&q={search_term.replace(' ', '%20').replace('　', '%E3%80%80')})")
            for result in results[page * 3:(page + 1) * 3]:
                title = result['title']
                url = result['link']
                snippet = result['snippet'].replace('\n', '')
                if ' ... ' in snippet:
                    snippet = snippet.split(' ... ')[1]
                for word in search_term.split():
                    snippet = snippet.replace(word, f"**{word}**")
                    # final_snippet = ''
                    # for snippet_word in snippet.split():
                    #     if not snippet_word.startswith('**') and word in snippet_word:
                    #         final_snippet += f"**{snippet_word}** "
                    #     else:
                    #         final_snippet += f"{snippet_word} "
                    # snippet = final_snippet
                emb.description += f"\n\n**[{title}]({url})**\n{snippet}"
            return emb

        page = 0
        msg = await utils.safe_send(ctx, embed=make_embed(0))
        await msg.add_reaction('⬅')
        await msg.add_reaction('➡')

        def check(reaction, user):
            if ((str(reaction.emoji) == '⬅' and page != 0) or
                (str(reaction.emoji) == '➡' and page != len(results) // 3)) and user == ctx.author and \
                    reaction.message.id == msg.id:
                return True

        while True:
            try:
                reaction, user = await ctx.bot.wait_for('reaction_add', timeout=30.0, check=check)
            except asyncio.TimeoutError:
                try:
                    await msg.clear_reactions()
                except (discord.Forbidden, discord.NotFound):
                    pass
                return

            if str(reaction.emoji) == '⬅':
                page -= 1
            if str(reaction.emoji) == '➡':
                page += 1
            await msg.edit(embed=make_embed(page))
            try:
                await reaction.remove(user)
            except discord.Forbidden:
                pass

    @staticmethod
    async def get_number_google_results(ctx, site, engine_id, search_term) -> str:
        """
        Returns number of Google results for a search term.
        site: Can limit search results to a certain site. Input URL like https://twitter.com
        """
        with open(f'{dir_path}/gcse_api.txt', 'r') as read_file:
            url = f'https://www.googleapis.com/customsearch/v1' \
                  f'?exactTerms={search_term}' \
                  f'&key={read_file.read()}' \
                  f'&cx={engine_id}'  # %22 is quotation mark
            if site:
                url += f"&siteSearch={site}"

        data = await utils.aiohttp_get(ctx, url)

        num_of_results = data.split('"formattedTotalResults": "')[1].split('"')[0]
        try:
            return num_of_results
        except ValueError:
            return "0"

    @commands.command(aliases=['sc'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @commands.cooldown(1, 5, type=commands.BucketType.user)
    async def searchcompare(self, ctx, *search_terms):
        """Compares the number of exact results from different exact searches.

        Usage: `;sc <term1> <term2> ...`. Use quotation marks to input a term with multiple words.

        Examples: `;sc おはよう おはよー`   `;sc こんにちは こんにちわ こにちわ`

        Prefix the terms with one `site:<site>` to limit the search to one site in the google.jp portion.
        Example: `;sc site:twitter.com ワロタ 笑`

        News sites index from top ten news sites in Japan:
        `news24`, `nhk`, `rocketnews24`, `asahi`, `jiji`,
        `nikkei`, `oricon`, `sankei`, `yomiuri`, `news.yahoo.co.jp`"""
        if not search_terms:
            await utils.safe_send(ctx, ctx.command.help)
            return
        if len(search_terms) > 5:
            await utils.safe_send(ctx, "Please input less terms. You'll kill my bot!!")
            return

        if search_terms[0].startswith('site:'):
            site = re.search("site: ?(.*)", search_terms[0]).group(1)
            search_terms = search_terms[1:]
        else:
            site = None

        # ### Call the search ###
        results = {}
        s = ''
        for search_term in search_terms:
            s += f"__{search_term}__\n"

            # Normal google results
            engine_id = 'c7afcd4ef85db31a2'
            num_of_google_results = await self.get_number_google_results(ctx, site, engine_id, search_term) or "0"
            url = f'https://cse.google.com/cse?cx=c7afcd4ef85db31a2#gsc.tab=0&gsc.q=%22{quote(search_term)}%22'  # %22 --> "
            if site:
                url += f"%20site:{site}"
            s += f"[google.jp]({url}): 約{num_of_google_results}件\n"

            # News sites
            engine_id = 'cbbca2d78e3d9fb2d'
            num_of_news_results = await self.get_number_google_results(ctx, site, engine_id, search_term) or "0"
            url = f"https://cse.google.com/cse?cx=cbbca2d78e3d9fb2d#gsc.tab=0&gsc.q=%22{quote(search_term)}%22"
            s += f"[News sites]({url}): 約{num_of_news_results}件\n"

            # Massif
            massif_result = await self.get_massif_results(ctx, search_term)
            num_of_massif_results: str = massif_result['hits'] or 0
            num_of_massif_results = f"{num_of_massif_results:,}"
            if massif_result['hits_limited']:
                num_of_massif_results += "+"
            url = f"https://massif.la/ja/search?q={quote(search_term)}"
            s += f"[Massif]({url}): {num_of_massif_results}\n"

            # Yourei
            yourei_result = await self.get_yourei_results(ctx, search_term)
            if yourei_result:
                num_yourei_results = getattr(yourei_result.find(id="num-examples"), "text", "0")
            else:
                num_yourei_results = "Unavailable"
            url = f"https://yourei.jp/{quote(search_term)}"
            s += f"[Yourei]({url}): {num_yourei_results}\n"

            s += "\n"  # Split different search terms

        await utils.safe_send(ctx, embed=discord.Embed(title="Search comparison results", description=s, color=0x0C8DF0))

    @commands.command()
    @commands.bot_has_permissions(send_messages=True)
    async def jisho(self, ctx, *, text):
        """Provides a link to a Jisho search"""
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass
        pretty_url = "https://jisho.org/search/" + text.replace(" ", "%20").replace("　", "%E3%80%80")
        await utils.safe_send(ctx, f"Try finding the meaning to the word you're looking for here: "
                                f"{pretty_url}")

    @commands.command(aliases=['diff'])
    async def difference(self, ctx, *, query):
        """Pastes a text which links to how to find the difference between two words for language learning"""
        if not query:
            query = "X Y"
        urlquery = '+'.join(query.split())
        emb = utils.green_embed(f"A lot of 'what is the difference between X and Y' kinds of questions can be answered "
                             f"by typing something like the following into google (click the links to see the "
                             f"search results):\n\n"
                             f"['Japanese {query} difference']"
                             f"(https://www.google.com/search?q=japanese+{urlquery}+difference)\n"
                             f"['{query} difference']"
                             f"(https://www.google.com/search?q={urlquery}+difference)\n"
                             f"['{query} 違い']"
                             f"(https://www.google.com/search?q={urlquery}+違い)\n"
                             )
        await utils.safe_send(ctx, embed=emb)

    @commands.command()
    @commands.check(lambda ctx: ctx.guild.id != 116379774825267202)
    async def neko(self, ctx, *search):
        """Search the grammar database at itazuraneko. Use: `;neko <search term>`. Optionally, add a tag at the end
        to specify which grammar dictionary you want to search (options: `-basic`, `-intermediate`, `-advanced`,
        `-handbook`, `-donnatoki`).
        """

        if not search:
            await utils.safe_send(ctx, "You have to input a search term!")
            return

        dictionaries: dict[str: str] = {"dojg/dojgpages/basic": "A Dictionary of Basic Japanese Grammar",
                                        "basic": "A Dictionary of Basic Japanese Grammar",
                                        "dojg/dojgpages/intermediate": "A Dictionary of Intermediate Japanese Grammar",
                                        "intermediate": "A Dictionary of Intermediate Japanese Grammar",
                                        "dojg/dojgpages/advanced": "A Dictionary of Advanced Japanese Grammar",
                                        "advanced": "A Dictionary of Advanced Japanese Grammar",
                                        "https://core6000.neocities.org/hjgp/": "Handbook of Japanese Grammar",
                                        "handbook": "Handbook of Japanese Grammar",
                                        "donnatoki": "どんなときどう使う 日本語表現文型辞典"}

        dict_abbreviations = {"A Dictionary of Basic Japanese Grammar": "DoBJG",
                              "A Dictionary of Intermediate Japanese Grammar": "DoIJG",
                              "A Dictionary of Advanced Japanese Grammar": "DoAJG",
                              "Handbook of Japanese Grammar": "HoJG",
                              "どんなときどう使う 日本語表現文型辞典": "表現文型辞典"}

        # html = await utils.aiohttp_get(ctx, 'https://itazuraneko.neocities.org/grammar/masterreference.html')
        html = await utils.aiohttp_get(ctx, 'https://djtguide.github.io/grammar/masterreference.html')

        soup = BeautifulSoup(html, 'html.parser')

        def fancyfind(tag):
            if tag.name != "a":
                return
            if tag.parent.name != "td":
                return
            return True
            # if tag.contents[0].has_attr("class"):
            # return tag.name == "td" and tag.contents[0]["class"][0] == "underscore"

        results = soup.find_all(fancyfind)

        #  results look like this
        # <td id="basic"><a class="underscore" href="dojg/dojgpages/basicあげる1.html">あげる(1)</a></td>
        # <td><a class="underscore" href="dojg/dojgpages/basicあげる2.html">あげる(2)</a></td>
        # <td><a class="underscore" href="dojg/dojgpages/basic間あいだに.html">間・あいだ(に)</a></td>
        # <td><a class="underscore" href="dojg/dojgpages/basicあまり.html">あまり</a></td>
        # <td><a class="underscore" href="dojg/dojgpages/basicある1.html">ある(1)</a></td>
        # <td><a class="underscore" href="dojg/dojgpages/basicある2.html">ある(2)</a></td>
        # <td><a class="underscore" href="dojg/dojgpages/basicあとで.html">あとで</a></td>
        # <td><a class="underscore" href="dojg/dojgpages/basicば.html">ば</a></td>
        # <td><a class="underscore" href="dojg/dojgpages/basicばかり.html">ばかり</a></td>
        # <td><a class="underscore" href="dojg/dojgpages/basicばよかった.html">ばよかった</a></td>
        # <td><a class="underscore" href="https://core6000.neocities.org/hjgp/entries/3.htm">上がる</a></td>
        # ruby: しろ〈<ruby>命<rt>めい</rt>令<rt>れい</rt></ruby>〉--> しろ〈命めい令れい〉

        entries = []

        def parse_search(text):
            # for c in "()（）":
            #     text = text.replace(c, "")
            # if "〈" in text:
            #     text = re.compile("〈.*〉").sub("", text)
            # for the purpose of matching searches, changes things like が〈前置き・和らげ〉 or が(1) to just が
            text = re.compile(r"(〈.*〉)|(\(\d+\))").sub("", text)
            return text.replace("…", "～").replace("~", "～")

        for i in results:
            url = i["href"]
            dictionary: Optional[str] = None
            for site in dictionaries:
                if site in url:
                    dictionary: str = dictionaries[site]
                    break
            if not url.startswith("https"):
                url: str = "https://djtguide.github.io/grammar/" + url
            grammar = "".join([str(x) for x in i.contents])
            if "<rt>" in grammar:
                grammar = re.compile(r"(<rt>.*?</rt>|</?ruby>)").sub("", grammar)
            search_field = parse_search(grammar)
            entries.append((grammar, dictionary, url, search_field))

        if search[-1][0] == "-":
            dictionary = dictionaries[search[-1][1:].casefold()]
            search = search[:-1]
        else:
            dictionary = None

        exacts = []
        almost = []
        contains = []
        for term in search:
            for entry in entries:  # (grammar name, dictionary name, url, search field)
                if dictionary and entry[1] != dictionary:
                    continue
                term = parse_search(term)
                if term == entry[3]:
                    exacts.append(entry)
                elif len(term) >= 2 and LDist(term, entry[3]) <= len(term) // 3:
                    almost.append(entry)
                elif term in entry[3]:
                    contains.append(entry)

        def min_dist(search_term) -> int:
            search_term = search_term[3]
            distances = []
            for _term in search:
                distances.append(LDist(search_term, _term))

            return min(distances)

        # sort the items in contains list by the distance from the search term
        # the terms closest to the search term will appear first
        contains = sorted(contains, key=min_dist)

        async def wait_for_delete(msg):
            await msg.add_reaction('🗑️')
            try:
                await self.bot.wait_for('reaction_add', timeout=15.0,
                                        check=lambda r, m: str(r.emoji) == '🗑️' and m == ctx.author)
            except asyncio.TimeoutError:
                try:
                    await msg.clear_reactions()
                except (discord.Forbidden, discord.NotFound):
                    pass
                return
            await msg.delete()

            try:
                await ctx.message.delete()
            except discord.Forbidden:
                pass

        if not (exacts or almost or contains):
            msg = await utils.safe_send(ctx, embed=utils.red_embed("I couldn't find any results for your search term."))
            await wait_for_delete(msg)
            return
        emb = discord.Embed(title="Itazuraneko Grammar Search", color=0x00FF00)
        desc = 'These are pulled from [this page](https://djtguide.github.io/grammar/masterreference.html). ' \
               '\nIf you save the link, you can do\nyour own seaches in the future.\n\n'
        index = 1
        # Add in these "middle" elements to mark where in the list there should be dividers added
        total_length = len(exacts + almost + contains)
        for entry in exacts + ['middle'] + almost + ['middle'] + contains:
            if entry == 'middle':
                if desc[-7:] != "～～～～～～\n":
                    desc += "～～～～～～\n"
                continue
            addition = f"{index}) [{entry[0]}]({entry[2]}) ({dict_abbreviations[entry[1]]})\n"
            if len(desc + addition) < 2028:
                desc += addition
                index += 1
            else:
                # index has already been incremented by 1 from previous iteration even if this iteration couldn't fit
                # so i need to subtract 1 from the below calculation
                desc += f"(+ {total_length - (index - 1)} others...)"
                break
        emb.description = desc
        msg = await utils.safe_send(ctx, embed=emb)
        await wait_for_delete(msg)

    @neko.error
    async def neko_error(self, ctx, error):
        # Return error message if check fails
        if isinstance(error, commands.CheckFailure):
            if ctx.guild.id == 116379774825267202:
                await utils.safe_send(ctx, "This command is disabled in this server.")
            else:
                raise error
        else:
            raise error

    @commands.command(aliases=['bp'])
    async def bunpro(self, ctx, search):
        """Search the grammar database at [bunpro](https://bunpro.jp/grammar_points).
        Use: `;bunpro/;bp <search term>`.
        """
        if not search:
            # await utils.safe_send(ctx, "You have to input a search term!")
            return

        # html = await utils.aiohttp_get(ctx, 'https://itazuraneko.neocities.org/grammar/masterreference.html')
        html = await utils.aiohttp_get(ctx, 'https://bunpro.jp/grammar_points')

        soup = BeautifulSoup(html, 'html.parser')
        
        def fancyfind(tag):
            # Check if the tag is a <li> and has the 'js_search-tile_index' class
            if tag.name == 'li' and 'js_search-tile_index' in tag.get('class', []):
                return True
            return False

        results = soup.find_all(fancyfind)
        grammar_points = []
        for result in results:
            link = explanation = jlpt_level = ''

            # get jlpt level
            for class_ in result['class']:
                if class_.startswith('js_search-option_jlptN'):  # Updated to match new class structure
                    jlpt_level = class_[-2:]  # This will extract "N5", "N4", etc.

            # get url link and explanation text
            for content in result.contents:
                if content.name == 'a':
                    link = "https://bunpro.jp/" + content['href']
                    try:
                        explanation = content['title']
                    except KeyError:
                        print(link, content)

            # get japanese_title and english_title
            # bad_split = result.text.split('\n')  # result looks like '\n\n\n\n\nだ\nTo be\n\n\n\n\n\n\n\n'
            # good_split = [i for i in bad_split if i]  # bad_split looks like ['', '', 'だ', 'To be', '', '', '']
            good_split = [i.strip() for i in result.stripped_strings]  # Use stripped_strings to clean up white space
            japanese_title = good_split[0]  # "だ"
            english_title = good_split[1]  # "To be"

            grammar_points.append((japanese_title, english_title, jlpt_level, link, explanation))

        def standardize_formatting(input_text):
            output_text = input_text.replace("＋", "+")
            output_text = output_text.replace("～", "~")
            output_text = output_text.replace("（", "(")
            output_text = output_text.replace("）", ")")
            output_text = output_text.replace("　", " ")
            return output_text

        exacts = []
        almost = []
        contains = []
        formatted_search = standardize_formatting(search)
        print('formatted_search:', formatted_search)
        for entry in grammar_points:  # (japanese_title, english_title, jlpt_level, link, explanation)
            formatted_entry = [standardize_formatting(i) for i in entry]
            if formatted_search in formatted_entry:
                exacts.append(entry)
            else:
                for entry_part in formatted_entry:
                    if len(formatted_search) >= 2 and LDist(formatted_search, entry_part) <= len(formatted_search) // 3:
                        almost.append(entry)
                    elif formatted_search in entry_part:
                        contains.append(entry)

        def min_dist(grammar_point) -> int:
            distances = []
            formatted_entry = [standardize_formatting(i) for i in grammar_point]
            for grammar_part in formatted_entry[:2]:
                distance = LDist(formatted_search, grammar_part)
                distances.append(distance)
                print(distance, grammar_part, formatted_search)

            return min(distances)

        # sort the items in "contains" list by the distance from the search term
        # the terms closest to the search term will appear first
        contains = sorted(contains, key=min_dist)

        async def wait_for_delete(msg):
            await msg.add_reaction('🗑️')
            try:
                await self.bot.wait_for('reaction_add', timeout=15.0,
                                        check=lambda r, m: str(r.emoji) == '🗑️' and m == ctx.author)
            except asyncio.TimeoutError:
                try:
                    await msg.clear_reactions()
                except (discord.Forbidden, discord.NotFound):
                    pass
                return
            await msg.delete()

            try:
                await ctx.message.delete()
            except discord.Forbidden:
                pass

        if not (exacts or almost or contains):
            msg = await utils.safe_send(ctx, embed=utils.red_embed("I couldn't find any results for your search term."))
            await wait_for_delete(msg)
            return
        emb = discord.Embed(title="Bunpro Grammar Search", color=0x00FF00)
        desc = 'These are pulled from [this page](https://bunpro.jp/grammar_points). ' \
               'If you save the link, \nyou can do your own seaches in the future.\n\n'
        index = 1
        # Add in these "middle" elements to mark where in the list there should be dividers added
        total_length = len(exacts + almost + contains)
        # noinspection PyTypeChecker
        # above noinspection setting is because pycharm isn't happy putting ['middle'] into ['a', 'b', ...]
        list_with_middles = exacts + ['middle'] + almost + ['middle'] + contains
        for entry in list_with_middles:
            # entry = (japanese_title, english_title, jlpt_level, link, explanation)
            if entry == 'middle':
                if desc[-7:] != "～～～～～～\n":
                    desc += "～～～～～～\n"
                continue
            link_text = f"{entry[0]} - {entry[1]}"[:40]
            addition = f"{index}) [{link_text}]({entry[3]}) ({entry[2]})\n"
            if len(desc + addition) < 2028:
                desc += addition
                index += 1
            else:
                # index has already been incremented by 1 from previous iteration even if this iteration couldn't fit
                # so I need to subtract 1 from the below calculation
                desc += f"(+ {total_length - (index - 1)} others...)"
                break
        emb.description = desc
        msg = await utils.safe_send(ctx, embed=emb)
        await wait_for_delete(msg)

    async def get_massif_results(self, ctx, search_term):
        url_quoted_search_term = quote(search_term)
        url = f"https://massif.la/ja/search?q={url_quoted_search_term}&fmt=json"

        text = await utils.aiohttp_get(ctx, url)
        if not text:
            await utils.safe_send(ctx, embed=utils.red_embed("No results found."))
            return

        jr = json.loads(text)
        return jr

    @commands.command()
    async def massif(self, ctx, *, search_term):
        """Performs a search on the massif database. Note most of the sentences
        here are from amateur writers, so they may be unnatural. In addition,
        they are all from web novels, so the language may be more dramatic
        or exaggerated than actual real-life Japanese.
        
        __Try searching for:__
        words: もちろん　セミ　光景　あくまで　揃う　痙攣
        phrases: 写真を撮る　表情を浮かべる　蛇口をひねる
        multiple in the same sentence: 冒険者 戦う　過去 時間
        exact text: 'あろう'　'以'　'留まる'"""
        url_quoted_search_term = quote(search_term)
        url = f"https://massif.la/ja/search?q={url_quoted_search_term}&fmt=json"

        jr = await self.get_massif_results(ctx, search_term)
        if not jr:
            return

        # Sample JSON data:
        # {
        #   "hits": 4898,
        #   "hits_limited": false,
        #
        #   "results": [
        #     {
        #       "highlighted_html": "あっという間に<em>テスト</em>は終わり、放課後になった。",
        #       "sample_source": {
        #         "publish_date": "2018-02-21",
        #         "title": "99回告白したけどダメでした - 101話",
        #         "url": "https://ncode.syosetu.com/n5829ej/103/"
        #       },
        #       "source_count": 1,
        #       "text": "あっという間にテストは終わり、放課後になった。"
        #     },
        #     ..., ..., ...,
        #     ]

        hits: int = jr['hits']  # number of results
        hits_limited: bool = jr['hits_limited']  # if number of results was 10,000+
        results: list[dict] = jr['results']
        # result['highlighted_html']: text with key-word bolded with <em> ... </em>
        # result['text']: raw text
        # result['source_count']: usually 1? idk what this is
        # result['sample_source']['publish_date']: string of date published like 2018-02-21
        # result['sample_source']['title']: title of source
        # result['sample_source']['url']: url of source page

        if not hits:
            await utils.safe_send(ctx, embed=utils.red_embed("No results found."))
            return

        emb = discord.Embed(title="Massif search results", url=url.replace("&fmt=json", ""))
        emb.description = f"__First {min(10, hits)} of {'>' if hits_limited else ''}{hits} unique matching" \
                          f" sentences__\n(see full results by clicking the above link)\n\n"
        emb.colour = 0x0099CC

        index = 1
        for result in results[:10]:
            text = result['highlighted_html']
            text = text.replace("</em><em>", "").replace("<em>", "**__").replace("</em>", "__**")
            index_text = f"[`[ {index} ]`]({result['sample_source']['url']}) "
            emb.description += index_text + text + '\n'
            index += 1

        await utils.safe_send(ctx, embed=emb)

    async def get_yourei_results(self, ctx, search_term) -> Optional[BeautifulSoup]:
        url_quoted_search_term = quote(search_term)
        url = f"https://yourei.jp/{url_quoted_search_term}"

        text = await utils.aiohttp_get(ctx, url)
        if not text:
            return

        soup = BeautifulSoup(text, 'html.parser')

        return soup

    @commands.command()
    async def yourei(self, ctx, *, search_term):
        """Searches the [yourei.jp](https://yourei.jp) database for example sentences.

        Note that yourei only supports searching of words it specifically has in its dictionary
        rather than for general phrases. Therefore, zero results for a phrase usually means
        it's not in its dictionary rather than it's not common Japanese.

        For example, searching 「寿司を食べる」 returns zero results even though the
        phrase probably appears many times in literature."""
        url_quoted_search_term = quote(search_term)
        url = f"https://yourei.jp/{url_quoted_search_term}"

        soup = await self.get_yourei_results(ctx, search_term)
        if not soup:
            return  # sending error information to user should have been handled in above function

        try:
            results = soup.find_all("li", "sentence")  # list of sentence tag objects (get text using result.text)
        except IndexError:
            await utils.safe_send(ctx, "It's possible the HTML structure of the yourei.jp site has changed. I received "
                                    "a response with data from the site but the list of sentences were not where I "
                                    f"expected. Try checking the site yourself: {url}")
            return

        num_examples = soup.find(id="num-examples")
        if num_examples:
            num_examples = num_examples.text  # a string like "13,381", need to remove the comma
        else:
            num_examples = '0'
        num_examples = int(num_examples.replace(',', ''))  # an int 13381

        if not num_examples:
            await utils.safe_send(ctx, embed=utils.red_embed("Your search returned no results. Note, this probably means "
                                                       "your word or phrase wasn't in yourei's (limited) database "
                                                       "rather than it never appearing in literature. The database "
                                                       "focuses mainly on single words or very short phrases."))
            return

        # results now should be a list of sentence tags, bs4.element.Tag

        emb = discord.Embed(title="Yourei.jp search results", url=url)
        emb.description = f"__First {min(7, num_examples)} of {num_examples} 例文__" \
                          f"\n(see full results by clicking the above link)\n\n"
        emb.colour = 0x0099CC

        index = 1
        for result in results[:8]:
            text = (result.find(class_="the-sentence") or result).text  # either the main sentence or just full result
            text = (text.split() or [''])[0]  # remove \n characters
            text = text.replace(search_term, f"**__{search_term}__**").replace("__****__", "")
            if not text:
                continue
            source_link_class = result.find(class_="sentence-source-title")
            if hasattr(source_link_class, 'a'):
                source_link = source_link_class.a.attrs['href']
                source_title = source_link_class.text
                index_text = f"[`[ {index} ] {source_title}`]({source_link})\n"
            else:
                index_text = f"`[ {index} ]`\n"

            emb.description += index_text + text + '\n'
            index += 1

        await utils.safe_send(ctx, embed=emb)


async def setup(bot):
    await bot.add_cog(Questions(bot))
