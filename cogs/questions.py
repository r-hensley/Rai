import discord
from discord.ext import commands
from .utils import helper_functions as hf
import asyncio, aiohttp, async_timeout
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime, date

import os
dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


class Questions(commands.Cog):
    """Help"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['tk', 'taekim', 'gram', 'g'])
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
        if not search_term:
            await hf.safe_send(ctx, "Please enter a search term. Check the help for this command")
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

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    response = resp
                    data = await resp.text()
        except (aiohttp.InvalidURL, aiohttp.ClientConnectorError):
            await hf.safe_send(ctx, f'invalid_url:  Your URL was invalid ({url})')
            return
        if response.status != 200:
            await hf.safe_send(ctx, f'html_error: Error {r.status_code}: {r.reason} ({url})')
            return

        jr = json.loads(data)
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
            await hf.safe_send(ctx, ctx.command.help)
            return

        # ### Call the search ###
        engine_id = 'ddde7b27ce4758ac8'
        with open(f'{dir_path}/gcse_api.txt', 'r') as read_file:
            url = f'https://www.googleapis.com/customsearch/v1' \
                  f'?q={search_term}' \
                  f'&cx={engine_id}' \
                  f'&key={read_file.read()}'

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    response = resp
                    data = await resp.text()
        except (aiohttp.InvalidURL, aiohttp.ClientConnectorError):
            await hf.safe_send(ctx, f'invalid_url:  Your URL was invalid ({url})')
            return
        if response.status != 200:
            await hf.safe_send(ctx, f'html_error: Error {r.status}: {r.reason} ({url})')
            return

        jr = json.loads(data)
        if 'items' in jr:
            results = jr['items']
        else:
            await hf.safe_send(ctx, embed=hf.red_embed("No results found."))
            return
        search_term = jr['queries']['request'][0]['searchTerms']

        def make_embed(page):
            emb = hf.green_embed(f"[Search for {search_term}](https://cse.google.com/cse?cx=ddde7b27ce4758ac8&"
                                 f"q={search_term.replace(' ','%20').replace('　', '%E3%80%80')})")
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
            try:
                await reaction.remove(user)
            except discord.Forbidden:
                pass

    @commands.command(aliases=['sc'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @commands.cooldown(1, 5, type=commands.BucketType.user)
    async def searchcompare(self, ctx, *search_terms):
        """Compares the number of exact results from different exact searches.

        Usage: `;sc <term1> <term2> ...`. Use quotation marks to input a term with multiple words.

        Examples: `;sc おはよう おはよー`   `;sc こんにちは こんにちわ こにちわ`

        Prefix the terms with one `site:<site>` to limit the search to one site.
        Example: `;sc site:twitter.com ワロタ 笑`"""
        if not search_terms:
            await hf.safe_send(ctx, ctx.command.help)
            return
        if len(search_terms) > 5:
            await hf.safe_send(ctx, "Please input less terms. You'll kill my bot!!")
            return

        if search_terms[0].startswith('site:'):
            site = re.search("site: ?(.*)", search_terms[0]).group(1)
            search_terms = search_terms[1:]
        else:
            site = None

        # ### Call the search ###
        engine_id = 'c7afcd4ef85db31a2'
        results = {}
        for search_term in search_terms:
            with open(f'{dir_path}/gcse_api.txt', 'r') as read_file:
                url = f'https://www.googleapis.com/customsearch/v1' \
                      f'?exactTerms={search_term}' \
                      f'&key={read_file.read()}' \
                      f'&cx={engine_id}'  # %22 is quotation mark
                if site:
                    url += f"&siteSearch={site}"
            try:
                with async_timeout.timeout(10):
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url) as resp:
                            response = resp
                            data = await resp.text()
                            try:
                                key = f"[{search_term}](https://cse.google.com/cse?cx=c7afcd4ef85db31a2#gsc.tab=0" \
                                      f'&gsc.q="{search_term}")'
                                if site:
                                    key = key[:-1] + f"%20site:{site})"
                                results[key] = data.split('"formattedTotalResults": "')[1].split('"')[0]
                            except IndexError:
                                await hf.safe_send(ctx, "There was an error retrieving the results.")
                                return
            except (aiohttp.InvalidURL, aiohttp.ClientConnectorError):
                await hf.safe_send(ctx, f'invalid_url:  Your URL was invalid ({url})')
                return
            if response.status != 200:
                await hf.safe_send(ctx, f'html_error: Error {response.status}: {response.reason} ({url})')
                return

        s = '\n'.join([f"**{x}**: 約{results[x]}件" for x in results])
        await hf.safe_send(ctx, embed=discord.Embed(title="Google search results", description=s, color=0x0C8DF0))

    @commands.command(aliases=['nsc', 'ns', 'nc'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @commands.cooldown(1, 5, type=commands.BucketType.user)
    async def newssearchcompare(self, ctx, *search_terms):
        """Compares number of results from top ten Japanese news sites:
        `news24`, `nhk`, `rocketnews24`, `asahi`, `jiji`,
        `nikkei`, `oricon`, `sankei`, `yomiuri`, `news.yahoo.co.jp`

        Usage: `;nsc <term1> <term2> ...`. Use quotation marks to input a term with multiple words.

        Examples: `;nsc おはよう おはよー`   `;nsc こんにちは こんにちわ こにちわ`"""
        if not search_terms:
            await hf.safe_send(ctx, ctx.command.help)
            return
        if len(search_terms) > 5:
            await hf.safe_send(ctx, "Please input less terms. You'll kill my bot!!")
            return

        # ### Call the search ###
        engine_id = 'cbbca2d78e3d9fb2d'
        results = {}
        for search_term in search_terms:
            with open(f'{dir_path}/gcse_api.txt', 'r') as read_file:
                url = f'https://www.googleapis.com/customsearch/v1' \
                      f'?exactTerms={search_term}' \
                      f'&key={read_file.read()}' \
                      f'&cx={engine_id}'  # %22 is quotation mark

            try:
                with async_timeout.timeout(10):
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url) as resp:
                            response = resp
                            data = await resp.text()
                            try:
                                results[f"[{search_term}](https://cse.google.com/cse?cx=cbbca2d78e3d9fb2d#gsc.tab=0"
                                        f"&gsc.q=%22{search_term}%22)"] = \
                                    data.split('"formattedTotalResults": "')[1].split('"')[0]
                            except IndexError:
                                await hf.safe_send(ctx, "There was an error retrieving the results.")
                                return
            except (aiohttp.InvalidURL, aiohttp.ClientConnectorError):
                await hf.safe_send(ctx, f'invalid_url:  Your URL was invalid ({url})')
                return
            if response.status != 200:
                await hf.safe_send(ctx, f'html_error: Error {response.status}: {response.reason} ({url})')
                return

        s = '\n'.join([f"**{x}**: 約{results[x]}件" for x in results])
        await hf.safe_send(ctx, embed=discord.Embed(title="News sites search results", description=s, color=0x7900F7))

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

        print(ctx.author, target_message.author)

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
            emb.add_field(name=f"Jump Link to Question:", value=f"[Jump URL]({target_message.jump_url})")
        else:
            emb.add_field(name=f"Question:", value=f"{title}\n[Jump URL]({target_message.jump_url})")
        if ctx.author != target_message.author:
            emb.set_footer(text=f"Question added by {ctx.author.name}")
        try:
            await self._delete_log(ctx)
            log_message = await hf.safe_send(log_channel, embed=emb)
            await self._post_log(ctx)
        except discord.errors.HTTPException as err:
            if err.status == 400:
                await hf.safe_send(ctx, "The question was too long, or the embed is too big.")
            elif err.status == 403:
                await hf.safe_send(ctx, "I didn't have permissions to post in that channel")
            else:
                raise
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
    @commands.guild_only()
    async def question(self, ctx, *, args=None):
        """A module for asking questions, put the title of your quesiton like `;question <title>`"""
        if not args:
            msg = f"Type `;q <question text>` to make a question, or do `;help q`. For now, here's the questions list:"
            await hf.safe_send(ctx, msg)
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
        except KeyError:
            log_message = None
            await hf.safe_send(ctx, "Sorry I think this question got a bit bugged out. I'm going to close it.")

        try:
            question_message = await ctx.channel.fetch_message(question['question_message'])
            if ctx.author.id not in [question_message.author.id, question['command_caller']] \
                    and not hf.submod_check(ctx) and ctx.author.id not in \
                    self.bot.db['channel_mods'].get(str(ctx.guild.id), {}).get(str(ctx.channel.id), []):
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
                          value=answer_text + '\n' + f"[Jump URL]({answer_message.jump_url})")
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

        await self._delete_log(ctx)
        await self._post_log(ctx)

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
    async def question_list(self, ctx, target_channel=None):
        """Shows a list of currently open questions"""
        if not target_channel:
            target_channel = ctx.channel
        try:
            config = self.bot.db['questions'][str(ctx.guild.id)]
        except KeyError:
            await hf.safe_send(target_channel, f"There are no questions channels on this server.  Run `;question"
                                               f" setup` in the questions channel to start setup.")
            return

        # getting the main log channel
        if str(ctx.channel.id) in config:
            log_channel_id = config[str(ctx.channel.id)]['log_channel']  # main question channels
        elif str(ctx.guild.id) in config:
            log_channel_id = config[str(ctx.guild.id)]['log_channel']  # a default log channel for "all other chan."
        else:
            log_channel_id = None
            for q_chan in config:
                if config[q_chan]['log_channel'] == ctx.channel.id:
                    log_channel_id = ctx.channel.id  # if you call from a log channel instead of a question channel
                    break
            if not log_channel_id:
                await hf.safe_send(target_channel, "This channel is not setup as a questions channel.")
                return

        first = True
        # the ⁣ are invisble tags to confirm that this is indeed a `;q list` result for the _list_update function
        emb = discord.Embed(title=f"⁣List⁣ of open questions (sorted by channel then date):")
        for channel in config:
            if config[channel]['log_channel'] != log_channel_id:
                continue
            channel_config = config[str(channel)]['questions']
            question_channel = self.bot.get_channel(int(channel))
            if first:
                first = False
                emb.description=f"**__#{question_channel.name}__**"
            else:
                if channel_config:
                    emb.add_field(name=f"⁣**__{'　'*30}__**⁣",
                                  value=f'**__#{question_channel.name}__**', inline=False)
            for question in channel_config.copy():
                try:
                    if question not in channel_config:
                        await hf.safe_send(ctx, "Seems you're maybe trying things too fast. Try again.")
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
                        log_message = ctx.guild.get_channel(log_channel_id)
                        try:
                            log_message = await log_message.fetch_message(q_config['log_message'])
                        except discord.Forbidden:
                            await hf.safe_send(ctx, f"I Lack the ability to see messages or message history in "
                                                    f"{log_message.mention}.")
                            return
                        value_text += f"__[Responses: {len(q_config['responses'])}]({log_message.jump_url})__\n"

                    value_text += f"⁣⁣⁣⁣\n[Jump URL]({question_message.jump_url})"
                    text_splice = 800 - len(value_text)
                    if len(question_text) > text_splice:
                        question_text = question_text[:-3] + '...'
                    value_text = value_text.replace("⁣⁣⁣⁣", question_text[:text_splice])
                    emb.add_field(name=f"Question `{question}`", value=value_text)
                except discord.errors.NotFound:
                    emb.add_field(name=f"Question `{question}`",
                                  value="original message not found")
        await hf.safe_send(target_channel, embed=emb)

    @question.command()
    @hf.is_admin()
    async def edit(self, ctx, log_id, target, *text):
        """
        Edit either the asker, answerer, question, title, or answer of a question log in the log channel

        Usage: `;q edit <log_id> <asker|answerer|question|title|answer> <new data>`.

        Example: `;q edit 2 question  What is the difference between が and は`.
        """
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
        except discord.errors.Forbidden:
            await hf.safe_send(ctx, f"I lack the ability to add reactions, please give me this permission")

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
        try:
            config = self.bot.db['questions'][str(ctx.guild.id)][str(ctx.channel.id)]
        except KeyError:
            return
        if not response:
            await hf.safe_send(ctx, "You need to type something for your response.")
            return
        if len(response.split()) == 1:
            try:
                msg = await ctx.channel.fetch_message(int(response))
                await ctx.message.add_reaction('⤴')
                ctx.message = msg
                ctx.author = msg.author
                response = msg.content
            except (discord.NotFound, ValueError):
                pass
        if index not in config['questions']:
            await hf.safe_send(ctx, "Invalid question index. Make sure you're typing this command in the channel "
                                    "the question was originally made in.")
            return

        try:
            log_channel = ctx.guild.get_channel(config['log_channel'])
        except discord.NotFound:
            await hf.safe_send(ctx, "The original log channel can't be found (type `;q setup`)")
            return
        try:
            log_message = await log_channel.fetch_message(config['questions'][index]['log_message'])
        except discord.NotFound:
            await hf.safe_send(ctx, "The original question log message could not be found. Type `;q a <index>` to "
                                    "close the question and clear it.")
            return

        emb: discord.Embed = log_message.embeds[0]
        value_text = f"⁣⁣⁣\n[Jump URL]({ctx.message.jump_url})"
        emb.add_field(name=f"Response by {ctx.author.name}#{ctx.author.discriminator}",
                      value=value_text.replace('⁣⁣⁣', response[:1024-len(value_text)]))
        await log_message.edit(embed=emb)
        config['questions'][index].setdefault('responses', []).append(ctx.message.jump_url)
        await self._delete_log(ctx)
        await self._post_log(ctx)
        await ctx.message.add_reaction('✅')

    async def _delete_log(self, ctx):
        """Internal command for deleting the last message in log channel if it is `;q list` result"""
        try:
            config = self.bot.db['questions'][str(ctx.guild.id)][str(ctx.channel.id)]
        except KeyError:
            return

        log_channel = ctx.guild.get_channel(config['log_channel'])
        if not log_channel:
            await hf.safe_send(ctx, "The original log channel was not found. Please run `;q setup`.")
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
        try:
            config = self.bot.db['questions'][str(ctx.guild.id)][str(ctx.channel.id)]
        except KeyError:
            return

        log_channel = ctx.guild.get_channel(config['log_channel'])
        if not log_channel:
            await hf.safe_send(ctx, "The original log channel was not found. Please run `;q setup`.")
            return
        # ctx.channel = log_channel
        await ctx.invoke(self.question_list, log_channel)

    @commands.command(aliases=['diff'])
    async def difference(self, ctx, *, query):
        """Pastes a text which links to how to find the difference between two words for language learning"""
        if not query:
            query = "X Y"
        urlquery = '+'.join(query.split())
        emb = hf.green_embed(f"A lot of 'what is the difference between X and Y' kinds of questions can be answered "
                             f"by typing something like the following into google (click the links to see the "
                             f"search results):\n\n"
                             f"['Japanese {query} difference']"
                             f"(https://www.google.com/search?q=japanese+{urlquery}+difference)\n"
                             f"['{query} difference']"
                             f"(https://www.google.com/search?q={urlquery}+difference)\n"
                             f"['{query} 違い']"
                             f"(https://www.google.com/search?q={urlquery}+違い)\n"
                             )
        await hf.safe_send(ctx, embed=emb)

    @commands.command()
    async def neko(self, ctx, *search):
        """Search the grammar database at itazuraneko. Use: `;neko <search term>`. Optionally, add a tag at the end
        to specify which grammar dictionary you want to search (options: `-basic`, `-intermediate`, `-advanced`,
        `-handbook`, `-donnatoki`).
        """

        if not search:
            await hf.safe_send(ctx, "You have to input a search term!")
            return

        dictionaries = {"dojg/dojgpages/basic": "A Dictionary of Basic Japanese Grammar",
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

        with async_timeout.timeout(10):
            async with aiohttp.ClientSession() as session:
                async with session.get('https://itazuraneko.neocities.org/grammar/masterreference.html') as response:
                    html = await response.text()

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
            for c in "()（）":
                text = text.replace(c, "")
            if "〈" in text:
                text = re.compile("〈.*〉").sub("", text)
            return text.replace("…", "～").replace("~", "～")

        for i in results:
            url = i["href"]
            dictionary = None
            for site in dictionaries:
                if site in url:
                    dictionary = dictionaries[site]
                    break
            if not url.startswith("https"):
                url = "https://itazuraneko.neocities.org/grammar/" + url
            grammar = "".join([str(x) for x in i.contents])
            if "<rt>" in grammar:
                grammar = re.compile("(<rt>.*?<\/rt>|<\/?ruby>)").sub("", grammar)
            search_field = parse_search(grammar)
            entries.append((grammar, dictionary, url, search_field))

        if search[-1][0] == "-":
            dictionary = dictionaries[search[-1][1:].casefold()]
            search = search[:-1]
        else:
            dictionary = None

        exacts = []
        contains = []
        for entry in entries:  # (grammar name, dictionary name, url, search field)
            if dictionary and entry[1] != dictionary:
                continue
            for term in search:
                term = parse_search(term)
                if term == entry[3]:
                    exacts.append(entry)
                elif term in entry[3]:
                    contains.append(entry)

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

        if not exacts and not contains:
            msg = await hf.safe_send(ctx, embed=hf.red_embed("I couldn't find any results for your search term."))
            await wait_for_delete(msg)
            return
        emb = discord.Embed(title="Itazuraneko Grammar Search", color=0x00FF00)
        desc = ''
        index = 1
        for entry in exacts + ['middle'] + contains:
            if entry == 'middle':
                desc += "～～～～～～\n"
                continue
            addition = f"{index}) [{entry[0]}]({entry[2]}) ({dict_abbreviations[entry[1]]})\n"
            if len(desc + addition) < 2046:
                desc += addition
                index += 1
            else:
                break
        emb.description = desc
        msg = await hf.safe_send(ctx, embed=emb)
        await wait_for_delete(msg)


def setup(bot):
    bot.add_cog(Questions(bot))
