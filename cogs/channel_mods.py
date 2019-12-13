import discord
from discord.ext import commands
from .utils import helper_functions as hf
import re

import os
dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


class ChannelMods(commands.Cog):
    """Commands that channel mods can use in their specific channels only. For adding channel \
    mods, see `;help channel_mod`. Submods and admins can also use these commands."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        if not ctx.guild:
            return
        if str(ctx.guild.id) not in self.bot.db['mod_channel'] and ctx.command.name != 'set_mod_channel':
            await hf.safe_send(ctx, "Please set a mod channel using `;set_mod_channel`.")
            return
        if not hf.submod_check(ctx):
            try:
                if ctx.author.id not in self.bot.db['channel_mods'][str(ctx.guild.id)][str(ctx.channel.id)]:
                    return
            except KeyError:
                return
        else:
            return True

    @commands.command(name="delete", aliases=['del'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True, manage_messages=True)
    async def msg_delete(self, ctx, *ids):
        """A command to delete messages for submods.  Usage: `;del <list of IDs>`\n\n
        Example: `;del 589654995956269086 589654963337166886 589654194189893642`"""
        await hf.safe_send(ctx.author, f"I'm gonna delete your message to potentially keep your privacy, but in case "
                                       f"something goes wrong, here was what you sent: \n{ctx.message.content}")
        await ctx.message.delete()
        msgs = []
        failed_ids = []
        invalid_ids = []

        # search ctx.channel for the ids
        for msg_id in ids:
            try:
                msg = await ctx.channel.fetch_message(msg_id)
                msgs.append(msg)
            except discord.NotFound:
                failed_ids.append(msg_id)
            except discord.HTTPException:
                invalid_ids.append(msg_id)
                raise

        if invalid_ids:
            await hf.safe_send(ctx, f"The following IDs were not properly formatted: `{'`, `'.join(invalid_ids)}`")

        # search every channel, not just ctx.channel for the missing IDs
        if failed_ids:
            for channel in ctx.guild.text_channels:
                for msg_id in failed_ids.copy():
                    try:
                        msg = await channel.fetch_message(msg_id)
                        msgs.append(msg)
                        failed_ids.remove(msg_id)
                    except discord.NotFound:
                        break
                    except discord.Forbidden:
                        break
                if not failed_ids:
                    break
        if failed_ids:
            await hf.safe_send(ctx, f"Unable to find ID(s) `{'`, `'.join(failed_ids)}`.")

        if not msgs:
            return  # no messages found

        emb = discord.Embed(title=f"Deleted messages", color=discord.Color(int('ff0000', 16)),
                            description=f"by {ctx.author.mention} ({ctx.author.name}#{ctx.author.discriminator})")
        embeds = []
        for msg_index in range(len(msgs)):
            msg = msgs[msg_index]
            jump_url = ''
            async for msg_history in msg.channel.history(limit=1, before=msg):
                jump_url = msg_history.jump_url
            try:
                await msg.delete()
            except discord.NotFound:
                continue
            except discord.Forbidden:
                await ctx.send(f"I lack the permission to delete messages in {msg.channel.mention}.")
                return
            if msg.embeds:
                for embed in msg.embeds:
                    embeds.append(embed)
                    emb.add_field(name=f"Embed deleted [Jump URL]({jump_url})", value="Content shown below")
            if msg.content:
                emb.add_field(name=f"Message {msg_index} by "
                                   f"{msg.author.name}#{msg.author.discriminator} ({msg.author.id})",
                              value=f"([Jump URL]({jump_url})) {msg.content}"[:1024 - len(jump_url)])
            if msg.content[1024:]:
                emb.add_field(name=f"continued", value=f"...{msg.content[1024-len(jump_url):len(jump_url)+1024]}")
            if msg.attachments:
                x = [f"{att.filename}: {att.proxy_url}" for att in msg.attachments]
                emb.add_field(name="Attachments (might expire soon):", value='\n'.join(x))
            emb.timestamp = msg.created_at
        emb.set_footer(text=f"In #{msgs[0].channel.name} - Message sent at:")
        if str(ctx.guild.id) in self.bot.db['submod_channel']:
            channel = self.bot.get_channel(self.bot.db['submod_channel'][str(ctx.guild.id)])
        elif str(ctx.guild.id) in self.bot.db['mod_channel']:
            channel = self.bot.get_channel(self.bot.db['mod_channel'][str(ctx.guild.id)])
        else:
            await hf.safe_send(ctx, "Please set either a mod channel or a submod channel with "
                                    "`;set_mod_channel` or `;set_submod_channel`")
            return
        await hf.safe_send(channel, embed=emb)
        if embeds:
            for embed in embeds:
                await hf.safe_send(channel, embed=embed)

        @commands.command()
        @commands.bot_has_permissions(send_messages=True, manage_messages=True)
        async def pin(self, ctx, message_id=None):
            """Pin a message"""
            to_be_pinned_msg = None
            if not message_id:
                async for message in ctx.channel.history(limit=2):
                    if message.content == ';pin':
                        continue
                    to_be_pinned_msg = message
            else:
                if not re.search('\d{17,22}', message_id):
                    await hf.safe_send(ctx, "Please input a valid ID")
                    return
                to_be_pinned_msg = await ctx.channel.fetch_message(message_id)
            try:
                await ctx.message.delete()
            except discord.Forbidden:
                pass
            try:
                await to_be_pinned_msg.pin()
            except discord.Forbidden:
                await hf.safe_send(ctx, "I lack permission to pin messages in this channel")

    @commands.command()
    async def log(self, ctx, user, *, reason="None"):
        warn = self.bot.get_command('warn')
        if not await warn.can_run(ctx):
            raise commands.CheckFailure
        if reason:
            reason += ' -s'
        else:
            reason = ' -s'
        await ctx.invoke(warn, user, reason=reason)

    @commands.command(aliases=['w'])
    async def warn(self, ctx, user, *, reason="None"):
        """Log a mod incident"""
        if not hf.submod_check(ctx):
            try:
                if ctx.author.id not in self.bot.db['channel_mods'][str(ctx.guild.id)][str(ctx.channel.id)]:
                    return
            except KeyError:
                return

        re_result = re.search('^<?@?!?([0-9]{17,22})>?$', user)
        if re_result:
            id = int(re_result.group(1))
            user = ctx.guild.get_member(id)
            if not user:
                reason += " -s"
                try:
                    user = await self.bot.fetch_user(id)
                except discord.NotFound:
                    user = None
        else:
            user = None
        if not user:
            await hf.safe_send(ctx, "I could not find the user.  For warns and mutes, please use either an ID or "
                                    "a mention to the user (this is to prevent mistaking people).")
            return
        emb = hf.red_embed(f"Warned on {ctx.guild.name} server")
        silent = False
        if '-s' in reason:
            silent = True
            reason = reason.replace(' -s', '').replace('-s ', '').replace('-s', '')
            emb.description = "Warning *(This incident was not sent to the user)*"
        emb.color = discord.Color(int('ff8800', 16))  # embed
        emb.add_field(name="User", value=f"{user.name} ({user.id})", inline=False)
        emb.add_field(name="Reason", value=reason, inline=False)
        if not silent:
            try:
                await hf.safe_send(user, embed=emb)
            except discord.Forbidden:
                await hf.safe_send(ctx, "I could not send the message, maybe the user has DMs disabled. Canceling "
                                        "warn (consider using the -s tag to not send a message).")
                return
        if not emb.description:
            emb.description = "Warning"
        emb.add_field(name="Jump URL", value=ctx.message.jump_url, inline=False)
        emb.set_footer(text=f"Warned by {ctx.author.name} ({ctx.author.id})")
        config = hf.add_to_modlog(ctx, user, 'Warning', reason, silent)
        modlog_channel = self.bot.get_channel(config['channel'])
        await hf.safe_send(modlog_channel, embed=emb)
        await hf.safe_send(ctx, embed=emb)

    @commands.command(aliases=['channel_helper', 'cm', 'ch'])
    @hf.is_admin()
    async def channel_mod(self, ctx, *, user):
        """Assigns a channel mod"""
        config = self.bot.db['channel_mods'].setdefault(str(ctx.guild.id), {})
        user = await hf.member_converter(ctx, user)
        if not user:
            await ctx.invoke(self.list_channel_mods)
            return
        if str(ctx.channel.id) in config:
            if user.id in config[str(ctx.channel.id)]:
                await hf.safe_send(ctx, "That user is already a channel mod in this channel.")
                return
            else:
                config[str(ctx.channel.id)].append(user.id)
        else:
            config[str(ctx.channel.id)] = [user.id]
        await ctx.message.delete()
        await hf.safe_send(ctx, f"Set {user.name} as a channel mod for this channel", delete_after=5.0)

    @commands.command(aliases=['list_channel_helpers'])
    @hf.is_admin()
    async def list_channel_mods(self, ctx):
        """Lists current channel mods"""
        output_msg = '```md\n'
        for channel_id in self.bot.db['channel_mods'][str(ctx.guild.id)]:
            channel = self.bot.get_channel(int(channel_id))
            output_msg += f"#{channel.name}\n"
            for user_id in self.bot.db['channel_mods'][str(ctx.guild.id)][channel_id]:
                user = self.bot.get_user(int(user_id))
                if not user:
                    await hf.safe_send(ctx, f"<@{user_id}> was not found.  Removing from list...")
                    self.bot.db['channel_mods'][str(ctx.guild.id)][channel_id].remove(user_id)
                    continue
                output_msg += f"{user.display_name}\n"
            output_msg += '\n'
        output_msg += '```'
        await hf.safe_send(ctx, output_msg)

    @commands.command(aliases=['rcm', 'rch'])
    @hf.is_admin()
    async def remove_channel_mod(self, ctx, user):
        """Removes a channel mod"""
        config = self.bot.db['channel_mods'].setdefault(str(ctx.guild.id), {})
        user = await hf.member_converter(ctx, user)
        if not user:
            return
        if str(ctx.channel.id) in config:
            if user.id not in config[str(ctx.channel.id)]:
                await hf.safe_send(ctx, "That user is not a channel mod in this channel.")
                return
            else:
                config[str(ctx.channel.id)].remove(user.id)
                if not config[str(ctx.channel.id)]:
                    del config[str(ctx.channel.id)]
        else:
            return
        await ctx.message.delete()
        await hf.safe_send(ctx, f"Removed {user.name} as a channel mod for this channel", delete_after=5.0)


def setup(bot):
    bot.add_cog(ChannelMods(bot))
