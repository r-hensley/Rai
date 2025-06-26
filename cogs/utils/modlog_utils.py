# pylint: disable=C0301,C0116,c0114
from typing import Optional
from datetime import datetime, timezone
import discord
from discord.ext import commands
from cogs import channel_mods as cm
from cogs.utils.BotUtils import bot_utils as utils
from . import helper_functions as hf


# async def resolve_user(ctx, id_in: str, bot) -> Tuple[Optional[discord.Member], Optional[discord.User], Optional[str]]:
#     member: discord.Member = await utils.member_converter(ctx, id_in)
#     if member:
#         return member, member, str(member.id)
#     try:
#         user = await bot.fetch_user(int(id_in))
#         return None, user, id_in
#     except (discord.NotFound, discord.HTTPException, ValueError):
#         return None, None, None
def save_db(bot, path="db.json"):
    import json
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(bot.db, f, indent=4)
        print("✅ Database saved to disk")
    except Exception as e:  # pylint: disable=W0718
        print(f"❌ Failed to save DB: {e}")


async def resolve_user(ctx: commands.Context, id_arg: str, bot) -> tuple[Optional[discord.User], Optional[str]]:
    try:
        member = await commands.MemberConverter().convert(ctx, id_arg)
        return member, member, str(member.id)
    except commands.BadArgument:
        try:
            user = await commands.UserConverter().convert(ctx, id_arg)
            return None, user, str(user.id)
        except commands.BadArgument:
            try:
                user = await bot.fetch_user(int(id_arg))
                return user, str(user.id)
            except (discord.NotFound, discord.HTTPException, ValueError):
                return None, None, None


async def get_user_status(ctx, guild_id: str, member: Optional[discord.Member], user: Optional[discord.User]):
    db = ctx.bot.db
    user_id = str((member or user).id)

    muted = False
    unmute_date = None
    if unmute_date_str := db['mutes'].get(guild_id, {}).get('timed_mutes', {}).get(user_id, ""):
        muted = True
        unmute_date = hf.convert_to_datetime(unmute_date_str)

    voice_muted = False
    voice_unmute_date = None
    if voice_unmute_str := db['voice_mutes'].get(guild_id, {}).get('timed_mutes', {}).get(user_id, None):
        voice_muted = True
        voice_unmute_date = hf.convert_to_datetime(voice_unmute_str)

    if member:
        mute_role_id: str = db['mutes'].get(guild_id, {}).get('role', 0)
        mute_role: discord.Role = ctx.guild.get_role(int(mute_role_id))
        if mute_role and mute_role in member.roles:
            muted = True

        voice_role_id: str = db['voice_mutes'].get(guild_id, {}).get('role', 0)
        voice_role: discord.Role = ctx.guild.get_role(int(voice_role_id))
        if voice_role and voice_role in member.roles:
            voice_muted = True

    timeout = member.is_timed_out() if member else False

    banned = False
    unban_date = None
    if user:
        try:
            await ctx.guild.fetch_ban(user)
            banned = True
            if unban_str := db['bans'].get(guild_id, {}).get('timed_bans', {}).get(user_id, None):
                unban_date = hf.convert_to_datetime(unban_str)
        except (discord.NotFound, discord.HTTPException, discord.Forbidden):
            pass

    return {
        "muted": muted,
        "unmute_date": unmute_date,
        "voice_muted": voice_muted,
        "voice_unmute_date": voice_unmute_date,
        "timeout": timeout,
        "banned": banned,
        "unban_date": unban_date
    }


