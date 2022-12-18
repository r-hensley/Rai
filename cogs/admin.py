import asyncio
import os
import re
from datetime import datetime, timezone
from sre_constants import error as sre_constants_error
from typing import Optional, List

import aiohttp
import discord
import io
from discord.ext import commands

from .utils import helper_functions as hf
from .utils.timeutil import format_interval

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
JP_SERVER_ID = 189571157446492161
SP_SERVER_ID = 243838819743432704
RYRY_SPAM_CHAN = 275879535977955330


class Admin(commands.Cog):
    """Stuff for admins. Commands in this module require either the mod role set by `;set_mod_role` or the\
    Administrator permission."""

    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.modlog = bot.get_command('modlog')

    async def cog_check(self, ctx):
        if not ctx.guild:
            return
        if str(ctx.guild.id) not in self.bot.db['mod_channel'] and ctx.command.name != 'set_mod_channel':
            return
        return hf.admin_check(ctx)

    async def bot_check(self, ctx):
        if not ctx.guild:
            return True
        if str(ctx.guild.id) in self.bot.db['modsonly']:
            if self.bot.db['modsonly'][str(ctx.guild.id)]['enable']:
                if not hf.admin_check(ctx):
                    return
        return True

    @commands.group(invoke_without_command=True, aliases=['rr', 'reactionroles'])
    @commands.bot_has_permissions(embed_links=True, manage_roles=True)
    async def reaction_roles(self, ctx, *, args=''):
        """The setup command for reaction roles. If you type just `;rr`, you'll be taken through a guide for setting \
        up one role."""
        inputs = []
        if len(args) == 0:  # take a user through the slow guide menu
            x = await self.reaction_roles_guide(ctx)
            if not x:
                return
            inputs.append(x)
        else:  # a user inputs all three necessary arguments
            for i_input in args.split('\n'):
                if len(i_input.split()) < 3:
                    await hf.safe_send(ctx, "One of your lines didn't have enough arguments. Please check "
                                            "the help command.")
                    return
                x = i_input.split()
                x = await self.quick_reaction_roles(ctx, x[0], x[1], ' '.join(x[2:]))
                if not x:
                    return
                inputs.append(x)

        config = self.bot.db['reactionroles'].setdefault(str(ctx.guild.id), {})
        msg_emoji_dict = {}
        for i_input in inputs:
            reaction_msg = i_input[0]
            emoji = i_input[1]
            role = i_input[2]

            if reaction_msg in msg_emoji_dict:
                msg_emoji_dict[reaction_msg].append(emoji)
            else:
                msg_emoji_dict[reaction_msg] = [emoji]

            if type(emoji) in [discord.Emoji, discord.PartialEmoji]:
                emoji_str = str(emoji.id)  # a discord emoji
            else:
                emoji_str = emoji  # a str unicode emoji

            config.setdefault(str(reaction_msg.id), {})[emoji_str] = role.id

        for i_message in msg_emoji_dict:
            try:
                await i_message.add_reaction(*[i for i in msg_emoji_dict[i_message]])
            except discord.Forbidden:
                await hf.safe_send(ctx, "I lack permissions to add reactions. Please attach your emojis to the "
                                        "target message yourself.")
        try:
            await ctx.message.add_reaction('✅')
        except (discord.NotFound, discord.HTTPException):
            pass

    @staticmethod
    async def get_reaction_msg(ctx, text):
        msg_id = re.findall(r'^\d{17,22}$', text)
        if msg_id:
            msg_id = msg_id[0]
        else:
            await hf.safe_send(ctx, f"{text} is an invalid response. Please make sure to only respond with a message "
                                    "ID that looks like 708540770323529758. Please start over.")
            return

        try:
            return await ctx.channel.fetch_message(msg_id)
        except discord.NotFound:
            await hf.safe_send(ctx, f"I was not able to find the message you linked to with {text}. Make sure it is a"
                                    " message in this channel. Please start over.")
            return

    @staticmethod
    async def get_role(ctx, text):
        role_id = re.findall(r'^<@&(\d{17,22})>$', text)  # a mention like <@&380195245071138816>
        if role_id:
            role_id = int(role_id[0])
        else:
            role_id = re.findall(r'^\d{17,22}$', text)  # only the ID like 380195245071138816
            if role_id:
                role_id = int(role_id[0])
            else:  # gives the name of the role in text
                role: Optional[discord.Role] = discord.utils.find(lambda r: r.name == text, ctx.guild.roles)
                if not role:
                    await hf.safe_send(ctx, f"I couldn't find the role {text} you were looking for. Please start over.")
                    return
                else:
                    return role
        if role_id:
            role = ctx.guild.get_role(role_id)
            if not role:
                await hf.safe_send(ctx, f"I couldn't find the role of {text}. Please start over.")
                return
            return role

    async def reaction_roles_guide(self, ctx):  # returns 1) reaction_msg 2) emoji 3) role
        # ########### STEP 1: MSG_ID ################# # gives "reaction_msg"
        emb = hf.green_embed("First, please paste the `message id` of the reaction roles message. It must be a "
                             "message in this channel. Example: `708540770323529758`")
        emb.title = "Reaction Roles - Step 1"
        msg = await hf.safe_send(ctx, embed=emb)

        try:
            resp = await self.bot.wait_for('message', check=lambda m: m.author.id == ctx.author.id, timeout=60.0)
        except asyncio.TimeoutError:
            await hf.safe_send(ctx, "Message timed out. Please start over.")
            return

        try:
            await resp.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

        reaction_msg = await self.get_reaction_msg(ctx, resp.content)
        if not reaction_msg:
            return

        # ############## STEP 2: EMOJI ###################  # gives "emoji"
        emb = hf.green_embed("Next, please react to this message with the emoji you wish to associate with your "
                             "reaction role. It must be an emoji from a guild I have access to.")
        emb.title = "Reaction Roles - Step 2"
        await msg.edit(embed=emb)

        try:
            reaction, _ = await self.bot.wait_for('reaction_add',
                                                  check=lambda r, u: u.id == ctx.author.id and r.message.id == msg.id,
                                                  timeout=60.0)
        except asyncio.TimeoutError:
            await hf.safe_send(ctx, "Message timed out. Please start over.")
            return
        emoji = reaction.emoji

        # ############## STEP 3: ROLE NAME ################# # gives "role"
        emb = hf.green_embed("Finally, please ping or write the ID or name of the role you wish to give.")
        emb.title = "Reaction Roles - Step 3"
        await msg.edit(embed=emb)

        try:
            resp = await self.bot.wait_for('message', check=lambda m: m.author.id == ctx.author.id, timeout=60.0)
        except asyncio.TimeoutError:
            await hf.safe_send(ctx, "Message timed out. Please start over.")
            return

        try:
            await resp.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

        role = await self.get_role(ctx, resp.content)
        if not role:
            return

        # ############## FINISHED #######################
        emb = hf.green_embed("Finished! You can now delete all messages except for the message you selected as your "
                             "reaction roles message.\n\nIn the future, you can speed up this process by using this "
                             f"command in the pattern of `;rr <reaction_msg_id> <emoji> <role_id_mention_or_name>`.\n\n"
                             f"For you, that would've been: `;rr {reaction_msg.id} {str(emoji)} {role.id}`. You can "
                             f"also do this for multiple roles in one command, just add new lines between each new "
                             f"emoji you want to add.")
        await msg.edit(embed=emb)

        return reaction_msg, emoji, role

    async def quick_reaction_roles(self, ctx, reaction_msg, emoji, role):
        # ######### reaction_msg ########
        reaction_msg = await self.get_reaction_msg(ctx, reaction_msg)
        if not reaction_msg:
            return

        # ######## emoji #############
        if len(emoji) == 1:
            if hf.generous_is_emoji(emoji):
                pass
            else:
                await hf.safe_send(ctx, f"I couldn't detect your emoji {emoji}. Please start over.")
                return
        else:
            emoji_id = re.findall(r'^<:\w+:(\d{17,22})>$', emoji)
            if not emoji_id:
                await hf.safe_send(ctx, f"I couldn't detect your emoji {emoji}. Please start over.")
                return
            emoji = self.bot.get_emoji(int(emoji_id[0]))
            if not emoji:
                await hf.safe_send(ctx, f"I couldn't find the emoji {emoji} in any of my servers. Please start over.")
                return
        # ######## role ###########
        role = await self.get_role(ctx, role)
        if not role:
            return
        # ############ finished ################
        return reaction_msg, emoji, role

    @commands.group(invoke_without_command=True, aliases=['voicemods'])
    async def voicemod(self, ctx, *, user):
        """Sets a voice mod. Type `;voicemod <user/ID>`."""
        config = self.bot.db['voicemod']
        if str(ctx.guild.id) not in config:
            return
        user = await hf.member_converter(ctx, user)
        config2 = config[str(ctx.guild.id)]
        if not user:
            return
        if user.id in config2:
            await hf.safe_send(ctx, embed=hf.red_embed(f"{user.mention} is already a voice mod."))
            return
        config2.append(user.id)
        await hf.safe_send(ctx, embed=hf.green_embed(f"{user.mention} is now a voice mod."))

    @voicemod.command(name="list")
    async def voicemod_list(self, ctx):
        """Lists the current voicemods"""
        config = self.bot.db['voicemod']
        if str(ctx.guild.id) not in config:
            return
        mod_ids = config[str(ctx.guild.id)]
        mods = []
        for mod_id in mod_ids:
            mod = await hf.member_converter(ctx, mod_id)
            if mod:
                mods.append(f"{mod.mention} ({mod.name})")
            else:
                try:
                    user = await self.bot.fetch_user(mod_id)
                except discord.NotFound:
                    continue
                await hf.safe_send(ctx, f"Could not find {user.name} ({mod_id}), so I'm removing them from the list.")
                config[str(ctx.guild.id)].remove(mod_id)
        list_of_mods = '\n'.join(mods)
        await hf.safe_send(ctx, embed=hf.green_embed(f"__List of voice mods__\n{list_of_mods}"))

    @voicemod.command(name="remove")
    async def voicemod_remove(self, ctx, *, user):
        """Removes a voice mod. Type `;voicemod remove <user/ID>`."""
        config = self.bot.db['voicemod']
        if str(ctx.guild.id) not in config:
            return
        user = await hf.member_converter(ctx, user)
        config2 = config[str(ctx.guild.id)]
        if not user:
            return
        if user.id not in config2:
            await hf.safe_send(ctx, embed=hf.red_embed(f"{user.mention} is not a voice mod."))
            return
        config2.remove(user.id)
        await hf.safe_send(ctx, embed=hf.green_embed(f"{user.mention} is no longer a voice mod."))

    @commands.command(aliases=['mutes', 'incidents', 'ai'])
    @commands.bot_has_permissions(embed_links=True)
    async def activeincidents(self, ctx):
        """Lists the current active incidents (timed mutes and bans)"""
        mutes: List[dict] = []
        author: Optional[discord.User] = None
        try:
            mute_config = self.bot.db['mutes'][str(ctx.guild.id)]['timed_mutes']
        except KeyError:
            return
        else:
            for user_id in mute_config:
                modlog = self.bot.db['modlog'][str(ctx.guild.id)][user_id]
                reason = "Unknown"
                author = None
                for incident in modlog[::-1]:
                    if incident['type'] == "Mute":
                        reason = incident['reason']
                        sju = incident['jump_url'].split('/')  # split jump url
                        message = await self.bot.get_channel(int(sju[-2])).fetch_message(int(sju[-1]))
                        author = message.author
                        break
                mutes.append({'id': user_id, 'type': 'Mute', 'until': mute_config[user_id], 'reason': reason,
                              'author': author})

        embed_text = "__Current Mutes__\n"
        for mute in mutes:
            member = await hf.member_converter(ctx, mute['id'])
            if member:
                member_text = f"{member.mention} ({member.id})"
            else:
                try:
                    user = await self.bot.fetch_user(mute['id'])
                except discord.NotFound:
                    continue
                member_text = f"{user.name} ({user.id})"
            interval = (datetime.strptime(mute['until'], "%Y/%m/%d %H:%M UTC")
                        .replace(tzinfo=timezone.utc) - discord.utils.utcnow())
            interval_str = format_interval(interval)
            embed_text += f"• {member_text}\n" \
                          f"Until {mute['until']} (in {interval_str})\n" \
                          f"{mute['reason']} (by {author.name})\n"
        await hf.safe_send(ctx, embed=hf.green_embed(embed_text))

    @commands.command(aliases=['baibairai'])
    async def modsonly(self, ctx):
        """Sets Rai to ignore commands from users."""
        config = self.bot.db['modsonly']
        if str(ctx.guild.id) in config:
            config[str(ctx.guild.id)]['enable'] = not config[str(ctx.guild.id)]['enable']
        else:
            config[str(ctx.guild.id)] = {'enable': True}
        value = config[str(ctx.guild.id)]['enable']
        if value:
            try:
                await ctx.send("Rai will now only respond to commands from mods. "
                               "Type `;modsonly` again to disable this.")
            except discord.Forbidden:
                pass
        else:
            try:
                await ctx.send("Rai will now respond to all users.")
            except discord.Forbidden:
                pass

    @commands.command(hidden=True)
    async def crosspost(self, ctx):
        """Makes Rai crosspost all your ban audits"""
        if not ctx.guild:
            return
        if ctx.author not in ctx.bot.get_guild(257984339025985546).members:
            return
        if str(ctx.guild.id) in self.bot.db['bans']:
            config = self.bot.db['bans'][str(ctx.guild.id)]
            try:
                config['crosspost'] = not config['crosspost']
            except KeyError:
                config['crosspost'] = True
        else:
            config = self.bot.db['bans'][str(ctx.guild.id)] = {'enable': False, 'channel': None, 'crosspost': True}
        if config['crosspost']:
            await hf.safe_send(ctx, "Rai will now crosspost ban logs")
        else:
            await hf.safe_send(ctx, "Rai won't crosspost ban logs anymore")

    @commands.command(hidden=True)
    async def echo(self, ctx, *, content: str):
        """Sends back whatever you send. Usage: `;echo <text>`"""
        try:
            await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        await hf.safe_send(ctx, content)

    @commands.command(hidden=True)
    async def post_rules(self, ctx):
        """Posts the rules page on the Chinese/Spanish server. See my personal server with `;ryry` for more \
        instructions."""
        if ctx.channel.id in [511097200030384158, 450170164059701268]:  # chinese server
            download_link = 'https://docs.google.com/document/u/0/export?format=txt' \
                            '&id=159L5Z1UEv7tJs_RurM1-GkoZeYAxTpvF5D4n6enqMuE' \
                            '&token=AC4w5VjkHYH7R7lINNiyXXfX29PlhW8qfg%3A1541923812297' \
                            '&includes_info_params=true'
            channel = 0
        elif ctx.channel.id in [243859172268048385, 513222365581410314]:  # english rules
            download_link = 'https://docs.google.com/document/export?format=txt' \
                            '&id=1kOML72CfGMtdSl2tNNtFdQiAOGMCN2kZedVvIHQIrw8' \
                            '&token=AC4w5Vjrirj8E-5sNyCUvJOAEoQqTGJLcA%3A1542430650712' \
                            '&includes_info_params=true'
            channel = 1
        elif ctx.channel.id in [499544213466120192, 513222453313667082]:  # spanish rules
            download_link = 'https://docs.google.com/document/export?format=txt' \
                            '&id=12Ydx_5M6KuO5NCfUrSD1P_eseR6VJDVAgMfOntJYRkM' \
                            '&token=AC4w5ViCHzxJBaDe7nEOyBL75Tud06QVow%3A1542432513956' \
                            '&includes_info_params=true'
            channel = 2
        else:
            return

        async for message in ctx.channel.history(limit=30):
            try:
                await message.delete()
            except discord.NotFound:
                pass
            except discord.Forbidden:
                await hf.safe_send(ctx, "I was unable to delete the old messages!")
                return
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(download_link) as resp:
                    response = resp
                    rules = await resp.text(encoding='utf-8-sig')
        except (aiohttp.InvalidURL, aiohttp.ClientConnectorError):
            await hf.safe_send(ctx, f'invalid_url:  Your URL was invalid ({download_link})')
            return
        if response.status != 200:
            await hf.safe_send(ctx, f'html_error: Error {resp.status}: {resp.reason} ({download_link})')
            return
        rules = rules.replace('__', '').replace('{und}',
                                                '__')  # google uses '__' page breaks so this gets around that
        rules = rules.split('########')
        index = 0
        jump_links = {}
        for page in rules:
            if page[0:6] == '!image':
                url = page.split(' ')[1].replace('\r', '').replace('\n', '')
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url) as resp:
                            buffer = io.BytesIO(await resp.read())
                except (aiohttp.InvalidURL, aiohttp.ClientConnectorError):
                    await hf.safe_send(ctx, f'invalid_url:  Your URL was invalid ({url})')
                    return
                if response.status != 200:
                    await hf.safe_send(ctx, f'html_error: Error {response.status}: {response.reason} ({url})')
                    return
                msg = await ctx.send(file=discord.File(buffer, filename="image.png"))
            elif page[:30].replace('\r', '').replace('\n', '').startswith('!lang'):
                spanishnative = self.bot.get_emoji(524733330525257729)
                englishnative = self.bot.get_emoji(524733316193058817)
                othernative = self.bot.get_emoji(524733977991315477)
                fluentspanish = self.bot.get_emoji(524732626674909205)
                fluentenglish = self.bot.get_emoji(524732533775007744)
                mods = self.bot.get_emoji(524733987092955138)
                post = page.replace('{spanishnative}', str(spanishnative)). \
                    replace('{englishnative}', str(englishnative)). \
                    replace('{othernative}', str(othernative)). \
                    replace('{fluentspanish}', str(fluentspanish)). \
                    replace('{fluentenglish}', str(fluentenglish)). \
                    replace('{mods}', str(mods))
                msg = await hf.safe_send(ctx, post[7:])
            elif page[:30].replace('\r', '').replace('\n', '').startswith('!roles'):
                if channel == 0:  # chinese
                    emoji = self.bot.get_emoji(358529029579603969)  # blobflags
                    post = page[8:].replace('{emoji}', str(emoji))
                    msg = await hf.safe_send(ctx, post)
                    self.bot.db['roles'][str(ctx.guild.id)]['message'] = msg.id
                    await msg.add_reaction("🔥")  # hardcore
                    await msg.add_reaction("📝")  # correct me
                    await msg.add_reaction("🗣")  # debate
                    await msg.add_reaction("🖋")  # handwriting
                    await msg.add_reaction("🎙")  # VC all
                    await msg.add_reaction('📖')  # book club
                elif channel == 1 or channel == 2:  # english/spanish
                    emoji = self.bot.get_emoji(513211476790738954)
                    post = page.replace('{table}', str(emoji))
                    msg = await hf.safe_send(ctx, post[8:])
                    await msg.add_reaction("🎨")
                    await msg.add_reaction("🐱")
                    await msg.add_reaction("🐶")
                    await msg.add_reaction("🎮")
                    await msg.add_reaction(emoji)  # table
                    await msg.add_reaction('🔥')
                    await msg.add_reaction("👪")
                    await msg.add_reaction("🎥")
                    await msg.add_reaction("🎵")
                    await msg.add_reaction("❗")
                    await msg.add_reaction("👚")
                    await msg.add_reaction("💻")
                    await msg.add_reaction("📔")
                    await msg.add_reaction("✏")
                    await msg.add_reaction('📆')
                    if channel == 1:
                        self.bot.db['roles'][str(ctx.guild.id)]['message1'] = msg.id
                    elif channel == 2:
                        self.bot.db['roles'][str(ctx.guild.id)]['message2'] = msg.id
                else:
                    await hf.safe_send(ctx, "Something went wrong")
                    return
            else:
                try:
                    msg = await hf.safe_send(ctx, page)
                except Exception as e:
                    await ctx.send(e)
                    raise
            if not msg:
                await hf.safe_send(ctx, "⠀\n⠀\n⠀\nThere was an error with one of your posts in the Google Doc.  Maybe "
                                        "check your usage of `########`.  Eight hashes means a new message.")
                return

            if channel == 0:
                if index == 3:
                    jump_links[0] = msg.jump_url
                elif index == 4:
                    jump_links[1] = msg.jump_url
                elif index == 5:
                    jump_links[2] = msg.jump_url
                elif index == 12:
                    jump_links[3] = msg.jump_url
                    jump_links[9] = msg.jump_url
                    jump_links[15] = msg.jump_url
                elif index == 2:
                    jump_links[4] = msg.jump_url
                    jump_links[10] = msg.jump_url
                    jump_links[16] = msg.jump_url
                elif index == 1:
                    jump_links[5] = msg.jump_url
                    jump_links[11] = msg.jump_url
                    jump_links[17] = msg.jump_url
                elif index == 6:
                    jump_links[6] = msg.jump_url
                elif index == 7:
                    jump_links[7] = msg.jump_url
                elif index == 8:
                    jump_links[8] = msg.jump_url
                elif index == 9:
                    jump_links[12] = msg.jump_url
                elif index == 10:
                    jump_links[13] = msg.jump_url
                elif index == 11:
                    jump_links[14] = msg.jump_url
            index += 1

            if '<@ &' in msg.content:
                await msg.edit(content=msg.content.replace('<@ &', '<@&'))
        if channel == 0:
            x = """⠀
:flag_tw: **台灣繁體**
• [伺服器規則](x0x)　
• [BOT指令](x1x)
• [常見問題](x2x)
• [身份組](x3x)
• [相關連結與 Discord 伺服器](x4x)
• [伺服器邀請連結](x5x)

:flag_cn: **大陆简体**
• [服务器规则](x6x)　
• [BOT指令](x7x)
• [常见问题](x8x)
• [身份组](x9x)
• [相关链接与 Discord 服务器](x10x)
• [服务器邀请链接](x11x)

:flag_gb: | :flag_us: **English**
• [Rules](x12x)　
• [Bot Commands](x13x)
• [FAQ](x14x)
• [Roles](x15x)
• [Useful Links & Servers](x16x)
• [Server Invite](x17x)
⠀"""
            for i in jump_links:
                x = x.replace(f"x{i}x", jump_links[i])
            await ctx.send(embed=hf.green_embed(x))

    @commands.group(invoke_without_command=True)
    async def captcha(self, ctx):
        """Sets up a checkmark requirement to enter a server"""
        await hf.safe_send(ctx,
                           'This module sets up a requirement to enter a server based on a user pushing a checkmark.  '
                           '\n1) First, do `;captcha toggle` to setup the module'
                           '\n2) Then, do `;captcha set_channel` in the channel you want to activate it in.'
                           '\n3) Then, do `;captcha set_role <role name>` '
                           'to set the role you wish to add upon them captchaing.'
                           '\n4) Finally, do `;captcha post_message` to post the message people will react to.')

    @captcha.command()
    @commands.bot_has_permissions(manage_roles=True)
    async def toggle(self, ctx):
        """Enable/disable the captcha post."""
        guild = str(ctx.guild.id)
        if guild in self.bot.db['captcha']:
            guild_config = self.bot.db['captcha'][guild]
            if guild_config['enable']:
                guild_config['enable'] = False
                await hf.safe_send(ctx, 'Captcha module disabled')
            else:
                guild_config['enable'] = True
                await hf.safe_send(ctx, 'Captcha module enabled')
        else:
            self.bot.db['captcha'][guild] = {'enable': True, 'channel': '', 'role': ''}
            await hf.safe_send(ctx, 'Captcha module setup and enabled.')

    @captcha.command(name="set_channel")
    async def captcha_set_channel(self, ctx):
        """Sets the channel that the captcha will be posted in."""
        guild = str(ctx.guild.id)
        if guild not in self.bot.db['captcha']:
            await self.toggle
        guild_config = self.bot.db['captcha'][guild]
        guild_config['channel'] = ctx.channel.id
        await hf.safe_send(ctx, f'Captcha channel set to {ctx.channel.name}')

    @captcha.command(name="set_role")
    async def captcha_set_role(self, ctx, *, role_input: str = None):
        """Sets the role that will be given when captcha is completed. Usage: `;captcha set_role <role_name>`"""
        if not role_input:
            instr_msg = await hf.safe_send(ctx, "Please input the exact name of the role new users will receive")
            try:
                reply_msg = await self.bot.wait_for('message',
                                                    timeout=20.0,
                                                    check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
                await instr_msg.delete()
                await reply_msg.delete()
            except asyncio.TimeoutError:
                await hf.safe_send(ctx, "Module timed out")
                await instr_msg.delete()
                return
            except discord.Forbidden:
                pass
        guild = str(ctx.guild.id)
        if guild not in self.bot.db['captcha']:
            await self.toggle
        guild_config = self.bot.db['captcha'][guild]
        role: Optional[discord.Role] = discord.utils.find(lambda r: r.name == role_input, ctx.guild.roles)
        if not role:
            await hf.safe_send(ctx, 'Failed to find a role.  Please type the name of the role after the command, like '
                                    '`;captcha set_role New User`')
        else:
            guild_config['role'] = role.id
            await hf.safe_send(ctx, f'Set role to {role.name} ({role.id})')

    @captcha.command(name="post_message")
    async def captcha_post_message(self, ctx):
        """Posts the captcha message into the channel set by `;captcha set_channel`."""
        guild = str(ctx.guild.id)
        if guild in self.bot.db['captcha']:
            guild_config = self.bot.db['captcha'][guild]
            if guild_config['enable']:
                msg = await hf.safe_send(ctx, 'Please react with the checkmark to enter the server')
                guild_config['message'] = msg.id
                await msg.add_reaction('✅')

    @commands.command(aliases=['purge', 'prune'])
    @commands.bot_has_permissions(manage_messages=True)
    async def clear(self, ctx, num=None, *args):
        """Deletes messages from a channel,
        Usage: `;clear <num_of_messages> [user] [after_message_id]`.
        See [the docs](https://github.com/ryry013/Rai#clearprune-messages) for a full explanation on how to use this."""
        if not num:
            await hf.safe_send(ctx, "Please input a number")
            return
        if 17 <= len(num) <= 20:  # message ID
            try:
                _ = await ctx.channel.fetch_message(int(num))
            except (ValueError, discord.NotFound):
                await hf.safe_send(ctx, "Looks like you tried to input a message ID, but I couldn't find that message")
                return
            args = ('0', int(num))
            num = 100
        try:
            int(num)
        except ValueError:
            await hf.safe_send(ctx, "You need to put a number of messages. "
                                    "Type `;help clear` for information on syntax.")
            return
        if 1000 < int(num):
            await hf.safe_send(ctx, "I can't erase a server for you! Capping the number of messages down "
                                    "to 1000.", delete_after=5)
            num = 1000
        if 100 < int(num):
            msg = await hf.safe_send(ctx, f"You're trying to delete the last {num} messages. "
                                          f"Please type `y` to confirm this.")
            try:
                await self.bot.wait_for('message', timeout=10,
                                        check=lambda m: m.author == ctx.author and m.content == 'y')
            except asyncio.TimeoutError:
                await msg.edit(content="Canceling channel prune", delete_after=5.0)
                return
        try:
            await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        if args:
            if args[0] == '0':
                user = None
            else:
                user = await hf.member_converter(ctx, args[0])
                if not user:
                    return
            try:
                msg = await ctx.channel.fetch_message(args[1])
            except discord.NotFound:  # invalid message ID given
                await hf.safe_send(ctx, 'Message not found')
                return
            except IndexError:  # no message ID given
                msg = None
                pass
        else:
            user = None
            msg = None

        try:
            if not user and not msg:
                await ctx.channel.purge(limit=int(num))
            if user and not msg:
                await ctx.channel.purge(limit=int(num), check=lambda m: m.author == user)
            if not user and msg:
                await ctx.channel.purge(limit=int(num), after=msg)
                try:
                    await msg.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass
            if user and msg:
                await ctx.channel.purge(limit=int(num), check=lambda m: m.author == user, after=msg)
                try:
                    await msg.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass
        except TypeError:
            pass
        except ValueError:
            await hf.safe_send(ctx, 'You must put a number after the command, like `;await clear 5`')
            return

    @commands.command()
    @commands.bot_has_permissions(ban_members=True)
    async def auto_bans(self, ctx):
        """Auto bans for amazingsexdating/users who join with invite link names/other spam sites"""
        config = hf.database_toggle(ctx.guild, self.bot.db['auto_bans'])
        if config['enable']:
            await hf.safe_send(ctx,
                               'Enabled the auto bans module.  I will now automatically ban all users who join with '
                               'a discord invite link username or who join and immediately send an '
                               'amazingsexdating link')
        else:
            await hf.safe_send(ctx, 'Disabled the auto bans module.  I will no longer auto ban users who join with a '
                                    'discord invite link username or who spam a link to amazingsexdating.')

    @commands.command()
    async def set_modlog_channel(self, ctx):
        """Sets the channel for modlog events"""
        if str(ctx.guild.id) in self.bot.db['modlog']:
            self.bot.db['modlog'][str(ctx.guild.id)]['channel'] = ctx.channel.id
        else:
            self.bot.db['modlog'][str(ctx.guild.id)] = {'channel': ctx.channel.id}
        await hf.safe_send(ctx, f"Set modlog channel as {ctx.channel.mention}.")

    @commands.command()
    async def set_mod_role(self, ctx, *, role_name):
        """Set the mod role for your server.  Type the exact name of the role like `;set_mod_role Mods`. \
        To remove the mod role, type `;set_mod_role none`."""
        config = hf.database_toggle(ctx.guild, self.bot.db['mod_role'])
        if 'enable' in config:
            del (config['enable'])
        if role_name.casefold() == "none":
            del self.bot.db['mod_role'][str(ctx.guild.id)]
            await hf.safe_send(ctx, "Removed mod role setting for this server")
            return
        mod_role: Optional[discord.Role] = discord.utils.find(lambda role: role.name == role_name, ctx.guild.roles)
        if not mod_role:
            await hf.safe_send(ctx, "The role with that name was not found")
            return None
        config['id'] = mod_role.id
        await hf.safe_send(ctx, f"Set the mod role to {mod_role.name} ({mod_role.id})")

    @commands.command(aliases=['setmodchannel'])
    async def set_mod_channel(self, ctx, channel_id=None):
        """Sets the mod channel for your server.  Run this command in the mod channel."""
        if not channel_id:
            channel_id = ctx.channel.id
        self.bot.db['mod_channel'][str(ctx.guild.id)] = channel_id
        await hf.safe_send(ctx, f"Set the mod channel for this server as {ctx.channel.mention}.")

    @commands.command()
    async def readd_roles(self, ctx):
        """Automatically readd roles to users who left the server and then rejoin."""
        if str(ctx.guild.id) not in self.bot.db['joins']:  # guild not in 'joins'
            self.bot.db['joins'][str(ctx.guild.id)] = {'enable': False,
                                                       'channel': ctx.channel.id,
                                                       'invites': {},
                                                       'invites_enable': False,
                                                       'readd_roles': {'enable': True,
                                                                       'users': {},
                                                                       'roles': {}
                                                                       }
                                                       }
        try:
            config = self.bot.db['joins'][str(ctx.guild.id)]['readd_roles']
            config['enable'] = not config['enable']
        except KeyError:  # the guild was in 'joins' but it didn't have 'readd_roles'
            config = self.bot.db['joins'][str(ctx.guild.id)]['readd_roles'] = {'enable': True, 'users': {}, 'roles': {}}
        if config['enable']:
            if not ctx.me.guild_permissions.manage_roles:
                await hf.safe_send(ctx, "I lack permission to manage roles.  Please fix that before enabling this")
                config['readd_roles']['enable'] = False
                return
            await hf.safe_send(ctx, "I will readd roles to people who have previously left the server")
        else:
            await hf.safe_send(ctx, "I will NOT readd roles to people who have previously left the server")
        if 'users' not in config:
            config['users'] = {}

    @commands.command(aliases=['newuserwatch'])
    async def new_user_watch(self, ctx):
        """Enables/disables the posting of watching for messages of new users. If enabled, all users that have new \
        accounts less than ten messages in the server will have their messages crossposted by whichever channel is \
        set by the `;super_watch` command."""
        config = self.bot.db['super_watch'].setdefault(str(ctx.guild.id),
                                                       {"users": [], "channel": ctx.channel.id, 'enable': False})
        if 'enable' not in config:
            config['enable'] = False
        if not config['enable']:
            config['enable'] = True
            await hf.safe_send(ctx, "I've enabled the watching of new users.")
        else:
            config['enable'] = False
            await hf.safe_send(ctx, "Ive disabled the watching of new users.")

    @commands.group(invoke_without_command=True, aliases=['superwatch', 'sw'])
    async def super_watch(self, ctx):
        """Sets the super_watch channel."""
        config = self.bot.db['super_watch'].setdefault(str(ctx.guild.id),
                                                       {"users": {}, "channel": ctx.channel.id})
        config['channel'] = ctx.channel.id
        await hf.safe_send(ctx, f"Messages sent from users on the super_watch list will be sent to {ctx.channel.name} "
                                f"({ctx.channel.id}).  \n\n"
                                f"Type `;sw add <ID>` to add someone to the list, or `;sw remove <ID>` to remove them. "
                                f"You can change the channel that super_watch sends posts to by typing `;sw set`.")

    @super_watch.command(name="add")
    async def superwatch_add(self, ctx, target):
        """Adds a user to the superwatch list."""
        if str(ctx.guild.id) not in self.bot.db['super_watch']:
            await ctx.invoke(self.super_watch)
        config = self.bot.db['super_watch'][str(ctx.guild.id)]['users']
        target = await hf.member_converter(ctx, target)
        if not target:  # invalid user given
            return
        if target.id not in config:
            config[str(target.id)] = ctx.message.jump_url
            await hf.safe_send(ctx, f"Added {target.name} to super_watch list")
        else:
            await hf.safe_send(ctx, f"{target.name} is already on the super_watch list")

    @super_watch.command(name="remove")
    async def superwatch_remove(self, ctx, *, target):
        """Removes a user from the superwatch list."""
        config = self.bot.db['super_watch'][str(ctx.guild.id)]['users']
        target_obj = await hf.member_converter(ctx, target)
        if not target_obj:
            try:
                target_id = int(target)
            except ValueError:
                return
        else:
            target_id = target_obj.id
        try:
            del (config[str(target_id)])
            await hf.safe_send(ctx, f"Removed <@{target_id}> from super_watch list")
        except KeyError:
            await hf.safe_send(ctx, "That user wasn't on the super_watch list")

    @super_watch.command(name="list")
    async def super_watch_list(self, ctx):
        """Lists the users in superwatch list."""
        config: list = self.bot.db['super_watch'].get(str(ctx.guild.id), {'users': []})['users']
        users = [f"<@{ID}>" for ID in config]
        if config:
            await hf.safe_send(ctx, f"Users currently on the super_watch list: {', '.join(users)}")
        else:
            await hf.safe_send(ctx, "There's currently no one on the super_watch list")

    @commands.group(invoke_without_command=True, aliases=['svw', 'supervoicewatch', 'voicewatch', 'vw'])
    async def super_voicewatch(self, ctx):
        """Log everytime chosen users join/leave the voice channels.  This sets the super voice watch log channel"""
        if str(ctx.guild.id) not in self.bot.db['mod_channel']:
            await hf.safe_send(ctx,
                               "Before using this, you have to set your mod channel using `;set_mod_channel` in the "
                               "channel you want to designate.")
            return
        config = self.bot.db['super_voicewatch'].setdefault(str(ctx.guild.id), {"users": [], "channel": ctx.channel.id})
        config['channel'] = ctx.channel.id
        await hf.safe_send(ctx, f"I've set the log channel for super voice watch to {ctx.channel.mention}\n\n"
                                "**About svw:** Puts a message in the mod channel every time someone on the super "
                                "watchlist joins a voice channel.  Use `;super_voicewatch add USER` or "
                                "`'super_voicewatch remove USER` to manipulate the list.  Type `;super_voicewatch "
                                "list` to see a full list.  Alias: `;svw`")

    @super_voicewatch.command(name="add")
    async def voicewatch_add(self, ctx, member: discord.Member):
        """Add a member to super voice watch"""
        if str(ctx.guild.id) not in self.bot.db['mod_channel']:
            await hf.safe_send(ctx,
                               "Before using this, you have to set your mod channel using `;set_mod_channel` in the "
                               "channel you want to designate.")
            return
        config = self.bot.db['super_voicewatch'].setdefault(str(ctx.guild.id), {'users': [], 'channel': ctx.channel.id})
        config['users'].append(member.id)
        await hf.safe_send(ctx, f"Added `{member.name} ({member.id})` to the super voice watchlist.")

    @super_voicewatch.command(name="remove")
    async def voicewatch_remove(self, ctx, member):
        """Remove a user from super voice watch"""
        config = self.bot.db['super_voicewatch'].setdefault(str(ctx.guild.id), {'users': [], 'channel': ctx.channel.id})
        target_obj = await hf.member_converter(ctx, member)
        if not target_obj:
            try:
                member_id = int(member)
                msg = f"Removed `{member_id}` from the super voice watchlist."
            except ValueError:
                return
        else:
            member_id = target_obj.id
            msg = f"Removed `{target_obj.name} ({member_id})` from the super voice watchlist."
        try:
            config['users'].remove(member_id)
        except ValueError:
            await hf.safe_send(ctx, "That user was not in the watchlist.")
            return
        await hf.safe_send(ctx, msg)

    @super_voicewatch.command(name="list")
    async def super_voicewatch_list(self, ctx):
        """Lists the users in super voice watch"""
        string = ''
        try:
            config = self.bot.db['super_voicewatch'][str(ctx.guild.id)]
        except KeyError:
            await hf.safe_send(ctx, "Voice watchlist not set-up yet on this server.  Run `;super_voicewatch`")
            return
        if not config['users']:
            await hf.safe_send(ctx, "The voice watchlist is empty")
            return
        for ID in config['users']:
            member = ctx.guild.get_member(ID)
            if member:
                string += f"{member.mention} `({member.name}#{member.discriminator} {member.id})`\n"
            else:
                string += f"{ID}\n"
        try:
            await hf.safe_send(ctx, string)
        except discord.HTTPException:
            await hf.safe_send(ctx, string[0:2000])
            await hf.safe_send(ctx, string[2000:])

    @commands.command(hidden=True)
    @commands.guild_only()
    async def timed_voice_role(self, ctx):
        """A command for setting up a role to be added when a user is in voice for a certain amount of time"""
        # #############  how long do they need to stay in a channel #################################
        q = await hf.safe_send(ctx, "Welcome to the setup module. This will give a role to a user if they've been "
                                    "in voice for sufficiently long. \n\n**First question: how long should they stay "
                                    "in voice to receive a role? (Please give a number of minutes).**\n\n"
                                    "Alternatively, type `cancel` at any time in this process to leave the module, or "
                                    "`disable` now to disable this feature completely.")
        timeout_message = "The module has timed out. Please start the command over."
        try:
            msg = await self.bot.wait_for("message", timeout=30.0,
                                          check=lambda m: m.channel == ctx.channel and m.author == ctx.author)
            wait_time = int(msg.content)
            try:
                if msg.content.casefold() == 'cancel':
                    await hf.safe_send(ctx, "Exiting module")
                    return
                if msg.content.casefold() == 'disable':
                    if str(ctx.guild.id) in self.bot.db['timed_voice_role']:
                        del self.bot.db['timed_voice_role'][str(ctx.guild.id)]
                    await hf.safe_send(ctx, "The module has been disabled.")
                    return

                await msg.delete()
            except ValueError:
                await hf.safe_send(ctx, "I failed to detect your time. Please start the command over and input a "
                                        "single number.")
                return
            except discord.Forbidden:
                pass

            await q.delete()

            # ####### should the role be removed when they leave #############################

            q = await hf.safe_send(ctx, "Thanks. Next, should the role be removed when the user leaves voice chat? "
                                        "Type `yes` or `no`.")

            msg = await self.bot.wait_for("message", timeout=30.0,
                                          check=lambda m: m.channel == ctx.channel and m.author == ctx.author)
            try:
                if msg.content.casefold() == 'cancel':
                    await hf.safe_send(ctx, "Exiting module")
                    return
                choice = msg.content.casefold()
                if choice not in ['yes', 'no']:
                    raise ValueError
                if choice == 'yes':
                    remove_when_leave = True
                else:
                    remove_when_leave = False
                await msg.delete()
            except ValueError:
                await hf.safe_send(ctx, "I failed to detect your answer. Please start the command over and input "
                                        "either exactly `yes` or `no`.")
                return
            await q.delete()

            # ####### should the timer be reset for going into the afk channel #############################

            q = await hf.safe_send(ctx, "Thanks. Next, should the role be removed if the user goes to the AFK channel? "
                                        "Type `yes` or `no`.")

            msg = await self.bot.wait_for("message", timeout=30.0,
                                          check=lambda m: m.channel == ctx.channel and m.author == ctx.author)
            try:
                if msg.content.casefold() == 'cancel':
                    await hf.safe_send(ctx, "Exiting module")
                    return
                choice = msg.content.casefold()
                if choice not in ['yes', 'no']:
                    raise ValueError
                if choice == 'yes':
                    remove_when_afk = True
                else:
                    remove_when_afk = False
                await msg.delete()
            except ValueError:
                await hf.safe_send(ctx, "I failed to detect your answer. Please start the command over and input "
                                        "either exactly `yes` or `no`.")
                return
            await q.delete()

            # ####### specify the role #############################

            q = await hf.safe_send(ctx, "Thanks. Next, please specify the role that you want me to assign to "
                                        "the users. Type the exact name of the role.")

            msg = await self.bot.wait_for("message", timeout=30.0,
                                          check=lambda m: m.channel == ctx.channel and m.author == ctx.author)
            try:
                if msg.content.casefold() == 'cancel':
                    await hf.safe_send(ctx, "Exiting module")
                    return
                choice = msg.content.casefold()
                role: Optional[discord.Role] = discord.utils.find(lambda r: r.name.casefold() == choice,
                                                                  ctx.guild.roles)
                if not role:
                    await hf.safe_send(ctx, "I was not able to find that role. Please start the process over.")
                    return
                await msg.delete()
            except ValueError:
                await hf.safe_send(ctx, "I failed to detect your answer. Please start the command over and input "
                                        "exactly the name of the role..")
                return
            await q.delete()

            # ####### specify the channel #############################

            q = await hf.safe_send(ctx, "Thanks. Finally, please specify the channel that you wish I watch. Type the "
                                        "name of the voice channel. Alternatively, type `none` to watch all channels.")

            msg = await self.bot.wait_for("message", timeout=30.0,
                                          check=lambda m: m.channel == ctx.channel and m.author == ctx.author)
            try:
                if msg.content.casefold() == 'cancel':
                    await hf.safe_send(ctx, "Exiting module")
                    return
                if msg.content.casefold() == 'none':
                    channel_id = None
                else:
                    choice = msg.content.casefold()
                    channel: Optional[discord.Role] = discord.utils.find(lambda c: c.name.casefold() == choice,
                                                                         ctx.guild.voice_channels)
                    if not channel:
                        await hf.safe_send(ctx, "I was not able to find that channel. Please start the process over.")
                        return
                    channel_id = channel.id
                await msg.delete()
            except ValueError:
                await hf.safe_send(ctx, "I failed to detect your answer. Please start the command over and input "
                                        "exactly the name of the channel.")
                return
            await q.delete()

        except asyncio.TimeoutError:
            await hf.safe_send(ctx, timeout_message)
            return

        self.bot.db['timed_voice_role'][str(ctx.guild.id)] = {'wait_time': wait_time,
                                                              'remove_when_leave': remove_when_leave,
                                                              'remove_when_afk': remove_when_afk,
                                                              'channel': channel_id,
                                                              'role': role.id}
        await hf.safe_send(ctx, f"Thanks, I've saved your settings. I will assign `{role.name} ({role.id})`. "
                                f"You can run this command again at any time to change the settings or disable it.")

    @commands.group(invoke_without_command=True, aliases=['setprefix'])
    async def set_prefix(self, ctx, prefix):
        """Sets a custom prefix for the bot"""
        if prefix:
            self.bot.db['prefix'][str(ctx.guild.id)] = prefix
            await hf.safe_send(ctx,
                               f"Set prefix to `{prefix}`.  You can change it again, or type `{prefix}set_prefix reset`"
                               f" to reset it back to the default prefix of `;`")
        else:
            prefix = self.bot.db['prefix'].get(str(ctx.guild.id), ';')
            await hf.safe_send(ctx, f"This is the command to set a custom prefix for the bot.  The current prefix is "
                                    f"`{prefix}`.  To change this, type `{prefix}set_prefix [prefix]` (for example, "
                                    f"`{prefix}set_prefix !`).  Type `{prefix}set_prefix reset` to reset to the "
                                    f"default prefix.")

    @set_prefix.command(name='reset')
    async def prefix_reset(self, ctx):
        try:
            prefix = self.bot.db['prefix']
            del prefix[str(ctx.guild.id)]
            await hf.safe_send(ctx, "The command prefix for this guild has successfully been reset to `;`")
        except KeyError:
            await hf.safe_send(ctx, "This guild already uses the default command prefix.")

    @staticmethod
    def make_options_embed(list_in):  # makes the options menu
        emb = discord.Embed(title='Options Menu',
                            description="Reply with any of the option numbers or letters (b/x)\n")
        counter = 1
        options = ''
        for option in list_in:
            options += f"**{counter})** {option}\n"
            counter += 1
        options += "\n**b)** Go back\n"
        options += "**x)** Close the options menu"
        emb.add_field(name="Options", value=options)
        return emb

    async def wait_menu(self, ctx, menu, emb_in, choices_in):  # posts wait menu, gets a response, returns choice
        if menu:
            try:
                await menu.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        menu = await hf.safe_send(ctx, embed=emb_in)
        try:
            msg = await self.bot.wait_for('message',
                                          timeout=60.0,
                                          check=lambda x: x.content.casefold() in choices_in and x.author == ctx.author)
        except asyncio.TimeoutError:
            await hf.safe_send(ctx, "Menu timed out")
            try:
                await menu.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
            return 'time_out', menu
        try:
            await msg.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

        return msg.content, menu

    @commands.command(aliases=['options'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def config(self, ctx, menu=None):
        """A comprehensive options and configuration menu for the bot"""
        if menu:
            if not isinstance(menu, discord.Message):
                menu = None

        while True:
            options = ["Set/view the mod/submod role (`;set_(sub)mod_role <role name>`)",  # 1
                       "Set/view the mod/submod channel (`;set_(sub)mod_channel`)",  # 2
                       "Set/view the custom prefix (`;set_prefix <prefix>`)",  # 3
                       "Logging modules",  # 4
                       "Report module (`;report`)",  # 5
                       "Setup a questions channel (`;q`)",  # 6
                       "Automatically readd roles to users who rejoin the server (`;readd_roles`)",  # 7
                       "Reaction-to-enter requirement for the server (`;captcha`)",  # 8
                       "Super voice watch (`;svw`)",  # 9
                       "Super text watch (`;sw`)",  # 10
                       ]
            emb = self.make_options_embed(options)
            emb.description = "(WIP) " + emb.description
            choices = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'x']
            try:
                choice, menu = await self.wait_menu(ctx, menu, emb, choices)
            except discord.Forbidden:
                await hf.safe_send(ctx,
                                   "I lack the ability to manage messages, which I require for the options module")
                return
            if choice == 'time_out':
                return
            elif choice == 'x':
                await menu.delete()
                await hf.safe_send(ctx, "Closing options menu")
                return

            #           main > set mod role
            elif choice == '1':
                while True:
                    options = ['Set the mod role (`;set_mod_role`)', "Unset the mod role",
                               "Set the submod role (currently only for the mute and ;question answer commands) "
                               "(`;set_submod_role`)", "Unset the submod role"]
                    emb = self.make_options_embed(options)
                    emb.title = "Setting mod role"
                    try:
                        config = self.bot.db['mod_role'][str(ctx.guild.id)]
                        if isinstance(config['id'], list):
                            role = ctx.guild.get_role(config['id'][0])
                        else:
                            role = ctx.guild.get_role(config['id'])
                        emb.description = f"Current role is {role.mention} ({role.id})\n" + emb.description
                    except KeyError:
                        emb.description = "No role is currently set\n" + emb.description

                    choices = ['1', '2', '3', '4', 'b', 'x']
                    choice, menu = await self.wait_menu(ctx, menu, emb, choices)
                    if choice == 'time_out':
                        return
                    if choice == 'b':
                        break
                    elif choice == 'x':
                        await hf.safe_send(ctx, "Closed options menu")
                        await menu.delete()
                        return
                    elif choice == '1':
                        instr_msg = await hf.safe_send(ctx,
                                                       "Please input the exact name of the role you wish to set as "
                                                       "the mod role")
                        reply_msg = await self.bot.wait_for('message',
                                                            timeout=20.0,
                                                            check=lambda x: x.author == ctx.author)
                        await ctx.invoke(self.set_mod_role, reply_msg.content)
                        await instr_msg.delete()
                        await reply_msg.delete()
                    elif choice == '2':
                        try:
                            del self.bot.db['mod_role'][str(ctx.guild.id)]
                            await hf.safe_send(ctx, "Removed the setting for a mod role")
                        except KeyError:
                            await hf.safe_send(ctx, "You currently don't have a mod role set")
                    elif choice == '3':
                        instr_msg = await hf.safe_send(ctx,
                                                       "Please input the exact name of the role you wish to set as "
                                                       "the submod role")
                        reply_msg = await self.bot.wait_for('message',
                                                            timeout=20.0,
                                                            check=lambda x: x.author == ctx.author)
                        await ctx.invoke(self.bot.get_command('set_submod_role'), reply_msg.content)
                        await instr_msg.delete()
                        await reply_msg.delete()
                    elif choice == '4':
                        try:
                            del self.bot.db['submod_role'][str(ctx.guild.id)]
                            await hf.safe_send(ctx, "Removed the setting for a submod role")
                        except KeyError:
                            await hf.safe_send(ctx, "You currently don't have a submod role set")

            #           main > set mod channel
            elif choice == '2':
                while True:
                    options = ['Set the mod channel as this channel (`;set_mod_channel`)', "Unset the mod channel",
                               'Set the submod channel as this channel (`;set_submod_channel`)']
                    emb = self.make_options_embed(options)
                    emb.title = "Setting mod channel"
                    config = self.bot.db['mod_channel']
                    try:
                        channel = ctx.guild.get_channel_or_thread(config[str(ctx.guild.id)])
                        emb.description = f"Current channel is {channel.mention} ({channel.id})\n" + emb.description
                    except KeyError:
                        emb.description = "There is no mod channel currently set\n" + emb.description

                    choices = ['1', '2', '3', 'b', 'x']
                    choice, menu = await self.wait_menu(ctx, menu, emb, choices)
                    if choice == 'time_out':
                        return
                    if choice == 'b':
                        break
                    elif choice == 'x':
                        await hf.safe_send(ctx, "Closed options menu")
                        await menu.delete()
                        return
                    elif choice == '1':
                        await ctx.invoke(self.set_mod_channel)
                    elif choice == '2':
                        try:
                            del config[str(ctx.guild.id)]
                            await hf.safe_send(ctx, "Unset the mod channel")
                        except KeyError:
                            await hf.safe_send(ctx, "There is no mod channel set")
                    elif choice == '3':
                        await ctx.invoke(self.bot.get_command('set_submod_channel'))

            #           # main > set custom prefix
            elif choice == '3':
                while True:
                    options = ['Set the custom prefix (`;set_prefix <prefix>`)',
                               "Reset the server's custom prefix (`<prefix>set_prefix reset`)"]
                    emb = self.make_options_embed(options)
                    emb.title = "Custom Prefix"
                    config = self.bot.db['prefix']
                    current_prefix = config.get(str(ctx.guild.id), 'not set')
                    emb.description = f"The custom prefix is {current_prefix}\n" + emb.description

                    choices = ['1', '2', 'b', 'x']
                    choice, menu = await self.wait_menu(ctx, menu, emb, choices)
                    if choice == 'time_out':
                        return
                    if choice == 'b':
                        break
                    elif choice == 'x':
                        await hf.safe_send(ctx, "Closing options menu")
                        await menu.delete()
                        return
                    elif choice == '1':
                        instr_msg = await hf.safe_send(ctx,
                                                       "Please input the custom prefix you wish to use on this server")
                        try:
                            reply_msg = await self.bot.wait_for('message',
                                                                timeout=20.0,
                                                                check=lambda x: x.author == ctx.author)
                            await instr_msg.delete()
                            await reply_msg.delete()
                            await ctx.invoke(self.set_prefix, reply_msg.content)
                        except asyncio.TimeoutError:
                            await hf.safe_send(ctx, "Module timed out")
                            await instr_msg.delete()
                            return
                    elif choice == '2':
                        await ctx.invoke(self.prefix_reset)

            #           main > logging module
            elif choice == '4':
                while True:
                    options = ['Deleted messages (`;deletes`)',  # 1
                               'Edited messages (`;edits`)',  # 2
                               'Joins and invite link tracking (`;joins`)',  # 3
                               'Leaves (`;leaves`)',  # 4
                               'Kicks (`;kicks`)',  # 5
                               'Bans (`;bans`)',  # 6
                               "Username/nickname changes (`;nicknames`)",  # 7
                               "Removed reactions (`;reactions`)",  # 8
                               ]
                    emb = self.make_options_embed(options)
                    emb.title = "Logging Module"

                    choices = ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'b', 'x']
                    choice, menu = await self.wait_menu(ctx, menu, emb, choices)
                    if choice == 'time_out':
                        return
                    if choice == 'b':
                        break
                    elif choice == 'x':
                        await hf.safe_send(ctx, "Closing options menu")
                        await menu.delete()
                        return

                    # main > logging > deletes
                    elif choice == '1':
                        options = ["Enable/disable this module (`;deletes`)",
                                   "Set the channel for logging (`;deletes set`)"]
                        emb = self.make_options_embed(options)
                        emb.title = "Logging > Deletes"
                        config = self.bot.db['deletes'][str(ctx.guild.id)]

                        while True:
                            if config['enable']:
                                channel = ctx.guild.get_channel_or_thread(config['channel'])
                                emb.description = f"I am currently set to track deleted messages in " \
                                                  f"{channel.mention}\n\nReply with any of the option numbers " \
                                                  f"or letters (b/x)"
                            else:
                                emb.description = "This module is currently disabled.  It tracks deleted messages " \
                                                  "by users.\n\nReply with any of the option numbers or letters (b/x)"

                            choices = ['1', '2', 'b', 'x']
                            choice, menu = await self.wait_menu(ctx, menu, emb, choices)

                            if choice == 'time_out':
                                return
                            elif choice == 'b':
                                break
                            elif choice == 'x':
                                await hf.safe_send(ctx, "Closing options menu")
                                await menu.delete()
                                return
                            elif choice == '1':
                                await ctx.invoke(self.bot.get_command('delete_logging'))
                            elif choice == '2':
                                await ctx.invoke(self.bot.get_command('delete_logging deletes_set'))

                    # main > logging > edits
                    elif choice == '2':
                        options = ["Enable/disable this module (`;edits`)",
                                   "Set the channel for logging (`;edits set`)"]
                        emb = self.make_options_embed(options)
                        emb.title = "Logging > Edits"
                        config = self.bot.db['edits'][str(ctx.guild.id)]

                        while True:
                            if config['enable']:
                                channel = ctx.guild.get_channel_or_thread(config['channel'])
                                emb.description = f"I am currently set to track edited messages in " \
                                                  f"{channel.mention}\n\nReply with any of the option numbers " \
                                                  f"or letters (b/x)"
                            else:
                                emb.description = "This module is currently disabled.  It tracks edited messages " \
                                                  "by users.\n\nReply with any of the option numbers or letters (b/x)"

                            choices = ['1', '2', 'b', 'x']
                            choice, menu = await self.wait_menu(ctx, menu, emb, choices)

                            if choice == 'time_out':
                                return
                            elif choice == 'b':
                                break
                            elif choice == 'x':
                                await hf.safe_send(ctx, "Closing options menu")
                                await menu.delete()
                                return
                            elif choice == '1':
                                await ctx.invoke(self.bot.get_command('edit_logging'))
                            elif choice == '2':
                                await ctx.invoke(self.bot.get_command('edit_logging deletes_set'))

                    # main > logging > welcomes/joins
                    elif choice == '3':
                        options = ["Enable/disable this module (`;joins`)",
                                   "Set the channel for logging (`;joins set`)",
                                   "Enable/disable tracking of invite links people used to join (`;joins invites`)"]
                        emb = self.make_options_embed(options)
                        emb.title = "Logging > Joins/Invite Tracking"
                        config = self.bot.db['joins'][str(ctx.guild.id)]

                        while True:
                            if config['enable']:
                                channel = ctx.guild.get_channel_or_thread(config['channel'])
                                emb.description = f"I am currently set to log member joins in " \
                                                  f"{channel.mention}\n\nReply with any of the option numbers " \
                                                  f"or letters (b/x)"
                            else:
                                emb.description = "This module is currently disabled.  It tracks joins " \
                                                  "by users.\n\nReply with any of the option numbers or letters (b/x)"

                            choices = ['1', '2', '3', 'b', 'x']
                            choice, menu = await self.wait_menu(ctx, menu, emb, choices)

                            if choice == 'time_out':
                                return
                            elif choice == 'b':
                                break
                            elif choice == 'x':
                                await hf.safe_send(ctx, "Closing options menu")
                                await menu.delete()
                                return
                            elif choice == '1':
                                await ctx.invoke(self.bot.get_command('welcome_logging'))
                            elif choice == '2':
                                await ctx.invoke(self.bot.get_command('welcome_logging welcomes_set'))
                            elif choice == '3':
                                await ctx.invoke(self.bot.get_command('welcome_logging invites_enable'))

                    # main > logging > leaves
                    elif choice == '4':
                        options = ["Enable/disable this module (`;leaves`)",
                                   "Set the channel for logging (`;leaves set`)"]
                        emb = self.make_options_embed(options)
                        emb.title = "Logging > Leaves"
                        config = self.bot.db['leaves'][str(ctx.guild.id)]

                        while True:
                            if config['enable']:
                                channel = ctx.guild.get_channel_or_thread(config['channel'])
                                emb.description = f"I am currently set to log when members leave the server in " \
                                                  f"{channel.mention}\n\nReply with any of the option numbers " \
                                                  f"or letters (b/x)"
                            else:
                                emb.description = "This module is currently disabled.  It logs when a member leaves." \
                                                  "\n\nReply with any of the option numbers or letters (b/x)"

                            choices = ['1', '2', 'b', 'x']
                            choice, menu = await self.wait_menu(ctx, menu, emb, choices)

                            if choice == 'time_out':
                                return
                            elif choice == 'b':
                                break
                            elif choice == 'x':
                                await hf.safe_send(ctx, "Closing options menu")
                                await menu.delete()
                                return
                            elif choice == '1':
                                await ctx.invoke(self.bot.get_command('leave_logging'))
                            elif choice == '2':
                                await ctx.invoke(self.bot.get_command('leave_logging leaves_set'))

                    # main > logging > kicks
                    elif choice == '5':
                        options = ["Enable/disable this module (`;kicks`)",
                                   "Set the channel for logging (`;kicks set`)"]
                        emb = self.make_options_embed(options)
                        emb.title = "Logging > Kicks"
                        config = self.bot.db['kicks'][str(ctx.guild.id)]

                        while True:
                            if config['enable']:
                                channel = ctx.guild.get_channel_or_thread(config['channel'])
                                emb.description = f"I am currently set to track kicked members " \
                                                  f"{channel.mention}\n\nReply with any of the option numbers " \
                                                  f"or letters (b/x)"
                            else:
                                emb.description = "This module is currently disabled.  It tracks kicked members " \
                                                  "\n\nReply with any of the option numbers or letters (b/x)"

                            choices = ['1', '2', 'b', 'x']
                            choice, menu = await self.wait_menu(ctx, menu, emb, choices)

                            if choice == 'time_out':
                                return
                            elif choice == 'b':
                                break
                            elif choice == 'x':
                                await hf.safe_send(ctx, "Closing options menu")
                                await menu.delete()
                                return
                            elif choice == '1':
                                await ctx.invoke(self.bot.get_command('kick_logging'))
                            elif choice == '2':
                                await ctx.invoke(self.bot.get_command('kick_logging kicks_set'))

                    # main > logging > bans
                    elif choice == '6':
                        options = ["Enable/disable this module (`;bans`)",
                                   "Set the channel for logging (`;bans set`)"]
                        emb = self.make_options_embed(options)
                        config = self.bot.db['bans'][str(ctx.guild.id)]

                        while True:
                            if config['enable']:
                                channel = ctx.guild.get_channel_or_thread(config['channel'])
                                emb.description = f"I am currently set to track banned members " \
                                                  f"{channel.mention}\n\nReply with any of the option numbers " \
                                                  f"or letters (b/x)"
                            else:
                                emb.description = "This module is currently disabled.  It tracks banned members " \
                                                  "\n\nReply with any of the option numbers or letters (b/x)"

                            choices = ['1', '2', 'b', 'x']
                            choice, menu = await self.wait_menu(ctx, menu, emb, choices)

                            if choice == 'time_out':
                                return
                            elif choice == 'b':
                                break
                            elif choice == 'x':
                                await hf.safe_send(ctx, "Closing options menu")
                                await menu.delete()
                                return
                            elif choice == '1':
                                await ctx.invoke(self.bot.get_command('ban_logging'))
                            elif choice == '2':
                                await ctx.invoke(self.bot.get_command('ban_logging bans_set'))

                    # main > logging > nicknames
                    elif choice == '7':
                        options = ["Enable/disable this module (`;nicknames`)",
                                   "Set the channel for logging (`;nicknames set`)"]
                        emb = self.make_options_embed(options)
                        emb.title = "Logging > Nicknames"
                        config = self.bot.db['nicknames'][str(ctx.guild.id)]

                        while True:
                            if config['enable']:
                                channel = ctx.guild.get_channel_or_thread(config['channel'])
                                emb.description = f"I am currently set to track member nickname changes " \
                                                  f"{channel.mention}\n\nReply with any of the option numbers " \
                                                  f"or letters (b/x)"
                            else:
                                emb.description = "This module is currently disabled.  It tracks member nickname " \
                                                  "changes.\n\nReply with any of the option numbers or letters (b/x)"

                            choices = ['1', '2', 'b', 'x']
                            choice, menu = await self.wait_menu(ctx, menu, emb, choices)

                            if choice == 'time_out':
                                return
                            elif choice == 'b':
                                break
                            elif choice == 'x':
                                await hf.safe_send(ctx, "Closing options menu")
                                await menu.delete()
                                return
                            elif choice == '1':
                                await ctx.invoke(self.bot.get_command('nickname_logging'))
                            elif choice == '2':
                                await ctx.invoke(self.bot.get_command('nickname_logging nicknames_set'))

                    # main > logging > reactions
                    elif choice == '8':
                        options = ["Enable/disable this module (`;reactions`)",
                                   "Set the channel for logging (`;reactions set`)"]
                        emb = self.make_options_embed(options)
                        emb.title = "Logging > Reactions"
                        config = self.bot.db['kicks'][str(ctx.guild.id)]

                        while True:
                            if config['enable']:
                                channel = ctx.guild.get_channel_or_thread(config['channel'])
                                emb.description = f"I am currently set to track when users remove a reaction from a " \
                                                  f"message in {channel.mention}\n\nReply with any of the option " \
                                                  f"numbers or letters (b/x)"
                            else:
                                emb.description = "This module is currently disabled.  It tracks when users remove " \
                                                  "a reaction from a\n\nReply with any of the option numbers or " \
                                                  "letters (b/x)"

                            choices = ['1', '2', 'b', 'x']
                            choice, menu = await self.wait_menu(ctx, menu, emb, choices)

                            if choice == 'time_out':
                                return
                            elif choice == 'b':
                                break
                            elif choice == 'x':
                                await hf.safe_send(ctx, "Closing options menu")
                                await menu.delete()
                                return
                            elif choice == '1':
                                await ctx.invoke(self.bot.get_command('reaction_logging'))
                            elif choice == '2':
                                await ctx.invoke(self.bot.get_command('reaction_logging reactions_set'))

            #           main > report module
            elif choice == '5':
                while True:
                    options = ['Set the mod role (these users can do `;report done`) (`set_mod_role`)',
                               "Set the mod channel (this is where anonymous reports go) (`;set_mod_channel`)",
                               "Set the report room (this is where users get taken for reports) (`;report setup`)",
                               "Check the report room waiting list (`;report check_waiting_list`)",
                               "Clear the report room waiting list (`;report clear_waiting_list`)",
                               "Reset the report room (in case of bugs) (`;report reset`)",
                               "Ping `@here` when someone makes an anonymous report (`;report anonymous_ping`)",
                               "Ping `@here` when someone makes enters the report room (`;report room_ping`)"]
                    emb = self.make_options_embed(options)
                    emb.title = "Setting up the report module"
                    try:
                        config = self.bot.db['report'][str(ctx.guild.id)]
                        channel = ctx.guild.get_channel_or_thread(config['channel'])
                        emb.description = f"Current report channel is {channel.mention} ({channel.id})\n" \
                                          f"{emb.description}"
                    except KeyError:
                        emb.description = f"The report room is not setup yet.\n{emb.description}"

                    choices = ['1', '2', '3', '4', '5', '6', '7', '8', 'b', 'x']
                    choice, menu = await self.wait_menu(ctx, menu, emb, choices)
                    if choice == 'time_out':
                        return
                    if choice == 'b':
                        break
                    elif choice == 'x':
                        await hf.safe_send(ctx, "Closed options menu")
                        await menu.delete()
                        return

                    # set mod role
                    elif choice == '1':
                        instr_msg = await hf.safe_send(ctx,
                                                       "Please input the exact name of the role you wish to set as "
                                                       "the mod role")
                        reply_msg = await self.bot.wait_for('message',
                                                            timeout=20.0,
                                                            check=lambda x: x.author == ctx.author)
                        await ctx.invoke(self.set_mod_role, reply_msg.content)
                        await instr_msg.delete()
                        await reply_msg.delete()

                    # set mod channel
                    elif choice == '2':
                        await ctx.invoke(self.set_mod_channel)

                    # Set the report room
                    elif choice == '3':
                        await ctx.invoke(self.bot.get_command('report setup'))

                    # Check waiting list
                    elif choice == '4':
                        await ctx.invoke(self.bot.get_command('report check_waiting_list'))

                    # Clear waiting list
                    elif choice == '5':
                        await ctx.invoke(self.bot.get_command('report clear_waiting_list'))

                    # Reset report room
                    elif choice == '6':
                        await ctx.invoke(self.bot.get_command('report reset'))

                    # Ping `@here` for anonymous reports
                    elif choice == '7':
                        await ctx.invoke(self.bot.get_command('report anonymous_ping'))

                    # Ping `@here` for users in the report room
                    elif choice == '8':
                        await ctx.invoke(self.bot.get_command('report room_ping'))

            #           main > questions module
            elif choice == '6':
                await ctx.invoke(self.bot.get_command('question setup'))

            #           main > readd roles
            elif choice == '7':
                await ctx.invoke(self.bot.get_command('readd_roles'))

            #           main > captcha
            elif choice == '8':
                while True:
                    options = ['Enable/disable the module (`;captcha toggle`)',
                               "Set here as the channel the new users will see (`;captcha set_channel`)",
                               "Set the role the new users will receive upon reacting "
                               "(`;captcha set_role <role name>`)",
                               "Post the message to this channel (`;captcha post_message`)"]
                    emb = self.make_options_embed(options)
                    emb.title = "Reaction-to-enter requirement for entering the server"
                    try:
                        config = self.bot.db['captcha'][str(ctx.guild.id)]
                        channel = ctx.guild.get_channel_or_thread(config['channel'])
                        role = ctx.guild.get_role(config['role'])
                        word_dict = {True: 'enabled', False: 'disabled'}
                        emb.description = f"This module is currently {word_dict[config['enable']]}.\n" \
                                          f"Current entry channel is {channel.mention} ({channel.id})\n" \
                                          f"The role new users receive is {role.mention} ({role.id})\n" \
                                          f"{emb.description}"
                    except KeyError:
                        await ctx.invoke(self.toggle)
                        continue

                    choices = ['1', '2', '3', '4', 'b', 'x']
                    choice, menu = await self.wait_menu(ctx, menu, emb, choices)
                    if choice == 'time_out':
                        return
                    if choice == 'b':
                        break
                    elif choice == 'x':
                        await hf.safe_send(ctx, "Closed options menu")
                        await menu.delete()
                        return

                    # Enable/disable the module
                    elif choice == '1':
                        await ctx.invoke(self.toggle)

                    # Set here as the channel the new users will see
                    elif choice == '2':
                        await ctx.invoke(self.captcha_set_channel)

                    # Set the role the new users will receive upon reacting"
                    elif choice == '3':
                        await ctx.invoke(self.captcha_set_role)

                    # Post the message to this channel
                    elif choice == '4':
                        await ctx.invoke(self.captcha_post_message)

            #           main > super voice watch
            elif choice == '9':
                while True:
                    options = ["Set here as the channel logs will be posted (`;svw`)",
                               'View list of people in super voice watch (`;svw list`)']
                    emb = self.make_options_embed(options)
                    emb.title = "Super voice watch"
                    try:
                        config = self.bot.db['super_voicewatch'][str(ctx.guild.id)]
                        channel = ctx.guild.get_channel_or_thread(config['channel'])
                        emb.description = f"When a user on the super voice list joins a voice channel, this will be " \
                                          f"logged in {channel.mention}\n" \
                                          f"{emb.description}"
                    except KeyError:
                        await ctx.invoke(self.super_voicewatch)
                        continue

                    choices = ['1', '2', 'b', 'x']
                    choice, menu = await self.wait_menu(ctx, menu, emb, choices)
                    if choice == 'time_out':
                        return
                    if choice == 'b':
                        break
                    elif choice == 'x':
                        await hf.safe_send(ctx, "Closed options menu")
                        await menu.delete()
                        return

                    # Set here as the channel the new users will see (`;svw`)
                    elif choice == '1':
                        await ctx.invoke(self.super_voicewatch)

                    # View list of people in super voice watch (`;svw list`)
                    elif choice == '2':
                        await ctx.invoke(self.super_voicewatch_list)

            #           main > super text watch
            elif choice == '10':
                while True:
                    options = ["Set here as the channel logs will be sent to (`;sw`)",
                               'View list of people in super voice watch (`;sw list`)']
                    emb = self.make_options_embed(options)
                    emb.title = "Super text watch"
                    try:
                        config = self.bot.db['super_watch'][str(ctx.guild.id)]
                        channel = ctx.guild.get_channel_or_thread(config['channel'])
                        emb.description = f"When a user on the super text watch list sends any message, this will be " \
                                          f"logged in {channel.mention}.  The purpose for this is if a user joins " \
                                          f"who you suspect to be a troll, and you want to watch them very carefully." \
                                          f"\n{emb.description}"
                    except KeyError:
                        await ctx.invoke(self.super_watch)
                        continue

                    choices = ['1', '2', 'b', 'x']
                    choice, menu = await self.wait_menu(ctx, menu, emb, choices)
                    if choice == 'time_out':
                        return
                    if choice == 'b':
                        break
                    elif choice == 'x':
                        await hf.safe_send(ctx, "Closed options menu")
                        await menu.delete()
                        return

                    # Set here as the channel the new users will see (`;svw`)
                    elif choice == '1':
                        await ctx.invoke(self.super_watch)

                    # View list of people in super voice watch (`;svw list`)
                    elif choice == '2':
                        await ctx.invoke(self.super_watch_list)

            else:
                await hf.safe_send(ctx, "Something went wrong")
                return

    @commands.command()
    async def asar(self, ctx, *args):
        """Adds a self-assignable role to the list of self-assignable roles."""
        try:
            if re.search(r"^\d{1,2}$", args[0]):  # I want a string, but want to see if it's a number first
                group = args[0]
                role_name = ' '.join(args[1:])
            else:
                group = '0'
                role_name = ' '.join(args[0:])
        except IndexError:
            await hf.safe_send(ctx, "Type the name of the role you wish to make self assignable.")
            return
        config = self.bot.db['SAR'].setdefault(str(ctx.guild.id), {'0': []})
        if re.search(r"\d{17,22}", role_name):
            role = ctx.guild.get_role(int(role_name))
        else:
            role: Optional[discord.Role] = discord.utils.find(lambda r: r.name == role_name, ctx.guild.roles)
        if not role:
            await hf.safe_send(ctx, "The role with that name was not found")
            return None
        if group not in config:
            config[group] = []
        for config_group in config:
            if role.id in config[config_group]:
                await hf.safe_send(ctx, embed=hf.red_embed(f"**{ctx.author.name}#{ctx.author.discriminator}** Role "
                                                           f"**{role.name}** is already in the list."))
                return
        config[group].append(role.id)
        await hf.safe_send(ctx, embed=hf.green_embed(f"**{ctx.author.name}#{ctx.author.discriminator}** Role "
                                                     f"**{role.name}** has been added to the list in group "
                                                     f"**{group}**."))

    @commands.command()
    async def rsar(self, ctx, *, role_name):
        """Removes a self-assignable role"""
        config = self.bot.db['SAR'].setdefault(str(ctx.guild.id), {'0': []})
        if re.search(r"\d{17,22}", role_name):
            role = ctx.guild.get_role(int(role_name))
        else:
            role: Optional[discord.Role] = discord.utils.find(lambda r: r.name == role_name, ctx.guild.roles)
        if not role:
            await hf.safe_send(ctx, "Role not found")
            return
        for group in config:
            if role.id in config[group]:
                config[group].remove(role.id)
                await hf.safe_send(ctx, embed=hf.red_embed(f"**{ctx.author.name}#{ctx.author.discriminator}** Role "
                                                           f"**{role.name}** has been removed from the list."))

    @commands.command()
    @commands.check(lambda x: x.guild.id == 243838819743432704 or x.author.id == 202995638860906496)
    async def send(self, ctx, channel_id: int, *, msg):
        """Sends a message to the channel ID specified"""
        channel = self.bot.get_channel(channel_id)
        if not channel:
            channel = self.bot.get_user(channel_id)
            if not channel:
                await hf.safe_send(ctx, "Invalid ID")
                return
        await channel.send(msg)
        await ctx.message.add_reaction("✅")

    @commands.command(aliases=["word_filter", "ban_filter", "wordban", 'banfilter'])
    @commands.bot_has_permissions(embed_links=True, ban_members=True)
    async def wordfilter(self, ctx):
        """Configuration for a filter that bans users when they say a word or phrase. Regex is allowed.
        It is configurable per word to ban within X amount of minutes from a user joining the server."""
        if str(ctx.guild.id) not in self.bot.db['wordfilter']:
            self.bot.db['wordfilter'][str(ctx.guild.id)] = {}
        emb = discord.Embed(title="Configuration for the word ban filter. Please type an option.",
                            description="1) See current banned words or phrases\n"
                                        "2) Add a new word or phrase\n"
                                        "3) Delete a word or phrase\n"
                                        "4) Exit this menu")
        try:
            resp, menu = await self.wait_menu(ctx, None, emb, ['1', '2', '3', '4'])
        except asyncio.TimeoutError:
            return  # Notification is handled in wait_menu function

        if resp == '1':
            await self.wordfilter_view(ctx, menu)
        elif resp == '2':
            await self.wordfilter_add(ctx, menu)
        elif resp == '3':
            await self.wordfilter_delete(ctx, menu)
        elif resp == '4':
            try:
                await menu.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
            await hf.safe_send(ctx, "I've closed the module.", delete_after=10.0)
        else:
            try:
                await menu.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
            await hf.safe_send(ctx, "I didn't understand your response. Please start over.", delete_after=10.0)

    async def wordfilter_view(self, ctx, menu):
        config = self.bot.db['wordfilter'][str(ctx.guild.id)]
        if not config:
            await menu.edit(embed=hf.red_embed("There are currently no logged words in this server's word filter."),
                            delete_after=10.0)
            return
        s = ""
        try:
            await menu.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        for word_entry in config:
            new_s = f"- `{word_entry}` - {config[word_entry]} mins\n"
            if len(s + new_s) < 2048:
                s += new_s
            else:
                await hf.safe_send(ctx, embed=discord.Embed(description=s))
                s = new_s
        await hf.safe_send(ctx, embed=discord.Embed(description=s))

    async def wordfilter_add(self, ctx, menu):
        config = self.bot.db['wordfilter'][str(ctx.guild.id)]
        await menu.edit(embed=discord.Embed(description="Please input the regex for the word you want to ban for. "
                                                        "If you want to test it, try this site: https://regex101.com/"
                                                        ".\n(If you want just a simple string, you can input it "
                                                        "without worrying what 'regex' is)\n\nIf the keyword already "
                                                        "exists, I will overwrite it."))
        try:
            msg = await self.bot.wait_for('message',
                                          timeout=60.0,
                                          check=lambda x: x.channel == ctx.channel and x.author == ctx.author)
        except asyncio.TimeoutError:
            try:
                await menu.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
            await hf.safe_send(ctx, "Menu timed out", delete_after=10.0)
            return

        try:
            re.compile(msg.content)
        except sre_constants_error as e:
            await menu.edit(embed=hf.red_embed(f"Your regex returned an error: `{e}`."))
            return

        word = msg.content
        try:
            await msg.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

        await menu.edit(embed=discord.Embed(description="Next, type the ban window in minutes. If a new user says "
                                                        "your selected word or phrase within the ban window number "
                                                        "of minutes from joining the server, they'll be automatically "
                                                        "banned."))
        try:
            msg = await self.bot.wait_for('message',
                                          timeout=60.0,
                                          check=lambda x: x.channel == ctx.channel and x.author == ctx.author)
        except asyncio.TimeoutError:
            try:
                await menu.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
            await hf.safe_send(ctx, "Menu timed out", delete_after=10.0)
            return

        try:
            minutes = int(msg.content)
        except ValueError:
            try:
                await menu.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
            await hf.safe_send(ctx, "Please start over and input only a single number.")
            return

        config[word] = minutes
        try:
            await msg.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        await menu.edit(embed=hf.green_embed(f"I will ban anyone who says this within **{minutes}** minutes of joining:"
                                             f"```{word}```"))

    async def wordfilter_delete(self, ctx, menu):
        config = self.bot.db['wordfilter'][str(ctx.guild.id)]
        await menu.edit(embed=discord.Embed(description="Please input the word or phrase you wish to delete from the "
                                                        "word filter."))
        try:
            msg = await self.bot.wait_for('message',
                                          timeout=60.0,
                                          check=lambda x: x.channel == ctx.channel and x.author == ctx.author)
        except asyncio.TimeoutError:
            try:
                await menu.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
            await hf.safe_send(ctx, "Menu timed out", delete_after=10.0)
            return

        if msg.content in config:
            try:
                await msg.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
            del (config[msg.content])
            await menu.edit(embed=hf.green_embed("Success! I've deleted that filter."))
        else:
            try:
                await menu.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
            await hf.safe_send(ctx, embed=hf.red_embed("I couldn't find that filter. Please start over and try again."),
                               delete_after=10.0)

    @commands.group(invoke_without_command=True, aliases=['antiraid'])
    @commands.bot_has_permissions(embed_links=True, ban_members=True)
    async def antispam(self, ctx, menu=None):
        """Opens configuation menu for the antispam/antiraid module."""
        config = self.bot.db['antispam'].setdefault(str(ctx.guild.id), {'enable': False, 'action': None,
                                                                        'message_threshhold': None,
                                                                        'time_threshhold': None,
                                                                        'ignored': [],
                                                                        'ban_override': None})
        if config['enable']:
            settings = f"**The current settings are as follows:\n" \
                       f"    - Message threshhold: {config['message_threshhold']}\n" \
                       f"    - Time threshhold (seconds): {config['time_threshhold']}\n" \
                       f"    - Punishment: {config['action'].capitalize()}**"
            if config.get('ban_override', None):
                settings = settings[:-2] + f"\n    - Ban override threshhold (minutes): {config['ban_override']}**"
        else:
            settings = "The antispam module is currently disabled."
        emb = discord.Embed(title="Configuration for the antispam module. Please type an option.",
                            description="1) Enable or disable the module.\n"
                                        "2) Change settings\n"
                                        "3) Ignore/unignore a channel\n"
                                        "4) View list of ignored channels\n"
                                        "5) Special setting: Always ban spammers who joined server recently\n"
                                        "6) Exit this menu\n\n"
                                        f"{settings}")
        try:
            resp: str
            menu: discord.Message
            resp, menu = await self.wait_menu(ctx, menu, emb, ['1', '2', '3', '4', '5', '6'])
        except asyncio.TimeoutError:
            return  # Notification is handled in wait_menu function

        if resp == '1':
            await self.antispam_toggle(ctx, menu, config)
        elif resp == '2':
            await self.antispam_settings(ctx, menu)
        elif resp == '3':
            await menu.edit(embed=hf.green_embed("Which channel do you wish to ignore? Please mention the channel."))
            try:
                msg: discord.Message = await self.bot.wait_for('message',
                                                               timeout=60.0,
                                                               check=lambda
                                                               m: m.channel == ctx.channel and m.author == ctx.author)
            except asyncio.TimeoutError:
                try:
                    await menu.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass
                await hf.safe_send(ctx, "Menu timed out", delete_after=10.0)
                return
            await menu.delete()
            await self.antispam_ignore(ctx, menu, msg.content)
        elif resp == '4':
            await self.antispam_list(ctx, menu)
        elif resp == '5':
            await self.antispam_ban_override(ctx, menu, config)
        elif resp == '6':
            try:
                await menu.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
            await hf.safe_send(ctx, "I've closed the module.", delete_after=10.0)
        else:
            try:
                await menu.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
            await hf.safe_send(ctx, "I didn't understand your response. Please start over.", delete_after=10.0)

    async def antispam_toggle(self, ctx, menu: discord.Message, config):
        if config['enable']:
            config['enable'] = False
            await menu.edit(embed=hf.red_embed("The antispam module has been disabled."))
        else:
            await self.antispam_settings(ctx, menu)
        await ctx.invoke(self.antispam, menu)

    async def antispam_settings(self, ctx, menu: discord.Message):
        await menu.edit(embed=hf.green_embed("`I should [ban/kick/mute] users who spam the same message [x] times "
                                             "in [y] seconds.`\n"
                                             "Please fill in the three blanks\n"
                                             "(example: `mute 5 10`)"))
        try:
            msg = await self.bot.wait_for('message',
                                          timeout=60.0,
                                          check=lambda m: m.channel == ctx.channel and m.author == ctx.author)
        except asyncio.TimeoutError:
            try:
                await menu.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
            await hf.safe_send(ctx, "Menu timed out", delete_after=10.0)
            return
        if len(msg.content.split()) != 3:
            await hf.safe_send(ctx, "Invalid options given. Please start over the command and give three answers "
                                    "in one message.")
            return
        choices = msg.content.split()
        if choices[0].casefold() not in ['ban', 'kick', 'mute']:
            await hf.safe_send(ctx, "Your choice for the punishment was not one of either `ban`, `kick`, or `mute`. "
                                    "Please start over the command and try again.")
            return
        try:
            message_threshhold = int(choices[1])
            time_threshhold = int(choices[2])
        except ValueError:
            await hf.safe_send(ctx, "Your choice for either the message or time threshhold was not a number. Please "
                                    "start over the command and try again.")
            return
        self.bot.db['antispam'][str(ctx.guild.id)]['enable'] = True
        self.bot.db['antispam'][str(ctx.guild.id)]['action'] = choices[0]
        self.bot.db['antispam'][str(ctx.guild.id)]['message_threshhold'] = message_threshhold
        self.bot.db['antispam'][str(ctx.guild.id)]['time_threshhold'] = time_threshhold

        await hf.safe_send(ctx, embed=hf.green_embed("Antispam has been configured!"), delete_after=10.0)
        await ctx.invoke(self.antispam, menu)

    @antispam.command(name='ignore')
    async def antispam_ignore(self, ctx: commands.Context, menu: discord.Message, channel: str):
        """Ignores a channel from antispam.

        Usage: `;antispam ignore #channel_name`"""
        re_result = re.search(r"<#(\d{17,22})>", channel)
        if re_result:
            channel_id = int(re_result.group(1))
        else:
            await hf.safe_send(ctx, "I couldn't find that channel. Please mention the channel with #")
            await ctx.invoke(self.antispam.invoke, menu)
            return

        if not channel_id or not self.bot.get_channel(channel_id):
            await hf.safe_send(ctx, "Please mention a valid channel.")
            return

        if not self.bot.db['antispam'].get(str(ctx.guild.id), {}).get('enable', None):
            await hf.safe_send(ctx, "This guild does not have antispam enabled")
            return

        config = self.bot.db['antispam'].get(str(ctx.guild.id))
        if channel_id in config['ignored']:
            config['ignored'].remove(channel_id)
            await hf.safe_send(ctx, "That channel is no longer ignored.")
        else:
            config['ignored'].append(channel_id)
            await hf.safe_send(ctx, "That channel will be ignored in the future.")

        await ctx.invoke(self.antispam.invoke, menu)

    @antispam.command(name='list')
    async def antispam_list(self, ctx: commands.Context, menu: discord.Message,):
        """Lists ignored channels for antispam"""
        if not self.bot.db['antispam'].get(str(ctx.guild.id), {}).get('enable', None):
            await hf.safe_send(ctx, "This guild does not have antispam enabled")
            return

        config = self.bot.db['antispam'].get(str(ctx.guild.id))
        channels = "The list of ignored channels is:\n"
        for i in config['ignored']:
            channel = self.bot.get_channel(i)
            if not channel:
                config['ignored'].remove(i)
                continue
            channels += f"{channel.mention}\n"

        await hf.safe_send(ctx, channels)
        await ctx.invoke(self.antispam.invoke, menu)

    async def antispam_ban_override(self, ctx: commands.Context, menu: discord.Message, config: dict):
        await menu.edit(embed=hf.green_embed("I should override my other selected settings and ban users that "
                                             "spam within `[X]` minutes of joining the server.\n\n"
                                             "Please input an integer number.\n"
                                             "Type `0` to disable the module.\n"
                                             "Type `cancel` to exit."))
        while True:
            try:
                msg: discord.Message = await self.bot.wait_for('message',
                                                               timeout=60.0,
                                                               check=lambda
                                                               m: m.channel == ctx.channel and m.author == ctx.author)

            except asyncio.TimeoutError:
                try:
                    await menu.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass
                await hf.safe_send(ctx, "Menu timed out", delete_after=10.0)
                return

            if msg.content.casefold() == 'cancel':
                try:
                    await menu.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass
                await hf.safe_send(ctx, "Exiting menu", delete_after=10.0)
                return

            try:
                minutes = int(msg.content)
                if minutes < 0:
                    raise ValueError
            except ValueError:
                await hf.safe_send(ctx, "Please input a single number.")
                return

            try:
                await menu.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

            config['ban_override'] = minutes

            try:
                await msg.add_reaction('✅')
            except discord.Forbidden:
                pass

            await ctx.invoke(self.antispam.invoke)

    @commands.command()
    async def vcc(self, ctx):
        """Gives most active voice channels in Spanish server"""
        # ('Join', 1635314436.453157, 871772651314618480, 859845745292214282)
        # ('Leave', 1635314434.395545, 898191413366366228, 902673467969785897)
        # (str: action, timestamp, user_id, channel_id)
        config = self.bot.db['spvoice']
        joins = {}
        times = {}
        for i in config:
            action = i[0]
            time = i[1]
            user_id = i[2]
            channel_id = i[3]
            if action == "Join":
                joins[user_id] = (time, channel_id)
            else:
                if user_id in joins:
                    times[channel_id] = times.get(channel_id, 0) + round(time - joins[user_id][0], 3)
                    del joins[user_id]

        sorted_dict = sorted(list(times.items()), key=lambda channel: channel[1], reverse=True)
        msg = '__Most active voice channels (mins. of voice activity)__\n'
        first_msg = ''  # only to be used if character length goes over 2000char
        for channel in sorted_dict:
            channel_obj = ctx.guild.get_channel_or_thread(channel[0])
            if not channel_obj:
                continue
            category_c = channel_obj.category.name[0].replace("S", " Ｓ ").replace("G", " Ｇ ")
            time = channel[1]
            interval_str = format_interval(time, show_seconds=True)
            addition = f"[{category_c}] {channel_obj.mention}: {interval_str}\n"

            if len(msg + addition) > 2000:
                first_msg = msg
                msg = addition
            else:
                msg += addition

        if first_msg:
            await hf.safe_send(ctx, first_msg)
            await hf.safe_send(ctx, msg)
        else:
            await hf.safe_send(ctx, msg)


async def setup(bot):
    await bot.add_cog(Admin(bot))
