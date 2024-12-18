from datetime import timedelta, timezone
import os
import asyncio
import re
from typing import Optional
from inspect import cleandoc
from random import choice
from collections import Counter
from dateparser import parse

import discord
from discord.ext import commands
from discord import app_commands
from Levenshtein import distance as LDist

from cogs.utils.helper_functions import format_interval

from .utils import helper_functions as hf
from cogs.utils.BotUtils import bot_utils as utils

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
BLACKLIST_CHANNEL_ID = 533863928263082014
MODCHAT_SERVER_ID = 257984339025985546
JP_SERVER_ID = 189571157446492161
SP_SERVER_ID = 243838819743432704
CH_SERVER_ID = 266695661670367232
CL_SERVER_ID = 320439136236601344
RY_SERVER_ID = 275146036178059265
FEDE_TESTER_SERVER_ID = 941155953682821201
FRENCH_SERVER_ID = 254463427949494292

ENG_ROLE = {
    266695661670367232: 266778623631949826,  # C-E Learning English Role
    320439136236601344: 474825178204078081  # r/CL Learning English Role
}
RYRY_RAI_BOT_ID = 270366726737231884


def doneq_check(ctx):
    if not ctx.guild:
        return
    if ctx.guild.id not in [JP_SERVER_ID, SP_SERVER_ID]:
        return
    if not isinstance(ctx.channel, discord.Thread):
        return
    if not isinstance(ctx.channel.parent, discord.ForumChannel):
        return
    return True


def fe_check(ctx):
    """Checks if a user has the correct combination of roles for the fe() command"""
    if not ctx.guild:
        return
    if ctx.guild.id != JP_SERVER_ID:
        return
    role_ids = [role.id for role in ctx.author.roles]
    lower_fluent_english = 241997079168155649
    native_japanese = 196765998706196480
    fluent_japanese = 270391106955509770
    if native_japanese in role_ids and lower_fluent_english in role_ids:
        return True
    if fluent_japanese in role_ids and lower_fluent_english in role_ids:
        return True


def blacklist_check():
    async def pred(ctx):
        if not ctx.guild:
            return
        modchat = ctx.bot.get_guild(MODCHAT_SERVER_ID)
        if not modchat:
            return
        if ctx.author in modchat.members:
            if ctx.guild.id == MODCHAT_SERVER_ID or hf.admin_check(ctx):
                return True

    return commands.check(pred)