def get_user_stats(bot, guild_id: str, member: discord.Member):
    total_msgs_month = 0
    total_msgs_week = 0
    message_count = {}

    if guild_id in bot.stats:
        stats_config = bot.stats[guild_id].get('messages', {})
        for day, users in stats_config.items():
            if str(member.id) in users:
                user_stats = users[str(member.id)]
                if 'channels' not in user_stats:
                    continue
                for channel, count in user_stats['channels'].items():
                    message_count[channel] = message_count.get(
                        channel, 0) + count
                    days_ago = (discord.utils.utcnow(
                    ) - datetime.strptime(day, "%Y%m%d").replace(tzinfo=timezone.utc)).days
                    if days_ago <= 7:
                        total_msgs_week += count
                    total_msgs_month += count

    voice_time_str = "0h"
    if 'voice' in bot.stats.get(guild_id, {}):
        total_voice = 0
        for day, voice_data in bot.stats[guild_id]['voice']['total_time'].items():
            if str(member.id) in voice_data:
                total_voice += voice_data[str(member.id)]
        voice_time_str = hf.format_interval(total_voice * 60)

    sentiment_str = None
    if guild_id in bot.db.get('sentiments', {}):
        user_sentiment = bot.db['sentiments'][guild_id].get(str(member.id), [])
        num_msgs = len(user_sentiment)
        if num_msgs:
            if num_msgs == 1000:
                sentiment_str = f"{round(sum(user_sentiment), 2)}"
            else:
                sentiment_str = f"{round(sum(user_sentiment) * 1000 / num_msgs, 2)}"

    return {
        "month": total_msgs_month,
        "week": total_msgs_week,
        "voice": voice_time_str,
        "sentiment": sentiment_str,
        "sentiment_count": num_msgs if sentiment_str else 0
    }


def format_modlog_entries(config, user_id: str):
    logs: list = config.get(user_id, [])
    valid_logs = []
    for entry in logs:
        if entry.get('silent') and entry['type'] == "AutoMod":
            continue
        valid_logs.append(entry)

    fields = []
    for entry in valid_logs:
        name = f"{logs.index(entry) + 1}) "
        name += "Silent Log" if entry['silent'] and entry['type'] == "Warning" else entry['type']
        if entry['silent'] and entry['type'] != "Warning":
            name += " (silent)"

        # incident_time = hf.convert_to_datetime(entry['date'])
        value = f"<t:{entry['date']}:f>\n" if isinstance(
            entry['date'], int) else f"<t:{int(hf.convert_to_datetime(entry['date']).timestamp())}:f>\n"
        if entry['length']:
            value += f"*For {entry['length']}*\n"
        if entry['reason']:
            value += f"__Reason__: {entry['reason']}\n"
        if entry['jump_url']:
            value += f"[Jump URL]({entry['jump_url']})\n"

        fields.append((name, value[:1024]))

    return fields


async def build_modlog_embed(bot, ctx: commands.Context, user: Optional[discord.User], page: int = 0) -> discord.Embed:
    user_id = str(user.id)
    guild_id = str(ctx.guild.id)
    config = bot.db['modlog'].get(guild_id, {})

    emb = utils.green_embed("")
    name = f"{str(user)} ({getattr(user, 'nick', '')})\n{user_id}" if getattr(
        user, "nick", None) else f"{str(user)}\n{user_id}"
    emb.set_author(name=name,
                   icon_url=user.display_avatar.replace(
                       static_format="png").url
                   )
    # emb.set_thumbnail(url=user.display_avatar.url)

    # ==== Modlog Entries ====
    fields = format_modlog_entries(config, user_id)
    # Pagination: show 5 per page
    per_page = 5
    total_pages = (len(fields) - 1) // per_page + 1 if fields else 1
    start = page * per_page
    end = start + per_page
    page_fields = fields[start:end]

    for name, value in page_fields:
        emb.add_field(name=name, value=value, inline=False)

    if not fields:
        emb.color = utils.grey_embed("").color
        emb.description += "\n***>> NO MODLOG ENTRIES << ***"
    else:
        emb.set_footer(text=f"Page {page + 1} of {total_pages}")

    return emb


