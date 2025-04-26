import asyncio
import re
from datetime import timedelta

import discord
from discord.ext import commands
from .message import Message, on_message_function

from .utils import helper_functions as hf
from cogs.utils.BotUtils import bot_utils as utils

MODCHAT_SERVER_ID = 257984339025985546
RYRY_SPAM_CHAN = 275879535977955330
JP_SERVER_ID = 189571157446492161
SP_SERVER_ID = 243838819743432704
CH_SERVER_ID = 266695661670367232
CL_SERVER_ID = 320439136236601344
RY_SERVER_ID = 275146036178059265
MODBOT_ID = 713245294657273856

ENG_ROLE = {
    266695661670367232: 266778623631949826,  # C-E Learning English Role
    320439136236601344: 474825178204078081  # r/CL Learning English Role
}
RYRY_RAI_BOT_ID = 270366726737231884
on_message_functions = []


class Cnserver(Message):

    # chinese server banned words

    @on_message_function()
    async def chinese_server_banned_words(self, msg: hf.RaiMessage):
        words = ['动态网自由门', '天安門', '天安门', '法輪功', '李洪志', 'Free Tibet', 'Tiananmen Square',
                 '反右派鬥爭', 'The Anti-Rightist Struggle', '大躍進政策', 'The Great Leap Forward', '文化大革命',
                 '人權', 'Human Rights', '民運', 'Democratization', '自由', 'Freedom', '獨立', 'Independence']
        if msg.guild.id not in [CH_SERVER_ID, 494502230385491978, CL_SERVER_ID, RY_SERVER_ID]:
            return
        word_count = 0
        for word in words:
            if word in msg.content:
                word_count += 1
            if word_count == 5:
                mod_channel = self.bot.get_channel(
                    self.bot.db['mod_channel'][str(msg.guild.id)])
                log_channel = self.bot.get_channel(
                    self.bot.db['bans'][str(msg.guild.id)]['channel'])
                if discord.utils.utcnow() - msg.author.joined_at > timedelta(minutes=60):
                    await utils.safe_send(mod_channel,
                                          f"Warning: {msg.author.name} may have said the banned words spam message"
                                          f"\nMessage was posted in {msg.channel.mention}.  Message:"
                                          f"\n```{msg.content}"[:1995] + '```')
                    return
                try:
                    await msg.delete()
                except discord.Forbidden:
                    await utils.safe_send(mod_channel,
                                          "Rai is lacking the permission to delete messages for the Chinese "
                                          "spam message.")
                except discord.NotFound:
                    pass

                try:
                    await asyncio.sleep(3)
                    await msg.author.ban(reason=f"Automatic ban: Chinese banned words spam\n"
                                         f"{msg.content[:100]}", delete_message_seconds=1 * 60 * 60 * 24)
                except discord.Forbidden:
                    await utils.safe_send(mod_channel,
                                          "I tried to ban someone for the Chinese spam message, but I lack "
                                          "the permission to ban users.")

                await utils.safe_send(log_channel, f"Banned {msg.author} for the banned words spam message."
                                      f"\nMessage was posted in {msg.channel.mention}.  Message:"
                                      f"\n```{msg.content}"[:1850] + '```')

                return

    @on_message_function()
    async def cn_lang_check(self, msg, check_hardcore_role=True):
        if msg.guild.id not in [CH_SERVER_ID, CL_SERVER_ID]:
            return
        # removes lines that start with a quote
        content = re.sub("^(>>>|>) .*$\n?", "", msg.content, flags=re.M)
        if len(content) > 3:
            if check_hardcore_role:
                try:
                    role = msg.guild.get_role(
                        self.bot.db['hardcore'][str(msg.guild.id)]['role'])
                except (KeyError, AttributeError):
                    return

                if not hasattr(msg.author, 'roles'):
                    return
                if role not in msg.author.roles:
                    return

            # this function is only called for two guilds
            learning_eng = msg.guild.get_role(ENG_ROLE[msg.guild.id])

            ratio = utils.jpenratio(content)
            if ratio is not None:  # it might be "0" so I can't do "if ratio"
                if learning_eng in msg.author.roles:
                    if ratio < .55:
                        try:
                            await msg.delete()
                        except discord.NotFound:
                            pass
                        if len(content) > 30:
                            await hf.long_deleted_msg_notification(msg)
                else:
                    if ratio > .45:
                        try:
                            await msg.delete()
                        except discord.NotFound:
                            pass
                        if len(content) > 60:
                            await hf.long_deleted_msg_notification(msg)

    @on_message_function()
    async def chinese_server_hardcore_mode(self, msg: hf.RaiMessage):
        if msg.guild.id in [CH_SERVER_ID, CL_SERVER_ID]:
            try:
                if msg.channel.id in self.bot.db['forcehardcore']:
                    await self.cn_lang_check(msg, check_hardcore_role=False)

                else:
                    if isinstance(msg.channel, discord.Thread):
                        channel_id = msg.channel.parent.id
                    elif isinstance(msg.channel, discord.TextChannel):
                        channel_id = msg.channel.id
                    else:
                        return
                    config = self.bot.db['hardcore'][str(
                        CH_SERVER_ID)]['ignore']
                    if '*' not in msg.content and channel_id not in config:
                        await self.cn_lang_check(msg)
            except KeyError:
                self.bot.db['forcehardcore'] = []


async def setup(bot: commands.Bot):
    await bot.add_cog(Cnserver(bot))