class General(commands.Cog):
    """My custom cog that does stuff!"""

    def __init__(self, bot):
        self.bot = bot
        self.ignored_characters = []

    @commands.command(hidden=True)
    @commands.bot_has_permissions(send_messages=True)
    async def help(self, ctx, *, arg=''):
        # If both a and b return True for a command, then it can run
        async def check_command(command):
            try:
                # Check permissions of command
                a = await command.can_run(ctx)
            except commands.BotMissingPermissions:
                # Bot lacks some permission required to do a command
                a = False
            except commands.CheckFailure:
                # A check attached to the command failed
                a = False
            if hasattr(command, "hidden"):
                # Hidden commands do not appear in help dialog
                b = not command.hidden
            else:
                # Slash commands don't have the attribute "hidden"
                # I've decided they shouldn't appear in the help dialog
                # since they're not a prefix command
                b = False
            return a and b

        if arg:  # user wants help on a specific command/cog
            requested = self.bot.get_command(arg)
            which = 'command'
            if not requested:
                requested = self.bot.get_cog(arg)
                which = 'cog'
            if not requested:
                await utils.safe_send(ctx, "I was unable to find the command or command module you requested.")
                return
            if which == 'command':
                message = f"**;{requested.qualified_name}**\n"
                if requested.aliases:
                    message += f"Aliases: `{'`, `'.join(requested.aliases)}`\n"
                if isinstance(requested, commands.Group):
                    usable_commands = sorted([c.name for c in requested.commands if await check_command(c)])
                    if usable_commands:
                        message += f"Subcommands: `{'`, `'.join(usable_commands)}`\n" \
                                   f"Use subcommands by chaining with the command group name. For example, " \
                                   f"`;{requested.name} {usable_commands[0]}`\n"

                message += '\n'
                if requested.help:
                    message += requested.help
                emb = utils.green_embed(cleandoc(message))
                await utils.safe_send(ctx, embed=emb)

            else:  # requested a cog
                message = f"**;{requested.qualified_name}**\n"
                c_list = sorted([c.name for c in requested.get_commands() if await check_command(c)])
                if c_list:
                    message += f"Commands: `{'`, `'.join(c_list)}`\n\n"
                else:
                    message += '\n\n'
                message += requested.description
                emb = utils.green_embed(cleandoc(message))
                await utils.safe_send(ctx, embed=emb)

        else:  # user wants to see full command list
            cmd_dict = {}
            help_msg = "Type `;help <command>` for more info on any command or category. " \
                       "For (subcommands), chain with the parent command.\n\n"
            for cog in self.bot.cogs:
                cmd_dict[cog] = []
                for command in self.bot.cogs[cog].get_commands():
                    if await check_command(command):
                        if isinstance(command, commands.Group):
                            to_append = [command.name, [c.name for c in command.commands if await check_command(c)]]
                            if to_append[1]:
                                cmd_dict[cog].append(f"`{to_append[0]}` (`{'`, `'.join(sorted(to_append[1]))}`)")
                            else:
                                cmd_dict[cog].append(f"`{to_append[0]}`")
                        else:
                            cmd_dict[cog].append(f"`{command.name}`")

            for cog in sorted([name for name in cmd_dict]):
                to_add = ""
                if cmd_dict[cog]:
                    to_add += f"__**{cog}**__  {', '.join(sorted(cmd_dict[cog]))}\n"
                if len(help_msg + to_add) <= 2000:
                    help_msg += to_add
                else:
                    await utils.safe_send(ctx, help_msg)
                    help_msg = to_add

            await utils.safe_send(ctx, help_msg)

    @commands.command()
    @commands.check(fe_check)
    async def fe(self, ctx):
        """If you have both fluent English and native or fluent Japanese tags, type this command
        to swap out the color in your name between blue and green."""
        upper_fluent_english = ctx.guild.get_role(820133363700596756)

        if upper_fluent_english in ctx.author.roles:
            try:
                await ctx.author.remove_roles(upper_fluent_english)
            except (discord.Forbidden, discord.HTTPException):
                await utils.safe_send(ctx, "There has been an error, please try again.")
                return

        else:
            try:
                await ctx.author.add_roles(upper_fluent_english)
            except (discord.Forbidden, discord.HTTPException):
                await utils.safe_send(ctx, "There has been an error, please try again.")
                return

        await ctx.message.add_reaction('✅')

    @commands.command()
    @commands.check(lambda ctx: ctx.author.id in [681266267763769377, 202995638860906496])
    async def callao(self, ctx: commands.Context):
        if not ctx.message.reference:
            return

        if not ctx.message.reference.cached_message:
            return

        try:
            await ctx.message.reference.cached_message.author.timeout(timedelta(seconds=5), reason="RAI_SELFMUTE")
            await ctx.message.reference.cached_message.reply("You callao!")
        except (discord.Forbidden, discord.HTTPException):
            await ctx.message.reply("Sorry, that user was too strong for me :(")

    @commands.command()
    @commands.check(lambda ctx: ctx.guild.id == 759132637414817822 if ctx.guild else False)
    async def risk(self, ctx):
        """Typing this command will sub you to pings for when it's your turn."""
        config = self.bot.db['risk']['sub']
        if str(ctx.author.id) in config:
            config[str(ctx.author.id)] = not config[str(ctx.author.id)]
        else:
            config[str(ctx.author.id)] = True
        if config[str(ctx.author.id)]:
            await utils.safe_send(ctx, "You will now receive pings when it's your turn.")
        else:
            await utils.safe_send(ctx, "You will no longer receive pings when it's your turn.")

    @commands.command()
    async def topic(self, ctx):
        """Provides a random conversation topic.
        Hint: make sure you also answer "why". Challenge your friends on their answers.
        If you disagree with their answer, talk it out."""
        path = f"{dir_path}/cogs/utils/conversation_topics.txt"
        if ctx.guild:
            if ctx.guild.id == FRENCH_SERVER_ID:
                path = f"{dir_path}/cogs/utils/french_conversation_topics.txt"

        topics = [line.rstrip('\n') for line in open(path, 'r', encoding='utf8')]
        topic = choice(topics)
        while topic.startswith('#'):
            topic = choice(topics)

        color = discord.Color.random()  # random color
        idx = str(topics.index(topic))  # number in the list of topics

        if 'topics' not in self.bot.db:
            self.bot.db['topics'] = {}

        description = f"__Topic {idx}/{len(topics)}__\n" \
                      f"**{topic}**"

        config = {}
        if ctx.guild:
            config: dict = self.bot.db['topics'].setdefault(str(ctx.guild.id), {})
            last_occurence: str = config.get(idx, {}).get('jump_url', '')
            number_of_times: int = config.get(idx, {}).get('number', 0)

            if last_occurence:
                if number_of_times > 1:
                    s = 's'
                else:
                    s = ''

                description += f"\n[`(chosen {number_of_times} time{s}, last time here)`]({last_occurence})"

        try:
            sent_msg = await utils.safe_send(ctx, embed=discord.Embed(description=description, color=color))
            if config:
                config[idx] = {'number': config.get(idx, {}).get('number', 0) + 1,
                               'jump_url': sent_msg.jump_url}
        except discord.Forbidden:
            pass

    @commands.command()
    @commands.guild_only()
    async def inrole(self, ctx, *, role_name):
        """Type `;inrole <role_name>` to see a list of users in a role."""
        role_name = role_name.casefold()
        role: Optional[discord.Role] = discord.utils.find(lambda i: i.name.casefold() == role_name, ctx.guild.roles)
        if not role:
            for i in ctx.guild.roles:
                if i.name.casefold().startswith(role_name):
                    role = i
                    break
        if not role:
            await utils.safe_send(ctx, "I couldn't find the role you specified.")
            return
        emb = discord.Embed(title=f"**List of members in {role.name} role - {len(role.members)}**",
                            description="",
                            color=0x00FF00)
        members = sorted(role.members, key=lambda m: m.name.casefold())
        for member in members:
            new_desc = emb.description + f"{str(member)}\n"
            if len(new_desc) < 2045:
                emb.description = new_desc
            else:
                emb.description += "..."
                break
        await utils.safe_send(ctx, embed=emb)

    @commands.group(aliases=['hc'], invoke_without_command=True)
    @commands.guild_only()
    @commands.check(lambda ctx: ctx.guild.id in [SP_SERVER_ID, CH_SERVER_ID, CL_SERVER_ID] if ctx.guild else False)
    async def hardcore(self, ctx: commands.Context):
        """Adds/removes the hardcore role from you."""
        role = ctx.guild.get_role(self.bot.db['hardcore'][str(ctx.guild.id)]['role'])
        if ctx.guild.id == SP_SERVER_ID:
            learning_eng = ctx.guild.get_role(247021017740869632)
            learning_sp = ctx.guild.get_role(297415063302832128)
            if learning_eng not in ctx.author.roles and learning_sp not in ctx.author.roles:
                await utils.safe_send(ctx, "You need to have a learning role to use this command.")
                return
            elif learning_eng in ctx.author.roles and learning_sp in ctx.author.roles:
                await utils.safe_send(ctx, "You have both learning roles. "
                                           "Please remove one before using this command.")
                return
        if role in ctx.author.roles:
            await ctx.author.remove_roles(role)
            try:
                await utils.safe_send(ctx, "I've removed hardcore from you.")
            except discord.Forbidden:
                pass
        else:
            await ctx.author.add_roles(role)
            await utils.safe_send(ctx, "I've added hardcore to you. You can only speak in the language you're learning.")

    @commands.command(aliases=['forcehardcore', 'forcedhardcore'])
    @commands.guild_only()
    @commands.check(lambda ctx: ctx.guild.id in [CH_SERVER_ID, CL_SERVER_ID] if ctx.guild else False)
    @commands.bot_has_permissions(manage_messages=True)
    @hf.is_admin()
    async def force_hardcore(self, ctx):
        try:
            if ctx.channel.id in self.bot.db['forcehardcore']:
                self.bot.db['forcehardcore'].remove(ctx.channel.id)
                await utils.safe_send(ctx, f"Removed {ctx.channel.name} from list of channels for forced hardcore mode")
            else:
                self.bot.db['forcehardcore'].append(ctx.channel.id)
                await utils.safe_send(ctx, f"Added {ctx.channel.name} to list of channels for forced hardcore mode")
        except KeyError:
            self.bot.db['forcehardcore'] = [ctx.channel.id]
            await utils.safe_send(ctx, f"Created forced hardcore mode config; "
                                    f"added {ctx.channel.name} to list of channels for forced hardcore mode")

    @hardcore.command()
    async def ignore(self, ctx):
        """Ignores a channel for hardcore mode."""
        if str(ctx.guild.id) in self.bot.db['hardcore']:
            config = self.bot.db['hardcore'][str(ctx.guild.id)]
        else:
            return
        try:
            if ctx.channel.id not in config['ignore']:
                config['ignore'].append(ctx.channel.id)
                await utils.safe_send(ctx, f"Added {ctx.channel.name} to list of ignored channels for hardcore mode")
            else:
                config['ignore'].remove(ctx.channel.id)
                await utils.safe_send(ctx, f"Removed {ctx.channel.name} from list of ignored channels for hardcore mode")
        except KeyError:
            config['ignore'] = [ctx.channel.id]
            await utils.safe_send(ctx, f"Added {ctx.channel.name} to list of ignored channels for hardcore mode")

    @hardcore.command()
    @hf.is_admin()
    async def list(self, ctx):
        """Lists the channels in hardcore mode."""
        channels = []
        try:
            for channel_id in self.bot.db['hardcore'][str(ctx.guild.id)]['ignore']:
                channel = self.bot.get_channel(int(channel_id))
                if channel:
                    channels.append(channel)
                else:
                    self.bot.db['hardcore'][str(ctx.guild.id)]['ignore'].remove(channel_id)
                    await utils.safe_send(ctx, f"Removed {channel_id} from list of excepted channels (couldn't find it).")
        except KeyError:
            return
        if channels:
            string = "__List of channels excepted from hardcore__:\n#" + '\n#'.join([c.name for c in channels])
            await utils.safe_send(ctx, string)

    @commands.group(hidden=True, aliases=['lh'], invoke_without_command=True)
    async def lovehug(self, ctx, url=None):
        """A command group for subscribing to lovehug mangas."""
        await ctx.invoke(self.lovehug_add, url)

    @lovehug.command(name='add')
    async def lovehug_add(self, ctx, url):
        """Adds a URL to your subscriptions."""
        search = await ctx.invoke(self.bot.get_command('lovehug_get_chapter'), url)
        if isinstance(search, str):
            if search.startswith('html_error'):
                await utils.safe_send(ctx, search)
                return
            if search.startswith('invalid_url'):
                await utils.safe_send(ctx, search)
                return
        if not search:
            await utils.safe_send(ctx, "The search failed to find a chapter")
            return
        if url not in self.bot.db['lovehug']:
            self.bot.db['lovehug'][url] = {'last': f"{url}{search['href']}",
                                           'subscribers': [ctx.author.id]}
        else:
            if ctx.author.id not in self.bot.db['lovehug'][url]['subscribers']:
                self.bot.db['lovehug'][url]['subscribers'].append(ctx.author.id)
            else:
                await utils.safe_send(ctx, "You're already subscribed to this manga.")
                return
        await utils.safe_send(ctx, f"The latest chapter is: {url}{search['href']}\n\n"
                                f"I'll tell you next time a chapter is uploaded.")

    @lovehug.command(name='remove')
    async def lovehug_remove(self, ctx, url):
        """Unsubscribes you from a manga. Input the URL: `;lh remove <url>`."""
        if url not in self.bot.db['lovehug']:
            await utils.safe_send(ctx, "No one is subscribed to that manga. Check your URL.")
            return
        else:
            if ctx.author.id in self.bot.db['lovehug'][url]['subscribers']:
                self.bot.db['lovehug'][url]['subscribers'].remove(ctx.author.id)
                await utils.safe_send(ctx, "You've been unsubscribed from that manga.")
                if len(self.bot.db['lovehug'][url]['subscribers']) == 0:
                    del self.bot.db['lovehug'][url]
            else:
                await utils.safe_send("You're not subscribed to that manga.")
                return

    @lovehug.command(name='list')
    async def lovehug_list(self, ctx):
        """Lists the manga you subscribed to."""
        subscriptions = []
        for url in self.bot.db['lovehug']:
            if ctx.author.id in self.bot.db['lovehug'][url]['subscribers']:
                subscriptions.append(f"<{url}>")
        subs_list = '\n'.join(subscriptions)
        if subscriptions:
            await utils.safe_send(ctx, f"The list of mangas you're subscribed to:\n{subs_list}")
        else:
            await utils.safe_send(ctx, "You're not subscribed to any mangas.")

    @commands.command(aliases=['git'])
    @commands.bot_has_permissions(send_messages=True)
    async def github(self, ctx):
        """Gives my github page"""
        await utils.safe_send(ctx, 'https://github.com/ryry013/Rai')

    @commands.command()
    @commands.bot_has_permissions(send_messages=True)
    async def punch(self, ctx, user: discord.Member = None):
        """A punch command I made as a test"""
        if not user:
            user = ctx.author
        await utils.safe_send(ctx, "ONE PUNCH! And " + user.mention + " is out! ლ(ಠ益ಠლ)")

    @commands.command()
    @commands.bot_has_permissions(send_messages=True)
    async def ping(self, ctx, x=1):
        """sends back 'hello'"""
        latency = str(round(self.bot.latency * 1000, x))
        fortnights = 0.00000082672 * self.bot.latency
        fortnights = f"{round(fortnights, 11):.11f} fortnights"
        if ctx.author.id == 233487484791685120:
            await utils.safe_send(ctx, fortnights)
        else:
            await utils.safe_send(ctx, latency + 'ms')

    @commands.command()
    @commands.bot_has_permissions(send_messages=True)
    async def invite(self, ctx):
        """Gives an invite to bring this bot to your server"""
        modchat = self.bot.get_guild(MODCHAT_SERVER_ID)
        if modchat:
            members = modchat.members
        else:
            members = []
        if ctx.author in members or ctx.author.id == self.bot.owner_id:
            await utils.safe_send(ctx, discord.utils.oauth_url(self.bot.user.id,
                                                            permissions=discord.Permissions(permissions=27776)))
        else:
            await utils.safe_send(ctx, "Sorry, the bot is currently not public. "
                                    "The bot owner can send you an invite link.")

    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(send_messages=True)
    async def pencil(self, ctx):
        """Adds a pencil to your name. Rai cannot edit the nickname of someone above it on the role list"""
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        try:
            await ctx.author.edit(nick=ctx.author.display_name + '📝')
            msg_text = "I've added 📝 to your name.  This means you wish to be corrected in your sentences"
            await utils.safe_send(ctx, msg_text, delete_after=7.0)
        except discord.Forbidden:
            await utils.safe_send(ctx, "I lack the permissions to change your nickname", delete_after=7.0)
        except discord.HTTPException:
            try:
                await ctx.message.add_reaction('💢')
            except discord.NotFound:
                pass

    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(send_messages=True)
    async def eraser(self, ctx):
        """Erases the pencil from `;pencil`. Rai cannot edit the nicknames of users above it on the role list."""
        try:
            await ctx.author.edit(nick=ctx.author.display_name[:-1])
            await ctx.message.add_reaction('◀')
        except discord.Forbidden:
            await utils.safe_send(ctx, "I lack the permissions to change your nickname")

    @commands.command(aliases=['ryry'])
    @commands.bot_has_permissions(send_messages=True)
    async def ryan(self, ctx):
        """Posts a link to the help docs server for my bot"""
        await utils.safe_send(ctx, "You can find some shitty docs for how to use my bot here: "
                                "https://github.com/ryry013/Rai/blob/master/README.md \n"
                                "You can ask questions and find some further details here: https://discord.gg/7k5MMpr")

    @commands.command(aliases=[';p', ';s', ';play', ';skip', '_;', '-;', ')', '__;', '___;', ';leave', ';join',
                               ';l', ';q', ';queue', ';pause', ';volume', ';1', ';vol', ';np', ';list'], hidden=True)
    async def ignore_commands_list(self, ctx):
        pass

    @commands.command(aliases=['cl', 'checklanguage'])
    @commands.bot_has_permissions(send_messages=True)
    @commands.cooldown(1, 15, type=commands.BucketType.user)
    @commands.check(lambda x: getattr(x.guild, "id", None) in [SP_SERVER_ID, 759132637414817822])
    async def check_language(self, ctx, *, msg: str):
        """Shows what's happening behind the scenes for hardcore mode.  Will try to detect the language that your\
        message was typed in, and display the results.  Note that this is non-deterministic code, which means\
        repeated results of the same exact message might give different results every time.

        Usage: `;cl <text you wish to check>`"""
        if not ctx.guild:
            return
        stripped_msg = utils.rem_emoji_url(msg)
        if len(msg) > 900:
            await utils.safe_send(ctx, "Please pick a shorter test  message")
            return
        if not stripped_msg:
            stripped_msg = ' '
        if ctx.guild.id in [SP_SERVER_ID, 759132637414817822]:
            probs = self.bot.langdetect.predict_proba([stripped_msg])[0]
            lang_result = f"English: {round(probs[0], 3)}\nSpanish: {round(probs[1], 3)}"
            ctx.command.reset_cooldown(ctx)
        else:
            await utils.safe_send(ctx, "The language module being used by Rai no longer works. A new one will be found.")
            return
        str = f"Your message:```{msg}```" \
              f"The message I see (no emojis or urls): ```{stripped_msg}```" \
              f"The language I detect: ```{lang_result}```"
        await utils.safe_send(ctx, str)

    @commands.command(aliases=['server', 'info', 'sinfo'])
    @commands.cooldown(1, 30, type=commands.BucketType.channel)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def serverinfo(self, ctx):
        """Shows info about this server"""
        guild = ctx.guild
        if not guild:
            await utils.safe_send(ctx,
                               f"{ctx.channel}.  Is that what you were looking for?  (Why are you trying to call info "
                               f"on 'this server' in a DM?)")
            return
        em = discord.Embed(title=f"**{guild.name}**",
                           description=f"**ID:** {guild.id}",
                           timestamp=guild.created_at,
                           colour=discord.Colour(0x877AD6))
        em.set_thumbnail(url=guild.icon.replace(static_format='png').url)
        if hasattr(guild, "region"):
            em.add_field(name="Region", value=guild.region)
        em.add_field(name="Channels", value=f"{len(guild.text_channels)} text / {len(guild.voice_channels)} voice")
        em.add_field(name="Verification Level", value=guild.verification_level)
        em.add_field(name="Guild created on (UTC)", value=guild.created_at.strftime("%Y/%m/%d %H:%M:%S"))
        em.add_field(name="Number of members", value=ctx.guild.member_count)

        if guild.afk_channel:
            em.add_field(name="Voice AFK Timeout",
                         value=f"{guild.afk_timeout // 60} mins → {guild.afk_channel.mention}")

        if guild.explicit_content_filter != "disabled":
            em.add_field(name="Explicit Content Filter", value=guild.explicit_content_filter)

        if guild.id not in [JP_SERVER_ID, SP_SERVER_ID]:
            em.add_field(name="Server owner", value=f"{str(guild.owner)}")

        # count top 6 member roles
        if len(guild.members) < 60000:
            role_count = Counter(role.name for member in guild.members
                                 for role in member.roles if not role.is_default())

            top_six_roles = '\n'.join(f"{role}: {count}" for role, count in role_count.most_common(6))
            em.add_field(name=f"Top 6 roles (out of {len(guild.roles)})", value=top_six_roles)
        else:
            em.add_field(name="Roles", value=str(len(guild.roles)))

        how_long_ago = discord.utils.utcnow() - guild.created_at
        days = how_long_ago.days
        years = days // 365
        bef_str = ''
        if years:
            bef_str = f"{years} years, "
        months = (days - 365 * years) // 30.416666666666668
        if months:
            bef_str += f"{int(months)} months, "
        days = days - 365 * years - round(30.416666666666668 * months)
        bef_str += f"{days} days"
        em.set_footer(text=f"Guild created {bef_str} ago on:")
        if len(em.fields) % 2 == 0:
            two = em.fields[-2]
            em.add_field(name=two.name, value=two.value)
            em.remove_field(-3)
        try:
            await utils.safe_send(ctx, embed=em)
        except discord.Forbidden:
            pass

    @commands.group(invoke_without_command=True, aliases=['gb', 'gbl', 'blacklist'], hidden=True)
    @blacklist_check()
    async def global_blacklist(self, ctx):
        """A global blacklist for banning spammers, requires three votes from mods from three different servers"""
        config = hf.database_toggle(ctx.guild, self.bot.db['global_blacklist'])
        if config['enable']:
            if not ctx.me.guild_permissions.ban_members:
                await utils.safe_send(ctx,
                                   'I lack the permission to ban members.  Please fix that before enabling this module')
                hf.database_toggle(ctx.guild, self.bot.db['global_blacklist'])
                return
            await utils.safe_send(ctx,
                               "Enabled the global blacklist on this server.  Anyone voted into the blacklist by three "
                               "mods and joining your server will be automatically banned.  "
                               "Type `;global_blacklist residency` to claim your residency on a server.")
        else:
            await utils.safe_send(ctx, "Disabled the global blacklist.  "
                                    "Anyone on the blacklist will be able to join  your server.")

    @global_blacklist.command(name='reason', aliases=['edit'])
    @blacklist_check()
    async def blacklist_reason(self, ctx, entry_message_id, *, reason):
        """Add a reason to a blacklist entry: `;gbl reason <message_id> <reason>`"""
        blacklist_channel = self.bot.get_channel(BLACKLIST_CHANNEL_ID)
        try:
            entry_message = await blacklist_channel.fetch_message(int(entry_message_id))
        except discord.NotFound:
            await utils.safe_send(ctx, "I couldn't find the message you were trying to edit. Make sure you link to "
                                    f"the message ID in the {blacklist_channel.mention}.")
            return
        emb = entry_message.embeds[0]
        old_reason = emb.fields[1].value
        emb.set_field_at(1, name=emb.fields[1].name, value=reason)
        await entry_message.edit(embed=emb)
        await utils.safe_send(ctx, f"Changed reason of {entry_message.jump_url}\nOld reason: ```{old_reason}```")

    @global_blacklist.command(name='remove', alias=['delete'])
    @blacklist_check()
    async def blacklist_remove(self, ctx, entry_message_id):
        """Removes a voting entry from the blacklist channel."""
        blacklist_channel = self.bot.get_channel(BLACKLIST_CHANNEL_ID)
        try:
            entry_message = await blacklist_channel.fetch_message(int(entry_message_id))
        except discord.NotFound:
            await utils.safe_send(ctx,
                               "Message not found.  If you inputted the ID of a user, please input the message ID of "
                               "the entry in the blacklist instead.")
            return
        emb = entry_message.embeds[0]
        target_id = emb.title.split(' ')[0]

        try:
            self.bot.db['global_blacklist']['blacklist'].remove(str(target_id))
        except ValueError:
            pass
        except KeyError:
            await utils.safe_send(ctx, "This user is not currently in the GBL.")

        try:
            del self.bot.db['global_blacklist']['votes'][str(target_id)]
        except ValueError:
            pass
        except KeyError:
            await utils.safe_send(ctx, "This user is not currently under consideration for votes.")

        await entry_message.delete()

        emb.color = discord.Color(int('ff00', 16))
        emb.set_field_at(0, name="Entry removed by", value=f"{str(ctx.author)}")
        await blacklist_channel.send(embed=emb)

        await ctx.message.add_reaction('✅')

    @global_blacklist.command()
    @blacklist_check()
    async def residency(self, ctx):
        """Claims your residency on a server"""
        config = self.bot.db['global_blacklist']['residency']
        if ctx.guild.id == MODCHAT_SERVER_ID:
            await utils.safe_send(ctx, "You can't claim residency here. Please do this command on the server you mod.")
            return

        if str(ctx.author.id) in config:
            server = self.bot.get_guild(config[str(ctx.author.id)])
            await utils.safe_send(ctx,
                               f"You've already claimed residency on {server.name}.  You can not change this without "
                               f"talking to Ryan.")
            return

        await utils.safe_send(ctx,
                           f"For the purpose of maintaining fairness in a ban, you're about to claim your mod residency"
                           f" to `{ctx.guild.name}`.  This can not be changed without talking to Ryan.  "
                           f"Do you wish to continue?\n\nType `yes` or `no` (case insensitive).")
        msg = await self.bot.wait_for('message',
                                      timeout=25.0,
                                      check=lambda m: m.author == ctx.author and m.channel == ctx.channel)

        if msg.content.casefold() == 'yes':  # register
            config[str(ctx.author.id)] = ctx.guild.id
            await utils.safe_send(ctx,
                               f"Registered your residency to `{ctx.guild.name}`.  Type `;global_blacklist add <ID>`"
                               f" to vote on a user for the blacklist")

        elif msg.content.casefold() == 'no':  # cancel
            await utils.safe_send(ctx, "Understood.  Exiting module.")

        else:  # invalid response
            await utils.safe_send(ctx, "Invalid response")

    @blacklist_check()
    @global_blacklist.command(aliases=['vote'], name="add")
    async def blacklist_add(self, ctx, *, args):
        """Add people to the blacklist"""
        args = args.replace('\n', ' ').split()
        list_of_ids = []
        reason = "None"
        for arg_index in range(len(args)):
            potential_id = re.search(r'\d{17,22}', args[arg_index])
            if potential_id:
                # using regex, add to list_of_ids just the ID digits (ignore characters around it)
                list_of_ids.append(potential_id.group())
            else:
                reason = ' '.join(args[arg_index:])
                break
        channel = self.bot.get_channel(BLACKLIST_CHANNEL_ID)
        config = self.bot.db['global_blacklist']
        if not list_of_ids:
            await utils.safe_send(ctx.author, "No valid ID found in command")
            return
        for user in list_of_ids:
            user_obj = self.bot.get_user(user)
            if not user_obj:
                try:
                    user = user.replace('<@!', '').replace('<@', '').replace('>', '')
                    user_obj = await self.bot.fetch_user(user)
                except (discord.NotFound, discord.HTTPException):
                    user_obj = None

            async def post_vote_notification(target_user, reason):
                try:
                    await ctx.message.add_reaction('✅')
                except discord.Forbidden:
                    await ctx.send("User added to blacklist ✅")
                if not target_user:
                    target_user = ''
                emb = discord.Embed(title=f"{user} {target_user} (1 vote)", color=discord.Color(int('ffff00', 16)))
                emb.add_field(name='Voters', value=ctx.author.name)
                emb.add_field(name='Reason', value=reason)
                msg = await utils.safe_send(channel, embed=emb)
                await msg.add_reaction('⬆')
                return msg

            try:  # the guild ID that the person trying to add a vote belongs to
                user_residency = config['residency'][str(ctx.author.id)]  # a guild id
            except KeyError:
                await utils.safe_send(ctx.author,
                                   "Please claim residency on a server first with `;global_blacklist residency`")
                return

            if user in config['blacklist']:  # already blacklisted
                await utils.safe_send(ctx, f"{user} is already on the blacklist")
                continue

            if user not in config['votes']:  # 0 votes
                config['votes'][user] = {'votes': [user_residency], 'message': 0}
                msg = await post_vote_notification(user_obj, reason)
                config['votes'][user]['message'] = msg.id
                continue

            if user in config['votes']:  # 1, 2, or 3 votes
                list_of_votes = config['votes'][user]['votes']
                if user_residency in list_of_votes:
                    try:
                        await utils.safe_send(ctx.author, f"{user} - Someone from your server already voted")
                    except discord.Forbidden:
                        await utils.safe_send(ctx, f"{user} - Someone from your server already voted")
                    continue

                message = await channel.fetch_message(config['votes'][user]['message'])
                emb = message.embeds[0]
                title_str = emb.title
                result = re.search(r'(\((.*)\))? \((.) votes?\)', title_str)
                # target_username = result.group(2)
                num_of_votes = result.group(3)
                emb.title = re.sub('(.) vote', f'{int(num_of_votes) + 1} vote', emb.title)
                if num_of_votes in '1':  # 1-->2
                    emb.title = emb.title.replace('vote', 'votes')
                if num_of_votes in '12':  # 1-->2 or 2-->3
                    config['votes'][user]['votes'].append(user_residency)
                if num_of_votes == '3':  # 2-->3
                    emb.color = discord.Color(int('ff0000', 16))
                    del config['votes'][user]
                    config['blacklist'].append(int(user))
                emb.set_field_at(0, name=emb.fields[0].name, value=emb.fields[0].value + f', {ctx.author.name}')
                await message.edit(embed=emb)

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
        await utils.safe_send(ctx, embed=emb)

    @global_blacklist.command(name="sub")
    @blacklist_check()
    async def blacklist_bansub(self, ctx):
        """Subscribes yourself to pings for your server"""
        # a list of which server IDs a user is subscribed to
        guild = self.bot.get_guild(MODCHAT_SERVER_ID)
        subbed_roles: list = self.bot.db['bansub']['user_to_role'].setdefault(str(ctx.author.id), [])
        user_role_ids = [role.id for role in ctx.author.roles if str(role.color) == "#3498db"]  # only want blue roles
        selection_dictionary = {}  # for later when the user selects a role to toggle
        guild_id_to_role: dict = self.bot.db['bansub']['guild_to_role']  # links a guild ID to the corresponding role
        role_to_guild_id = {guild_id_to_role[a]: a for a in guild_id_to_role}  # reverses the dictionary

        # ########################## DISPLAYING CURRENT SUBSCRIPTIONS ###########################

        counter = 1
        if not subbed_roles:
            msg = "You are currently not subscribed to pings for any servers.\n"
        else:
            msg = "You are currently subscribed to pings for the following servers: \n"
            for role_id in subbed_roles:  # a list of role IDs corresponding to server roles
                if role_id in user_role_ids:
                    user_role_ids.remove(role_id)
                role: discord.Role = guild.get_role(role_id)
                msg += f"    {counter}) {role.name}\n"
                selection_dictionary[counter] = role.id
                counter += 1

        msg += "\nHere are the roles to which you're not subscribed:\n"
        for role_id in user_role_ids:  # remaining here should only be the unsubscribed roles on the user's profile
            role: discord.Role = guild.get_role(role_id)
            msg += f"    {counter}) {role.name}\n"
            selection_dictionary[counter] = role.id
            counter += 1

        # ########################## ASK FOR WHICH ROLE TO TOGGLE ########################

        msg += "\nTo toggle the subscription for a role, please input now the number for that role."
        await utils.safe_send(ctx, msg)
        try:
            resp = await self.bot.wait_for("message", timeout=20.0,
                                           check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
        except asyncio.TimeoutError:
            await utils.safe_send(ctx, "Module timed out.")
            return
        try:
            resp = int(resp.content)
        except ValueError:
            await utils.safe_send(ctx, "Sorry, I didn't understand your response. Please input only a single number.")
            return
        if resp not in selection_dictionary:
            await utils.safe_send(ctx, "Sorry, I didn't understand your response. Please input only a single number.")
            return

        # ################################ TOGGLE THE ROLE #################################

        role_selection: int = selection_dictionary[resp]
        if role_selection in subbed_roles:
            subbed_roles.remove(role_selection)
            await utils.safe_send(ctx, "I've unsubcribed you from that role.")
        else:
            #      ####### Possibly match a role to a guild ########
            if role_selection not in role_to_guild_id:
                await utils.safe_send(ctx, "Before we continue, you need to tell me which server corresponds to that role."
                                        " We'll only need to do this once for your server. Please tell me either the "
                                        "server ID of that server, or the exact name of it.")
                try:
                    resp = await self.bot.wait_for("message", timeout=20.0,
                                                   check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
                    resp = resp.content
                except asyncio.TimeoutError:
                    await utils.safe_send(ctx, "Module timed out.")
                    return

                if re.search(r'^\d{17,22}$', resp):  # user specifies a guild ID
                    guild = self.bot.get_guild(int(resp))
                    if not guild:
                        await utils.safe_send(ctx, "I couldn't find the guild corresponding to that ID. "
                                                "Please start over.")
                        return
                else:  # user probably specified a guild name
                    guild = discord.utils.find(lambda g: g.name == resp, self.bot.guilds)
                    if not guild:
                        await utils.safe_send(ctx, "I couldn't find the guild corresponding to that guild name. "
                                                "Please start over.")
                        return
                guild_id_to_role[str(guild.id)] = role_selection

            #     ####### Add the role #######
            subbed_roles.append(role_selection)
            await utils.safe_send(ctx, "I've added you to the subscriptions for that role. I'll ping you for that server.")

    @global_blacklist.command(name="ignore")
    @blacklist_check()
    async def blacklist_ignore(self, ctx, user_id):
        """Types ;gbl ignore <id> to remove a user from (or add back to) all future logging in the bans channel.
        Use this for test accounts, alt accounts, etc."""
        try:
            user_id = int(user_id)
            if not (17 < len(str(user_id)) < 22):
                raise ValueError
        except ValueError:
            await utils.safe_send(ctx, "Please input a valid ID.")
            return
        if user_id in self.bot.db['bansub']['ignore']:
            self.bot.db['bansub']['ignore'].remove(user_id)
            await utils.safe_send(ctx, embed=utils.red_embed("I've removed that user from the ignore list."))
        else:
            self.bot.db['bansub']['ignore'].append(user_id)
            await utils.safe_send(ctx, embed=utils.green_embed("I've added that user to the ignore list for ban logging."))

    @commands.command()
    @commands.guild_only()
    async def lsar(self, ctx, page_num=1):
        """Lists self-assignable roles (type `;lsar <page number>` to view other pages, example: `;lsar 2`)."""
        if not ctx.guild:
            return
        roles_list = []
        config = self.bot.db['SAR'].setdefault(str(ctx.guild.id), {'0': []})
        for group in config.copy():
            if len(config[group]) == 0:
                del config[group]
        groups = sorted([int(key) for key in config])
        groups = [str(i) for i in groups]
        for group in groups:
            for role in config[group]:
                roles_list.append((group, role))
        role_list_str = f"**There are {len(roles_list)} self-assignable roles**\n"
        if len(roles_list) == 1:
            role_list_str = role_list_str.replace('roles', 'role').replace('are', 'is')
        current_group = ''
        try:
            current_group = roles_list[20 * (page_num - 1)][0]
            role_list_str += f"⟪Group {current_group}⟫\n"
        except IndexError:
            pass

        for role_tuple in roles_list[20 * (page_num - 1):20 * page_num]:
            if current_group != role_tuple[0]:
                current_group = groups[groups.index(current_group) + 1]
                role_list_str += f"\n⟪Group {current_group}⟫\n"

            role = ctx.guild.get_role(role_tuple[1])
            if not role:
                await ctx.send(f"Couldn't find role with ID {role_tuple[1]}. Removing from self-assignable roles.")
                config[current_group].remove(role_tuple[1])
                continue
            role_list_str += f"⠀{role.name}\n"

        emb = discord.Embed(description=role_list_str, color=discord.Color(int('00ff00', 16)))
        num_of_pages = (len(roles_list) // 20) + 1
        footer_text = f"{page_num} / {num_of_pages}"
        if page_num <= num_of_pages:
            footer_text += f" ・ (view the next page: ;lsar {page_num + 1})"
        emb.set_footer(text=footer_text)
        await utils.safe_send(ctx, embed=emb)

    @commands.command(hidden=True)
    @commands.bot_has_permissions(send_messages=True, embed_links=True, manage_roles=True)
    async def i(self, ctx, *, role_name):
        if role_name[:2] == 'am':
            await ctx.invoke(self.iam, role_name=role_name[3:])

    @staticmethod
    def iam_find_role(ctx, r_name):
        r_name = r_name.casefold()
        found_role: Optional[discord.Role] = discord.utils.find(lambda r: r.name.casefold() == r_name, ctx.guild.roles)
        if not found_role:
            if 3 <= len(r_name):
                found_role = discord.utils.find(lambda r: r.name.casefold().startswith(r_name), ctx.guild.roles)
                if not found_role:
                    if 3 <= len(r_name) <= 6:
                        found_role = discord.utils.find(lambda r: LDist(r.name.casefold()[:len(r_name)], r_name) <= 1,
                                                        ctx.guild.roles)
                    elif 6 < len(r_name):
                        found_role = discord.utils.find(lambda r: LDist(r.name.casefold()[:len(r_name)], r_name) <= 3,
                                                        ctx.guild.roles)
        return found_role

    @commands.command(aliases=['im'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True, manage_roles=True)
    @commands.guild_only()
    async def iam(self, ctx, *, role_name):
        """Command used to self-assign a role. Type `;iam <role name>`. Type `;lsar` to see the list of roles.

        You can also just type the beginning of a role name and it will find it. You can also slightly misspel it.

        Example: `;iam English`"""
        if not ctx.guild:
            return
        if str(ctx.guild.id) not in self.bot.db['SAR']:
            return
        config = self.bot.db['SAR'][str(ctx.guild.id)]
        role_name = role_name.casefold()
        found_role = self.iam_find_role(ctx, role_name)
        if not found_role:
            await utils.safe_send(ctx,
                               embed=utils.red_embed(f"**{str(ctx.author)}** No role found"))
            return

        if found_role in ctx.author.roles:
            await utils.safe_send(ctx, embed=utils.red_embed(f"**{str(ctx.author)}** "
                                                       f"You already have that role"))
            return

        for group in config:
            for role_id in config[group]:
                if found_role.id == role_id:
                    try:
                        await ctx.author.add_roles(found_role)
                    except discord.Forbidden:
                        await utils.safe_send(ctx, "Sorry, I could not add roles to that user!")
                        return
                    await utils.safe_send(ctx, embed=utils.green_embed(
                        f"**{str(ctx.author)}** You now have"
                        f" the **{found_role.name}** role."))
                    return

    @commands.command(aliases=['iamn', '!iam'])
    @commands.guild_only()
    @commands.bot_has_permissions(send_messages=True, embed_links=True, manage_roles=True)
    async def iamnot(self, ctx, *, role_name):
        """Command used to remove a self-assigned role"""
        if str(ctx.guild.id) not in self.bot.db['SAR']:
            return
        config = self.bot.db['SAR'][str(ctx.guild.id)]

        found_role = self.iam_find_role(ctx, role_name)
        if not found_role:
            await utils.safe_send(ctx,
                               embed=utils.red_embed(f"**{str(ctx.author)}** No role found"))
            return

        if found_role not in ctx.author.roles:
            await utils.safe_send(ctx, embed=utils.red_embed(f"**{str(ctx.author)}** "
                                                       f"You don't have that role"))
            return

        for group in config:
            for role_id in config[group]:
                if found_role.id == role_id:
                    await ctx.author.remove_roles(found_role)
                    await utils.safe_send(ctx,
                                       embed=utils.green_embed(
                                           f"**{str(ctx.author)}** You no longer have "
                                           f"the **{found_role.name}** role."))
                    return

        await utils.safe_send(ctx, embed=utils.red_embed(f"**{str(ctx.author)}** That role is not "
                                                   f"self-assignable."))

    @commands.command(aliases=['vmute', 'vm'])
    @hf.is_voicemod()
    @commands.bot_has_permissions(manage_roles=True, embed_links=True)
    async def voicemute(self, ctx, *, args):
        """Mutes a user.  Syntax: `;voicemute [time] <member> [reason]`.
        Example: `;voicemute 1d2h 12345678901234567`"""
        # This tag will signify to Rai that it should treat the command as a voice mute
        invisible_character = "⠀"
        args = f"{invisible_character}voice_mute_tag{invisible_character}" + args
        print('args in voice mute: ', args)
        await ctx.invoke(self.bot.get_command('mute'), args=args)

        return

    @commands.command(aliases=['vum', 'vunmute'])
    @hf.is_voicemod()
    @commands.bot_has_permissions(manage_roles=True, embed_links=True)
    async def voiceunmute(self, ctx, target_in, guild=None):
        """Unmutes a user"""
        if not guild:
            guild = ctx.guild
            target: discord.Member = await utils.member_converter(ctx, target_in)
        else:
            guild = self.bot.get_guild(int(guild))
            target: discord.Member = guild.get_member(int(target_in))
        try:
            config = self.bot.db['voice_mutes'][str(guild.id)]
        except IndexError:
            return
        role = guild.get_role(config['role'])

        failed = False
        if target:
            target_id = target.id
            try:
                await target.remove_roles(role)
                failed = False
            except discord.HTTPException:
                pass

        else:
            if ctx.author == ctx.bot.user:
                target_id = target_in
            else:
                return

        if str(target_id) in config['timed_mutes']:
            del config['timed_mutes'][str(target_id)]

        if ctx.author != ctx.bot.user:
            emb = discord.Embed(description=f"**{str(target)}** has been unmuted.",
                                color=discord.Color(int('00ffaa', 16)))
            await utils.safe_send(ctx, embed=emb)

        if not failed:
            return True

    @commands.command(aliases=['selfmute', 'sm'])
    @commands.bot_has_permissions(send_messages=True)
    @commands.guild_only()
    async def self_mute(self, ctx: commands.Context, time: Optional[str] = None):
        """Irreversible mutes yourself for a certain amount of time. Use like `;selfmute <amount of time>`.

        Examples:
        - `;selfmute 3h`   Mute yourself for three hours
        - `;selfmute 5d12h`    Mute yourself for 5d12h"""
        # redirect owner usage to owner.self_mute_owner()
        if ctx.author.id == self.bot.owner_id:
            owner_cog = self.bot.get_cog('Owner')
            if owner_cog:
                await owner_cog.self_mute_owner(ctx, time)
                return
        if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            await utils.safe_send(ctx, "This command works by manually deleting all the messages of the self-muted user, "
                                    "but Rai currently lacks the `Manage Messages` permission, so you can't use this "
                                    "command.")
            return

        if ctx.guild.id == JP_SERVER_ID:
            # check if ctx.author's highest role is higher than Rai's, and only if then, allow the command
            if ctx.author.top_role < ctx.guild.me.top_role:
                await utils.safe_send(ctx, "Please use Ciri's version of that command in this server: "
                                        "`,selfmute` or `,sm`.")
                return

        if ctx.channel.id != 247135634265735168 and ctx.guild.id == SP_SERVER_ID:
            await utils.safe_reply(ctx, "Please use the selfmute command in the bot channel: "
                                       "<#247135634265735168>")
            return

        if time:
            try:
                if self.bot.db['selfmute'][str(ctx.guild.id)][str(ctx.author.id)]['enable']:
                    await utils.safe_send(ctx, "You're already muted. No saving you now.")
                    return
            except KeyError:
                pass
        else:
            await utils.safe_send(ctx, "You need to put something! Please give a length of time like 3d, 2h, 5d2h, 5m.")
            return

        if neg := time.startswith("-"):  # negative time
            time = time[1:]  # remove negative sign
        try:
            time_string, length = hf.parse_time(f"{time}")  # length = [days, hours, minutes]
        except OverflowError:
            await utils.safe_reply(ctx, "You chose way too big of a number! Please choose a smaller one.")
            return
        if not time_string:
            await ctx.message.reply("Please give a length of time like 3d, 2h, 5d2h, 5m.")
            return
        delta_obj = timedelta(days=length[0], hours=length[1], minutes=length[2])
        if neg:
            unmute_time = discord.utils.utcnow() - delta_obj
        else:
            unmute_time = discord.utils.utcnow() + delta_obj
        if not neg and delta_obj.total_seconds() > 28 * 24 * 60 * 60:  # if length is longer than 28d
            await utils.safe_send(ctx, "Please choose a time less than 28d")
            return

        delta_str = format_interval(delta_obj)  # remove last space

        if not neg:
            conf_msg = (f"You are about to irreversibly mute yourself for {delta_str}. "
                        f"Is this really what you want to do? The mods of this server CANNOT undo "
                        f"this.\nType 'Yes' to confirm.")
        else:
            delta_str = "-" + delta_str
            conf_msg = (f"You are about to irreversibly mute yourself for... {delta_str}? You want to mute yourself "
                        f"for negative time? Well, the mods of the server cannot undo this. Type 'yes' to confirm.")
        conf = await utils.safe_reply(ctx.message, conf_msg)

        msg = ctx.message
        try:
            msg = await self.bot.wait_for('message',
                                          timeout=15,
                                          check=lambda m: m.author == ctx.author and m.channel == ctx.channel)

            if msg.content.casefold() == 'yes':  # confirm
                config = self.bot.db['selfmute'].setdefault(str(ctx.guild.id), {})
                if neg:
                    delta_obj = timedelta(seconds=0.5)  # unmute after 3 seconds
                timestamp = int(unmute_time.timestamp())

                try:
                    await ctx.author.timeout(delta_obj, reason="RAI_SELFMUTE")
                except (discord.Forbidden, discord.HTTPException):
                    config[str(ctx.author.id)] = {'enable': True, 'time': timestamp}  # someone who Rai couldn't timeout

                await conf.reply(f"Muted {ctx.author.display_name} for {delta_str}. This is irreversible.\n"
                                 f"Unmute time: <t:{timestamp}> (<t:{timestamp}:R>)")

            elif msg.content.casefold() in ['no', 'cancel']:
                raise asyncio.TimeoutError

        except asyncio.TimeoutError:
            await utils.safe_reply(msg, "Canceling.")
            return

    @commands.command(hidden=True, aliases=['pingmods'])
    @commands.check(lambda ctx: ctx.guild.id in [SP_SERVER_ID, RY_SERVER_ID] if ctx.guild else False)
    async def pingstaff(self, ctx):
        """Puts a `@here` ping into the staff channel with a link to your message"""
        channel = self.bot.get_channel(self.bot.db['mod_channel'][str(ctx.guild.id)])
        desc_text = f"Staff has been pinged in {ctx.channel.mention} [here]({ctx.message.jump_url}) by " \
                    f"{ctx.author.mention}."
        if len(ctx.message.content.split()) > 1:
            desc_text += f"\n\nMessage content: {' '.join(ctx.message.content.split()[1:])}"

        emb = utils.green_embed(desc_text)
        notif: Optional[discord.Message] = await channel.send("@here", embed=emb)

        try:
            await ctx.message.add_reaction("📨")
        except (discord.Forbidden, discord.NotFound):
            pass

        if hasattr(self.bot, 'synced_reactions'):
            self.bot.synced_reactions.append((notif, ctx.message))
        else:
            self.bot.synced_reactions = [(notif, ctx.message)]

    @commands.max_concurrency(1, commands.BucketType.channel)
    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.command()
    async def timer(self, ctx, time_left=0):
        """Starts a countdown. The `time_left` offset must be set to 30 seconds or 1, 2, 3, 4, 5 minutes.
        It will update the timer every second."""
        time_left = int(time_left)
        if time_left not in [1, 2, 3, 4, 5, 30]:
            await utils.safe_send(ctx, "Please choose any of the following values to set your timer: \n"
                                    "• Seconds: *30*\n"
                                    "• Minutes: *1*, *2*, *3*, *4* or *5* \n"
                                    "For example: `;timer 5`.")
            return

        if time_left == 30:
            time_str = f"{time_left}s"
        else:  # time is a number of minutes 1-5
            time_str = f"{time_left}min"
            time_left = time_left * 60

        embed = utils.green_embed(f"The countdown of **{time_str}** set up by "
                               f"{ctx.author.mention} **will start in: 5s**.")
        msg_countdown = await utils.safe_send(ctx, embed=embed)

        for a in range(4, -1, -1):
            await asyncio.sleep(1)
            embed.description = f"The countdown of **{time_str}** set up by {ctx.author.mention} " \
                                f"**will start in: {a}s**."
            try:
                await msg_countdown.edit(embed=embed)
            except discord.NotFound:
                return

        await msg_countdown.add_reaction('❌')
        await msg_countdown.add_reaction('↩')
        await msg_countdown.add_reaction('🔟')

        def check_reactions(reaction: discord.Reaction, user: discord.User) -> bool:
            return str(reaction) in '❌↩🔟' and user.id == ctx.author.id and reaction.message.id == msg_countdown.id

        time_left_backup = time_left

        # Countdown:
        aborted = False
        restarted = False
        added_seconds = False
        while time_left:
            mins, secs = divmod(time_left, 60)
            time_left_str = f"{mins}:{secs:02d}"
            if restarted:
                embed_text = f"The countdown of **{time_str}** set up by {ctx.author.mention} **has been restarted**." \
                             f"\n\nTime left: `{time_left_str}`"
            elif added_seconds:
                embed_text = f"The countdown of **{time_str}** set up by {ctx.author.mention} **is already running**!" \
                             f"\n\nTime left: `{time_left_str}`. Ten seconds added!"
            else:  # Normal operation
                embed_text = f"The countdown of **{time_str}** set up by {ctx.author.mention} **is already running**!" \
                             f"\n\nTime left: `{time_left_str}`"

            embed_countdown = utils.green_embed(embed_text)
            try:
                await msg_countdown.edit(embed=embed_countdown)
            except discord.NotFound:
                return

            try:
                reaction_added, user_react = await self.bot.wait_for("reaction_add", check=check_reactions, timeout=1)
            except asyncio.TimeoutError:
                time_left -= 1  # Restart loop
            else:
                if str(reaction_added) == '❌':
                    print("oops", reaction_added.message.content, reaction_added.message.author)
                    aborted = True
                    time_left = 0

                if str(reaction_added) == "↩":
                    restarted = True

                    try:
                        await msg_countdown.remove_reaction("↩", ctx.author)
                    except (discord.Forbidden, discord.NotFound):
                        pass

                    time_left = time_left_backup

                if str(reaction_added) == "🔟":
                    added_seconds = True

                    try:
                        await msg_countdown.remove_reaction("🔟", ctx.author)
                    except (discord.Forbidden, discord.NotFound):
                        pass

                    time_left = time_left + 10
                    if time_left > 60 * 5:
                        time_left = 60 * 5  # Don't let timer go over 5 mins

        if aborted:
            text_end = f"The countdown of **{time_str}** set up by {ctx.author.mention} **has been aborted**."
        else:
            text_end = f"The countdown of **{time_str}** set up by {ctx.author.mention} **has finished**!\n\nTime out!"

        embed_end = utils.green_embed(text_end)
        embed_end.set_footer(text="Command made by Fede#5370")

        try:
            await msg_countdown.edit(embed=embed_end)
        except discord.NotFound:
            return

        try:
            await msg_countdown.clear_reactions()
        except (discord.Forbidden, discord.NotFound):
            return

    @app_commands.command(name="time")
    @app_commands.describe(time_str="Input a date in any format (example: Jan. 23rd, 2012, 2014 feb 2 9:20am, now, "
                                    "today, ...)")
    @app_commands.choices(format_option=[
        app_commands.Choice(name='Short Time (9:41 PM)', value='t'),
        app_commands.Choice(name='Long Time (9:41:30 PM)', value='T'),
        app_commands.Choice(name='Short Date (2021/06/30)', value='d'),
        app_commands.Choice(name='Long Date (June 30 2021)', value='D'),
        app_commands.Choice(name='Short Date+Time (June 30 2021, 9:41 PM)', value='f'),
        app_commands.Choice(name='Long Date+Time (Wednesday, June 30, 2021, 9:41 PM)', value='F'),
        app_commands.Choice(name='Relative (2 months ago, in an hour, in five years)', value='R'),
    ])
    async def time_fmt(self, 
                       itx: discord.Interaction, 
                       time_str: str, 
                       format_option: app_commands.Choice[str] = 'f') -> None:
        """
        Returns a Discord-formatted date string representing the date you input (defaults to UTC).

        You can input something like "January 23rd, 2014", or also the special keyword "Now" or "Today".
        """
        date = parse(time_str, settings={'TIMEZONE': 'UTC', 'RETURN_AS_TIMEZONE_AWARE': True})
        # if not date.tzinfo:
        #     date = date.replace(tzinfo=timezone.utc)
        if not date:
            await itx.response.send_message("I failed to interpret your date string. Please try again.", 
                                            ephemeral=True)
            return

        if type(format_option) == str:
            format = format_option
        else:
            format = format_option.value

        date_str = f"<t:{int(date.timestamp())}:{format}>"
        await itx.response.send_message(date_str, ephemeral=True)
        await itx.followup.send(f"`{date_str}`", ephemeral=True)

    @commands.command(hidden=True)
    async def done(self, ctx: commands.Context):
        """Marks a post as done"""
        if not isinstance(ctx.channel, discord.Thread):
            return

        if not isinstance(ctx.channel.parent, discord.ForumChannel):
            return

        if len(ctx.channel.applied_tags or []) == 5:
            await ctx.message.reply("This post has five tags already. Please remove one tag then try "
                                    "to type `;done` again.")
            return

        for tag in ctx.channel.parent.available_tags:
            if str(tag.emoji) == "✅":
                await ctx.channel.add_tags(tag)

        await ctx.message.add_reaction("✅")
        # temporarily lock for one minute to prevent OP from accidentally opening their closed thread
        await ctx.channel.edit(archived=True, locked=True)

    @commands.command()
    @commands.check(doneq_check)
    async def doneq(self, ctx: commands.Context):
        """Posts a text asking if the OP of a forum post is done with their question, prompting them to type `;done`"""
        msg = f"{ctx.channel.owner.mention}\nJust as a reminder, once you're satisfied with the responses you've " \
              f"received in this thread, please type `;done` below this message! Otherwise, if you'd still like to " \
              f"wait for more responses, please feel free to keep this post open."
        try:
            await utils.safe_send(ctx.channel, msg)
        except (discord.Forbidden, discord.HTTPException):
            pass

        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.command(hidden=True)
    @commands.check(lambda ctx: ctx.author.id in [216848576549093376, 354352443502493706, 202995638860906496,
                                                  698304824667537458, 371093267410059264]
                                and ctx.guild.id == SP_SERVER_ID if ctx.guild else False)
    async def admin(self, ctx):
        """Allows chosen users to add/remove admin role"""
        # Current users: Jaleel, Evil, Ryan, Jelly, Rize
        admin_role = ctx.guild.get_role(243854949522472971)
        if admin_role in ctx.author.roles:
            await ctx.author.remove_roles(admin_role)
            await ctx.message.add_reaction('❌')
        else:
            await ctx.author.add_roles(admin_role)
            await ctx.message.add_reaction('✅')


async def setup(bot):
    await bot.add_cog(General(bot))