async def build_user_summary_embed(bot, ctx: commands.Context, member: Optional[discord.Member], user: Optional[discord.User]) -> discord.Embed:
    guild_id = str(ctx.guild.id)
    user_id = str(user.id)

    # ==== Basic Embed Setup ====
    emb = utils.green_embed("")
    name = f"Username: {str(user)}\nDisplay name: {getattr(user, 'nick', '')}\n{user_id}" if getattr(
        user, "nick", None) else f"{str(user)}\n{user_id}"
    emb.set_author(name=name,
                   #    icon_url=user.display_avatar.replace(static_format="png").url
                   )
    emb.set_thumbnail(url=user.display_avatar.url)

    # ==== User Status ====
    status = await get_user_status(ctx, guild_id, member, user)

    if status['banned']:
        emb.color = 0x141414
        emb.description += f"**`Current Status`** Temporarily Banned (unban <t:{int(status['unban_date'].timestamp())}:R>)\n" if status[
            'unban_date'] else "**`Current Status`** Indefinitely Banned\n"
    elif status['voice_muted']:
        emb.color = utils.red_embed("").color
        emb.description += f"**`Current Status`** Voice Muted (unmute <t:{int(status['voice_unmute_date'].timestamp())}:R>)\n" if status[
            'voice_unmute_date'] else "**`Current Status`** Indefinitely Voice Muted\n"
    elif status['muted']:
        emb.color = utils.red_embed("").color
        emb.description += f"**`Current Status`** Muted (unmute <t:{int(status['unmute_date'].timestamp())}:R>)\n" if status[
            'unmute_date'] else "**`Current Status`** Indefinitely Muted\n"
    elif status['timeout']:
        emb.color = utils.red_embed("").color
        if member.timed_out_until:
            emb.description += f"**`Current Status`** Timed out (expires <t:{int(member.timed_out_until.timestamp())}:R>)\n"
    elif not member:
        emb.color = utils.grey_embed("").color
        emb.description += "**`Current Status`** : User is not in server\n"
    else:
        emb.description += "**`Current Status`** : No active incidents\n"

    # ==== Stats ====
    if member:
        stats = get_user_stats(bot, guild_id, member)
        emb.description += f"\n**`Number of messages M | W`** : {stats['month']} | {stats['week']}"
        emb.description += f"\n**`Time in voice`** : {stats['voice']}"
        if stats['sentiment']:
            emb.description += f"\n**`Recent sentiment ({stats['sentiment_count']} msgs)`** : {stats['sentiment']}"

    # ==== Log count====
    modlog_config = bot.db.get("modlog", {}).get(str(ctx.guild.id), {})
    user_logs = modlog_config.get(str(user_id), [])

    log_count = len(user_logs)
    emb.description += f"\n**`Modlog Entries`** : {log_count}"

    # ==== Language Roles ====
    if member:
        lang_roles = [243853718758359040,
                      243854128424550401, 247020385730691073]
        found_roles = [
            r.mention for r in member.roles if r.id in lang_roles]
        if found_roles:
            emb.description += "\n**`Current Language Roles`** : " + \
                ", ".join(found_roles)

    # ==== Mention and Join Info ====
    if member:
        emb.description += f"\n{member.mention}\n"
        emb.set_footer(text="Join Date")
        emb.timestamp = member.joined_at
    else:
        emb.set_footer(text="User not in server")

    # ==== Join History ====
    join_history = bot.db.get('joins', {}).get(
        guild_id, {}).get('join_history', {}).get(user_id, None)
    if join_history:
        if member and datetime(2021, 6, 25, tzinfo=timezone.utc) <= member.joined_at <= datetime(2022, 7, 24, tzinfo=timezone.utc):
            join_history = await cm.fix_join_history_invite(ctx, user_id, join_history)
        else:
            join_history = await cm.fix_join_history_invite(ctx, user_id, join_history)

        if invite := join_history.get('invite'):
            if invite not in ['Through server discovery', ctx.guild.vanity_url_code]:
                invite_creator_id = join_history.get('invite_creator')
                if not invite_creator_id:
                    invite_obj = discord.utils.find(lambda i: i.code == invite, await ctx.guild.invites())
                    if not invite_obj and invite == ctx.guild.vanity_url_code:
                        invite_obj = await ctx.guild.vanity_invite()
                    invite_creator_id = getattr(
                        getattr(invite_obj, "inviter", None), "id", None)

                invite_creator_user = None
                if invite_creator_id:
                    try:
                        invite_creator_user = await bot.fetch_user(invite_creator_id)
                    except (discord.NotFound, discord.HTTPException):
                        pass

                invite_author_str = f"by {str(invite_creator_user)} ([ID](https://rai/inviter-id-is-I{invite_creator_id}))" if invite_creator_user else "by unknown user"
            else:
                invite_author_str = ""

            emb.description += f"\n[**`Used Invite`**]({join_history['jump_url']}) : {invite} {invite_author_str}"

    # ==== Spam Flags ====
    if member:
        excessive = await hf.excessive_dm_activity(ctx.guild.id, user_id)
        spammy = await hf.suspected_spam_activity_flag(ctx.guild.id, user_id)
        if excessive or spammy:
            emb.description += "\n⚠️ **__User Flags__** ⚠️\n"
        if excessive:
            emb.description += "**`Excessive DMs`** : User has been flagged for excessive DMs\n"
        if spammy:
            emb.description += "**`Suspected Spam`** : User has been flagged for suspected spam activity\n"

    return emb


