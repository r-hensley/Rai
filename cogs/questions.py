import discord
from discord.ext import commands
from .utils import helper_functions as hf
import asyncio
import requests
import json
from datetime import datetime, date

import os
dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


class Questions(commands.Cog):
    """Help"""

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        if ctx.guild:
            return True

    @commands.command(aliases=['tk', 't', 'taekim', 'gram', 'g'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @commands.cooldown(1, 5, type=commands.BucketType.user)
    async def grammar(self, ctx, *, search_term=None):
        """Searches for grammar articles.  Use: `;grammar <search term>`.  To specify a certain website, put
        it in the beginning of your search term from one of the following options:
        `[taekim-complete, taekim-grammar, taekim, maggie, japanesetest4you, imabi, jlptsensei, ejlx]`. \n
        Aliases = `[tk, t, taekim, gram, g, imabi]`"""
        if not search_term:
            await hf.safe_send(ctx, ctx.command.help)
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

        # ### Call the search ###
        engine_id = '013657184909367434363:djogpwlkrc0'
        with open(f'{dir_path}/gcse_api.txt', 'r') as read_file:
            url = f'https://www.googleapis.com/customsearch/v1' \
                  f'?q={search_term}' \
                  f'&cx={engine_id}' \
                  f'&key={read_file.read()}'
        if site:
            url += f"&siteSearch={site}"
        response = requests.get(url)
        if response.status_code != 200:
            await hf.safe_send(ctx, embed=hf.red_embed(f"Error {response.status_code}: {response.reason}"))
            return
        jr = json.loads(response.content)
        if 'items' in jr:
            results = jr['items']
        else:
            await hf.safe_send(ctx, embed=hf.red_embed("No results found."))
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
            emb = hf.green_embed(f"Search for {search_term}")
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
        msg = await hf.safe_send(ctx, embed=make_embed(0))
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
            await reaction.remove(user)

    @commands.command()
    @commands.bot_has_permissions(send_messages=True)
    async def jisho(self, ctx, *, text):
        """Provides a link to a Jisho search"""
        await ctx.message.delete()
        await hf.safe_send(ctx,
                           f"Try finding the meaning to the word you're looking for here: https://jisho.org/search/{text}")

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
            try:
                await hf.safe_send(ctx,
                                   f"This channel is not setup as a questions channel.  Run `;question setup` in the "
                                   f"questions channel to start setup.")
            except discord.Forbidden:
                await hf.safe_send(ctx.author, "Rai lacks permissions to send messages in that channel")
                return
            return
        if not title:
            title = target_message.content
        # for channel in self.bot.db['questions'][str(ctx.guild.id)]:
        # for question in self.bot.db['questions'][str(ctx.guild.id)][channel]:
        # question = self.bot.db['questions'][str(ctx.guild.id)][channel][question]
        # if (datetime.today() - datetime.strptime(question['date'], "%Y/%m/%d")).days >= 3:
        # log_channel = self.bot.get_channel(self.bot.db['questions']['channel']['log_channel'])
        # await hf.safe_send(log_channel, f"Closed question for being older than three days and unanswered")

        question_number = 1
        while str(question_number) in config['questions']:
            question_number += 1
        if question_number > 9:
            await hf.safe_send(ctx, f"Note, I've reached the maximum amount of open questions for reactions.  Try "
                                    f"running `;q list` and clearing out some old questions.")
        config['questions'][str(question_number)] = {}
        config['questions'][str(question_number)]['title'] = title
        config['questions'][str(question_number)]['question_message'] = target_message.id
        config['questions'][str(question_number)]['author'] = target_message.author.id
        config['questions'][str(question_number)]['command_caller'] = ctx.author.id
        config['questions'][str(question_number)]['date'] = date.today().strftime("%Y/%m/%d")

        log_channel = self.bot.get_channel(config['log_channel'])
        color = self.get_color_from_name(ctx)  # returns a RGB tuple unique to every username
        emb = discord.Embed(title=f"Question number: `{question_number}`",
                            description=f"Asked by {target_message.author.mention} ({target_message.author.name}) "
                                        f"in {target_message.channel.mention}",
                            color=discord.Color(color),
                            timestamp=datetime.utcnow())
        if len(f"{title}\n") > (1024 - len(target_message.jump_url)):
            emb.add_field(name=f"Question:", value=f"{title}"[:1024])
            if title[1024:]:
                emb.add_field(name=f"Question (cont.):", value=f"{title[1024:]}\n")
            emb.add_field(name=f"Jump Link to Question:", value=target_message.jump_url)
        else:
            emb.add_field(name=f"Question:", value=f"{title}\n{target_message.jump_url}")
        if ctx.author != target_message.author:
            emb.set_footer(text=f"Question added by {ctx.author.name}")
        try:
            log_message = await hf.safe_send(log_channel, embed=emb)
        except discord.errors.HTTPException as err:
            if err.status == 400:
                await hf.safe_send(ctx, "The question was too long")
            elif err.status == 403:
                await hf.safe_send(ctx, "I didn't have permissions to post in that channel")
            del (config['questions'][str(question_number)])
            return
        config['questions'][str(question_number)]['log_message'] = log_message.id
        number_map = {'1': '1\u20e3', '2': '2\u20e3', '3': '3\u20e3', '4': '4\u20e3', '5': '5\u20e3',
                      '6': '6\u20e3', '7': '7\u20e3', '8': '8\u20e3', '9': '9\u20e3'}
        if question_number < 10:
            try:
                await target_message.add_reaction(number_map[str(question_number)])
            except discord.errors.Forbidden:
                await hf.safe_send(ctx, f"I lack the ability to add reactions, please give me this permission")
            except discord.NotFound:
                await hf.safe_send(ctx, "I can't find the question message.")
                await ctx.invoke(self.answer, args=str(question_number))
                return

        if target_message.author != ctx.author:
            msg_text = f"Hello, someone has marked one of your questions using my questions log feature.  It is now " \
                       f"logged in <#{config['log_channel']}>.  This will" \
                       f" help make sure you receive an answer.  When someone answers your question, please type " \
                       f"`;q a` to mark the question as answered.  Thanks!"
            try:
                await hf.safe_send(target_message.author, msg_text)
            except discord.Forbidden:
                pass

    @commands.group(invoke_without_command=True, aliases=['q'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def question(self, ctx, *, args=None):
        """A module for asking questions, put the title of your quesiton like `;question <title>`"""
        if not args:
            msg = f"Type `;q <question text>` to make a question, or do `;help q`. For now, here's the questions list:"
            await hf.safe_send(ctx, msg)
            await ctx.invoke(self.question_list)
            return
        args = args.split(' ')

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
            msg = await hf.safe_send(ctx, "This will reset the questions database for this channel.  "
                                          "Do you wish to continue?  Type `y` to continue.")
            try:
                await self.bot.wait_for('message', timeout=15.0, check=lambda m: m.content == 'y' and
                                                                                 m.author == ctx.author)
            except asyncio.TimeoutError:
                await msg.edit(content="Canceled...", delete_after=10.0)
                return
        msg_1 = await hf.safe_send(ctx,
                                   f"Questions channel set as {ctx.channel.mention}.  In the way I just linked this "
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
            await hf.safe_send(ctx, f"Invalid channel specified.  Please start over and specify a link to a channel "
                                    f"(should highlight blue)")
            return
        config[str(ctx.channel.id)] = {'questions': {},
                                       'log_channel': log_channel_id}
        await hf.safe_send(ctx,
                           f"Set the log channel as {log_channel.mention}.  Setup complete.  Try starting your first "
                           f"question with `;question <title>` in this channel.")

    @question.command(aliases=['a'])
    async def answer(self, ctx, *, args=''):
        """Marks a question as answered, format: `;q a <question_id 0-9> [answer_id]`
        and has an optional answer_id field for if you wish to specify an answer message"""
        try:
            config = self.bot.db['questions'][str(ctx.guild.id)][str(ctx.channel.id)]
        except KeyError:
            await hf.safe_send(ctx,
                               f"This channel is not setup as a questions channel.  Please make sure you mark your "
                               f"question as 'answered' in the channel you asked it in.")
            return
        except AttributeError: # NoneType object has no attribute 'id' (used in a DM)
            return
        questions = config['questions']
        args = args.split(' ')

        async def self_answer_shortcut():
            for question_number in questions:
                if ctx.author.id == questions[question_number]['author']:
                    return int(question_number)
            await hf.safe_send(ctx, f"Only the asker of the question can omit stating the question ID.  You "
                                    f"must specify which question  you're trying to answer: `;q a <question id>`.  "
                                    f"For example, `;q a 3`.")
            return

        answer_message = answer_text = answer_id = None
        if args == ['']:  # if a user just inputs ;q a
            number = await self_answer_shortcut()
            answer_message = ctx.message
            answer_text = ''
            if not number:
                await hf.safe_send(ctx, f"Please enter the number of the question you wish to answer, like `;q a 3`.")
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
                        await hf.safe_send(ctx, f"I thought `{single_arg}` was a message ID but I couldn't find that "
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
                await hf.safe_send(ctx,
                                   f"A corresponding message to the specified ID was not found.  `;q a <question_id> "
                                   f"<message id>`")
                return

        try:
            number = str(number)
            question = questions[number]
        except KeyError:
            await hf.safe_send(ctx,
                               f"Invalid question number.  Check the log channel again and input a single number like "
                               f"`;question answer 3`.  Also, make sure you're answering in the right channel.")
            return
        except Exception:
            await hf.safe_send(ctx, f"You've done *something* wrong... (´・ω・`)")
            raise

        try:
            log_channel = self.bot.get_channel(config['log_channel'])
            log_message = await log_channel.fetch_message(question['log_message'])
        except discord.errors.NotFound:
            log_message = None
            await hf.safe_send(ctx, f"Message in log channel not found.  Continuing code.")

        try:
            question_message = await ctx.channel.fetch_message(question['question_message'])
            if ctx.author.id not in [question_message.author.id, question['command_caller']] \
                    and not hf.submod_check(ctx):
                await hf.safe_send(ctx, f"Only mods or the person who asked/started the question "
                                        f"originally can mark it as answered.")
                return
        except discord.errors.NotFound:
            if log_message:
                await log_message.delete()
            del questions[number]
            msg = await hf.safe_send(ctx, f"Original question message not found.  Closing question")
            await asyncio.sleep(5)
            await msg.delete()
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
                          value=answer_text + '\n' + answer_message.jump_url)
            await log_message.edit(embed=emb)

        try:
            question_message = await ctx.channel.fetch_message(question['question_message'])
            for reaction in question_message.reactions:
                if reaction.me:
                    try:
                        await question_message.remove_reaction(reaction.emoji, self.bot.user)
                    except discord.errors.Forbidden:
                        await hf.safe_send(ctx, f"I lack the ability to add reactions, please give me this permission")
        except discord.errors.NotFound:
            msg = await hf.safe_send(ctx, "That question was deleted")
            await log_message.delete()
            await asyncio.sleep(5)
            await msg.delete()
            await ctx.message.delete()

        try:
            del (config['questions'][number])
        except KeyError:
            pass
        if ctx.message:
            try:
                await ctx.message.add_reaction('\u2705')
            except discord.errors.Forbidden:
                await hf.safe_send(ctx, f"I lack the ability to add reactions, please give me this permission")
            except discord.NotFound:
                pass

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
            await hf.safe_send(ctx, f"Specified log message not found")
            return
        emb = log_message.embeds[0]
        if emb.title == 'ANSWERED':
            emb.description = emb.description.split('\n')[0]
            try:
                question_message = await ctx.channel.fetch_message(int(emb.fields[0].value.split('/')[-1]))
            except discord.errors.NotFound:
                await hf.safe_send(ctx, f"The message for the original question was not found")
                return
            await self.add_question(ctx, question_message, question_message.content)
        else:
            new_log_message = await hf.safe_send(log_channel, embed=emb)
            question['log_message'] = new_log_message.id
        await log_message.delete()

    @question.command(name='list')
    async def question_list(self, ctx):
        """Shows a list of currently open questions"""
        try:
            config = self.bot.db['questions'][str(ctx.guild.id)]
        except KeyError:
            await hf.safe_send(ctx, f"There are no questions channels on this server.  Run `;question setup` in the "
                                    f"questions channel to start setup.")
            return
        emb = discord.Embed(title=f"List of open questions:")
        if str(ctx.channel.id) in config:
            log_channel_id = config[str(ctx.channel.id)]['log_channel']
        elif str(ctx.guild.id) in config:
            log_channel_id = config[str(ctx.guild.id)]['log_channel']
        else:
            log_channel_id = '0'  # use all channels
        for channel in config:
            if config[channel]['log_channel'] != log_channel_id and log_channel_id != 0:
                continue
            channel_config = config[str(channel)]['questions']
            for question in channel_config.copy():
                try:
                    question_channel = self.bot.get_channel(int(channel))
                    question_message = await question_channel.fetch_message(
                        channel_config[question]['question_message'])
                    question_text = ' '.join(question_message.content.split(' '))
                    text_splice = 1020 - len(question_message.jump_url) - \
                                  len(f"By {question_message.author.mention} in {question_message.channel.mention}\n\n")
                    value_text = f"By {question_message.author.mention} in {question_message.channel.mention}\n" \
                                 f"{question_text[:text_splice]}\n" \
                                 f"{question_message.jump_url}"
                    emb.add_field(name=f"Question `{question}`",
                                  value=value_text)
                except discord.errors.NotFound:
                    emb.add_field(name=f"Question `{question}`",
                                  value="original message not found")
        await hf.safe_send(ctx, embed=emb)

    @question.command()
    @hf.is_admin()
    async def edit(self, ctx, log_id, target, *text):
        """Edit either the asker, answerer, question, title, or answer of a question log in the log channel

        Usage: `;q edit <log_id> <asker|answerer|question|title|answer> <new data>`.  Example: `;q edit 2 \
        question  What is the difference between が and は`."""
        config = self.bot.db['questions'][str(ctx.guild.id)][str(ctx.channel.id)]
        log_channel = self.bot.get_channel(config['log_channel'])
        target_message = await log_channel.fetch_message(int(log_id))
        if target not in ['asker', 'answerer', 'question', 'title', 'answer']:
            await hf.safe_send(ctx,
                               f"Invalid field specified in the log message.  Please choose a target to edit out of "
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
                await hf.safe_send(ctx, f"To edit the asker, give the user ID of the user.  For example: "
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
            await hf.safe_send(ctx, f"I lack the ability to add reactions, please give me this permission")

def setup(bot):
    bot.add_cog(Questions(bot))