def build_log_entry_embed(entry: dict, user: discord.User, index: int) -> discord.Embed:
    """
    Build an embed showing a detailed view of a single modlog entry.

    :param entry: The modlog entry dict.
    :param user: The discord.User the log belongs to.
    :param index: The index of the entry in the user's log list.
    :return: discord.Embed
    """
    embed = discord.Embed(
        title=f"Log Entry #{index + 1} — {entry.get('type', 'Unknown')}",
        color=discord.Color.orange()
    )

    embed.set_author(name=str(user), icon_url=user.display_avatar.replace(
        static_format="png").url)

    # Add fields
    embed.add_field(name="Reason", value=entry.get(
        "reason", "No reason provided."), inline=False)

    length = entry.get("length")
    if length:
        embed.add_field(name="Duration", value=length, inline=True)

    if entry.get("silent"):
        embed.add_field(name="Silent", value="Yes", inline=True)

    if entry.get("jump_url"):
        embed.add_field(
            name="Jump URL", value=f"[Click here]({entry['jump_url']})", inline=False)
    if entry.get('author'):
        embed.add_field(
            name='Date', value=f"<t:{entry['date']}:f>\n" if isinstance(
                entry['date'], int) else f"<t:{int(hf.convert_to_datetime(entry['date']).timestamp())}:f>\n")
        embed.set_footer(
            text=f"By {entry.get('author')} ({entry.get('author_id')})")
    if "date_edited" in entry:
        embed.set_footer(
            text=f"{embed.footer.text} | Edited: {entry['date_edited']}")

    return embed


async def get_modlog_entries(guild_id: int, user_id: str, bot) -> list[dict]:
    g_id = str(guild_id)
    if g_id in bot.db["modlog"] and user_id in bot.db["modlog"][g_id]:
        return bot.db["modlog"][g_id][user_id]
    return []


def build_log_message_embed(entry: dict, user: discord.User) -> discord.Embed:
    """
    Build an embed showing a detailed view of a single modlog entry.

    :param entry: The modlog entry dict.
    :param user: The discord.User the log belongs to.
    :param index: The index of the entry in the user's log list.
    :return: discord.Embed
    """

    embed = discord.Embed(
        title=f"{entry.get('type')}",
        color=discord.Color.orange()
    )

    # Add fields
    embed.add_field(name="User", value=f"{user} ({user.id})")
    embed.add_field(name="Reason", value=entry.get(
        "reason", "No reason provided."), inline=False)

    length = entry.get("length")
    if length:
        embed.add_field(name="Duration", value=length, inline=True)

    if entry.get("silent"):
        embed.add_field(name="Silent", value="Yes", inline=True)

    if entry.get("jump_url"):
        embed.add_field(
            name="Jump URL", value=f"[Click here]({entry['jump_url']})", inline=False)
    if entry.get('author'):
        embed.add_field(
            name='Date', value=f"<t:{entry.get('date', 'Unknown')}:f>")
        embed.set_footer(
            text=f"By {entry.get('author')} ({entry.get('author_id')})")
    if "date_edited" in entry:
        embed.set_footer(
            text=f"{embed.footer.text} | Edited: {entry['date_edited']}")

    return embed
