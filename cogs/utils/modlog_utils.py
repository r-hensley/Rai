# pylint: disable=C0301,C0116,c0114
import os
from typing import Optional, Tuple, Union, List, Dict, Any
from datetime import datetime, timezone
import shutil
import json
import discord
from discord.ext import commands
from cogs import channel_mods as cm
from cogs.utils.BotUtils import bot_utils as utils
from cogs.utils import helper_functions as hf


class ModLogEntry:
    """Represents a single modlog entry with methods for manipulation and formatting."""
    
    def __init__(self, entry_type: str, reason: str = "", author: str = "", author_id: str = "", 
                 length: str = "", silent: bool = False, jump_url: str = "", 
                 date: Optional[Union[int, str, datetime]] = None, date_edited: Optional[str] = None):
        self.type = entry_type
        self.reason = reason or "No reason provided"
        self.author = author
        self.author_id = author_id
        self.length = length
        self.silent = silent
        self.jump_url = jump_url
        self.date_edited = date_edited
        
        # Handle date conversion
        if date is None:
            self.date = int(datetime.now(timezone.utc).timestamp())
        elif isinstance(date, datetime):
            self.date = int(date.timestamp())
        elif isinstance(date, str):
            converted_date = hf.convert_to_datetime(date)
            self.date = int(converted_date.timestamp()) if converted_date else int(datetime.now(timezone.utc).timestamp())
        else:
            self.date = date
    
    @classmethod
    def from_dict(cls, data: dict) -> "ModLogEntry":
        """Create a ModLogEntry from a dictionary."""
        return cls(
            entry_type=data.get('type', 'Unknown'),
            reason=data.get('reason', ''),
            author=data.get('author', ''),
            author_id=data.get('author_id', ''),
            length=data.get('length', ''),
            silent=data.get('silent', False),
            jump_url=data.get('jump_url', ''),
            date=data.get('date'),
            date_edited=data.get('date_edited')
        )
    
    def to_dict(self) -> dict:
        """Convert the ModLogEntry to a dictionary for database storage."""
        data = {
            'type': self.type,
            'reason': self.reason,
            'date': self.date,
            'silent': self.silent
        }
        
        # Only include non-empty optional fields
        if self.author:
            data['author'] = self.author
        if self.author_id:
            data['author_id'] = self.author_id
        if self.length:
            data['length'] = self.length
        if self.jump_url:
            data['jump_url'] = self.jump_url
        if self.date_edited:
            data['date_edited'] = self.date_edited
            
        return data
    
    def is_visible(self) -> bool:
        """Check if this entry should be visible (not silent AutoMod)."""
        return not (self.silent and self.type == "AutoMod")
    
    def get_display_name(self, index: int) -> str:
        """Get the display name for this entry."""
        name = f"{index + 1}) "
        if self.silent and self.type == "Warning":
            name += "Silent Log"
        else:
            name += self.type
            if self.silent and self.type != "Warning":
                name += " (silent)"
        return name
    
    def get_formatted_value(self) -> str:
        """Get the formatted value string for embed fields."""
        value = f"<t:{self.date}:f>\n"
        
        if self.length:
            value += f"*For {self.length}*\n"
        if self.reason:
            value += f"__Reason__: {self.reason}\n"
        if self.jump_url:
            value += f"[Jump URL]({self.jump_url})\n"
            
        return value[:1024]
    
    def build_embed(self, user: discord.User, index: int) -> discord.Embed:
        """Build a detailed embed for this entry."""
        embed = discord.Embed(
            title=f"Log Entry #{index + 1} — {self.type}",
            color=discord.Color.orange()
        )
        
        embed.set_author(name=str(user), icon_url=user.display_avatar.replace(static_format="png").url)
        embed.add_field(name="Reason", value=self.reason, inline=False)
        
        if self.length:
            embed.add_field(name="Duration", value=self.length, inline=True)
        
        if self.silent:
            embed.add_field(name="Silent", value="Yes", inline=True)
        
        if self.jump_url:
            embed.add_field(name="Jump URL", value=f"[Click here]({self.jump_url})", inline=False)
        
        if self.author:
            embed.add_field(name='Date', value=f"<t:{self.date}:f>")
            embed.set_footer(text=f"By {self.author} ({self.author_id})")
        
        if self.date_edited:
            current_footer = embed.footer.text if embed.footer else ""
            embed.set_footer(text=f"{current_footer} | Edited: {self.date_edited}")
        
        return embed
    
    def build_message_embed(self, user: discord.User) -> discord.Embed:
        """Build a message embed for this entry."""
        embed = discord.Embed(title=self.type, color=discord.Color.orange())
        
        embed.add_field(name="User", value=f"{user} ({user.id})")
        embed.add_field(name="Reason", value=self.reason, inline=False)
        
        if self.length:
            embed.add_field(name="Duration", value=self.length, inline=True)
        
        if self.silent:
            embed.add_field(name="Silent", value="Yes", inline=True)
        
        if self.jump_url:
            embed.add_field(name="Jump URL", value=f"[Click here]({self.jump_url})", inline=False)
        
        if self.author:
            embed.add_field(name='Date', value=f"<t:{self.date}:f>")
            embed.set_footer(text=f"By {self.author} ({self.author_id})")
        
        if self.date_edited:
            current_footer = embed.footer.text if embed.footer else ""
            embed.set_footer(text=f"{current_footer} | Edited: {self.date_edited}")
        
        return embed
    
    def update(self, **kwargs) -> None:
        """Update entry fields."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        
        # Update edit timestamp
        self.date_edited = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


class UserProfile:
    """Comprehensive user profile class that serves as a single source of truth for user data."""
    
    def __init__(self, bot: commands.Bot, ctx_or_interaction: Union[commands.Context, discord.Interaction], 
                 user_id: str):
        self.bot = bot
        self.ctx = ctx_or_interaction
        self.guild = ctx_or_interaction.guild
        self.guild_id = str(self.guild.id) if self.guild else ""
        self.user_id = str(user_id)
        
        # Discord objects (to be populated)
        self.member: Optional[discord.Member] = None
        self.user: Optional[discord.User] = None
        
        # Cached data
        self._status: Optional[Dict[str, Any]] = None
        self._stats: Optional[Dict[str, Any]] = None
        self._modlog_entries: Optional[List[ModLogEntry]] = None
        self._join_history: Optional[Dict[str, Any]] = None
    
    @classmethod
    async def create(cls, bot: commands.Bot, ctx_or_interaction: Union[commands.Context, discord.Interaction], 
                     user_id: str) -> Optional["UserProfile"]:
        """Factory method to create and initialize a UserProfile."""
        profile = cls(bot, ctx_or_interaction, user_id)
        success = await profile._resolve_user()
        return profile if success else None
    
    async def _resolve_user(self) -> bool:
        """Resolve the Discord user/member objects."""
        try:
            user_id_int = int(self.user_id.strip("<@!>"))
        except ValueError:
            return False
        
        if self.guild:
            self.member = self.guild.get_member(user_id_int)
            if self.member is None:
                try:
                    self.member = await self.guild.fetch_member(user_id_int)
                except (discord.NotFound, discord.HTTPException):
                    self.member = None
        
        if self.member:
            self.user = self.member  # Member inherits from User
        else:
            try:
                self.user = self.bot.get_user(user_id_int)
                if self.user is None:
                    self.user = await self.bot.fetch_user(user_id_int)
            except (discord.NotFound, discord.HTTPException):
                return False
        
        return self.user is not None
    
    @property
    def discord_user(self) -> Optional[discord.User]:
        """Get the Discord user object."""
        return self.user
    
    @property
    def display_name(self) -> str:
        """Get the display name of the user."""
        if self.member:
            return self.member.display_name
        return str(self.user) if self.user else "Unknown User"
    
    @property
    def mention(self) -> str:
        """Get the mention string for the user."""
        return self.member.mention if self.member else f"<@{self.user_id}>"
    
    async def get_status(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Get user moderation status (muted, banned, etc.)."""
        if self._status is None or force_refresh:
            self._status = await get_user_status(self.ctx, self.guild_id, self.member, self.user)
        return self._status
    
    async def get_stats(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Get user statistics (messages, voice time, sentiment)."""
        if (self._stats is None or force_refresh) and self.member:
            self._stats = get_user_stats(self.bot, self.guild_id, self.member)
        return self._stats or {}
    
    async def get_modlog_entries(self, force_refresh: bool = False) -> List[ModLogEntry]:
        """Get user's modlog entries as ModLogEntry objects."""
        if self._modlog_entries is None or force_refresh:
            raw_entries = await get_modlog_entries(int(self.guild_id), self.user_id, self.bot)
            self._modlog_entries = [ModLogEntry.from_dict(entry) for entry in raw_entries]
        return self._modlog_entries
    
    async def get_visible_modlog_entries(self) -> List[ModLogEntry]:
        """Get only visible modlog entries (excluding silent AutoMod)."""
        entries = await self.get_modlog_entries()
        return [entry for entry in entries if entry.is_visible()]
    
    async def add_modlog_entry(self, entry: ModLogEntry) -> None:
        """Add a new modlog entry."""
        # Ensure modlog structure exists
        if not hasattr(self.bot, 'db'):
            return
        
        if "modlog" not in self.bot.db:
            self.bot.db["modlog"] = {}
        if self.guild_id not in self.bot.db["modlog"]:
            self.bot.db["modlog"][self.guild_id] = {}
        if self.user_id not in self.bot.db["modlog"][self.guild_id]:
            self.bot.db["modlog"][self.guild_id][self.user_id] = []
        
        # Add entry to database
        self.bot.db["modlog"][self.guild_id][self.user_id].append(entry.to_dict())
        
        # Update cache
        if self._modlog_entries is not None:
            self._modlog_entries.append(entry)
    
    async def update_modlog_entry(self, index: int, **kwargs) -> bool:
        """Update a modlog entry by index."""
        if not hasattr(self.bot, 'db'):
            return False
            
        entries = await self.get_modlog_entries()
        if 0 <= index < len(entries):
            entries[index].update(**kwargs)
            # Update in database
            self.bot.db["modlog"][self.guild_id][self.user_id][index] = entries[index].to_dict()
            return True
        return False
    
    async def delete_modlog_entry(self, index: int) -> bool:
        """Delete a modlog entry by index."""
        if not hasattr(self.bot, 'db'):
            return False
            
        entries = await self.get_modlog_entries()
        if 0 <= index < len(entries) and self._modlog_entries is not None:
            # Remove from database
            del self.bot.db["modlog"][self.guild_id][self.user_id][index]
            # Update cache
            del self._modlog_entries[index]
            return True
        return False
    
    async def get_join_history(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """Get user's join history."""
        if not hasattr(self.bot, 'db'):
            return None
            
        if self._join_history is None or force_refresh:
            join_history = self.bot.db.get('joins', {}).get(self.guild_id, {}).get('join_history', {}).get(self.user_id)
            if join_history and self.member:
                # Fix invite history if needed - only for commands.Context
                if (isinstance(self.ctx, commands.Context) and self.member.joined_at and 
                    datetime(2021, 6, 25, tzinfo=timezone.utc) <= self.member.joined_at <= datetime(2022, 7, 24, tzinfo=timezone.utc)):
                    join_history = await cm.fix_join_history_invite(self.ctx, int(self.user_id), join_history)
            self._join_history = join_history
        return self._join_history
    
    async def get_language_roles(self) -> List[discord.Role]:
        """Get user's language roles."""
        if not self.member:
            return []
        
        lang_role_ids = [243853718758359040, 243854128424550401, 247020385730691073]
        return [role for role in self.member.roles if role.id in lang_role_ids]
    
    async def get_user_flags(self) -> Dict[str, bool]:
        """Get user warning flags (excessive DMs, spam, etc.)."""
        if not self.member or not self.guild:
            return {"excessive_dms": False, "suspected_spam": False}
        
        try:
            excessive = await hf.excessive_dm_activity(self.guild.id, int(self.user_id))
            spammy = await hf.suspected_spam_activity_flag(self.guild.id, int(self.user_id))
            
            return {
                "excessive_dms": bool(excessive),
                "suspected_spam": bool(spammy)
            }
        except Exception:
            return {"excessive_dms": False, "suspected_spam": False}
    
    async def build_summary_embed(self) -> discord.Embed:
        """Build a comprehensive user summary embed."""
        if not self.user:
            return utils.red_embed("User not found")
        
        # Basic embed setup
        emb = utils.green_embed("")
        if not emb.description:
            emb.description = ""
            
        name = f"Username: {str(self.user)}\nDisplay name: {getattr(self.user, 'nick', '')}\n{self.user_id}" if getattr(
            self.user, "nick", None) else f"{str(self.user)}\n{self.user_id}"
        emb.set_author(name=name)
        emb.set_thumbnail(url=self.user.display_avatar.url)
        
        # User status
        status = await self.get_status()
        
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
            if self.member and self.member.timed_out_until:
                emb.description += f"**`Current Status`** Timed out (expires <t:{int(self.member.timed_out_until.timestamp())}:R>)\n"
        elif not self.member:
            emb.color = utils.grey_embed("").color
            emb.description += "**`Current Status`** : User is not in server\n"
        else:
            emb.description += "**`Current Status`** : No active incidents\n"
        
        # Stats
        if self.member:
            stats = await self.get_stats()
            emb.description += f"\n**`# of messages M | W`** : {stats.get('month', 0)} | {stats.get('week', 0)}"
            emb.description += f"\n**`Time in voice`** : {stats.get('voice', '0h')}"
            if stats.get('sentiment'):
                emb.description += f"\n**`Recent sentiment ({stats.get('sentiment_count', 0)} msgs)`** : {stats['sentiment']}"
        
        # Log count
        entries = await self.get_modlog_entries()
        emb.description += f"\n**`Modlog Entries`** : {len(entries)}"
        
        # Language roles
        lang_roles = await self.get_language_roles()
        if lang_roles:
            emb.description += "\n**`Current Language Roles`** : " + ", ".join([r.mention for r in lang_roles])
        
        # Mention and join info
        if self.member:
            emb.description += f"\n{self.member.mention}\n"
            emb.set_footer(text="Join Date")
            emb.timestamp = self.member.joined_at
        else:
            emb.set_footer(text="User not in server")
        
        # Join history
        join_history = await self.get_join_history()
        if join_history and self.guild:
            if invite := join_history.get('invite'):
                if invite not in ['Through server discovery', self.guild.vanity_url_code]:
                    invite_creator_id = join_history.get('invite_creator')
                    if not invite_creator_id:
                        invite_obj = discord.utils.find(lambda i: i.code == invite, await self.guild.invites())
                        if not invite_obj and invite == self.guild.vanity_url_code:
                            invite_obj = await self.guild.vanity_invite()
                        invite_creator_id = getattr(getattr(invite_obj, "inviter", None), "id", None)
                    
                    invite_creator_user = None
                    if invite_creator_id:
                        try:
                            invite_creator_user = await self.bot.fetch_user(invite_creator_id)
                        except (discord.NotFound, discord.HTTPException):
                            pass
                    
                    invite_author_str = f"by {str(invite_creator_user)} ([ID](https://rai/inviter-id-is-I{invite_creator_id}))" if invite_creator_user else "by unknown user"
                else:
                    invite_author_str = ""
                
                emb.description += f"\n[**`Used Invite`**]({join_history['jump_url']}) : {invite} {invite_author_str}"
        
        # User flags
        if self.member:
            flags = await self.get_user_flags()
            if flags.get('excessive_dms') or flags.get('suspected_spam'):
                emb.description += "\n⚠️ **__User Flags__** ⚠️\n"
            if flags.get('excessive_dms'):
                emb.description += "**`Excessive DMs`** : User has been flagged for excessive DMs\n"
            if flags.get('suspected_spam'):
                emb.description += "**`Suspected Spam`** : User has been flagged for suspected spam activity\n"
        
        return emb
    
    async def build_modlog_embed(self, page: Optional[int] = None) -> Tuple[discord.Embed, int]:
        """Build a modlog embed with pagination."""
        if not self.user:
            return utils.red_embed("User not found"), 0
        
        emb = utils.green_embed("")
        if not emb.description:
            emb.description = ""
            
        name = f"{str(self.user)} ({getattr(self.user, 'nick', '')})\n{self.user_id}" if getattr(
            self.user, "nick", None) else f"{str(self.user)}\n{self.user_id}"
        emb.set_author(name=name, icon_url=self.user.display_avatar.replace(static_format="png").url)
        
        # Get visible entries
        entries = await self.get_visible_modlog_entries()
        
        # Format entries
        fields = []
        for i, entry in enumerate(entries):
            name = entry.get_display_name(i)
            value = entry.get_formatted_value()
            fields.append((name, value))
        
        # Pagination
        per_page = 5
        total_pages = (len(fields) - 1) // per_page + 1 if fields else 1
        if page is None:
            page = total_pages - 1
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
        
        return emb, total_pages - 1


def save_db(bot, path="db.json", backup=True):
    temp_path = path + ".tmp"
    backup_path = path + ".bak"

    try:
        if backup and os.path.exists(path):
            shutil.copy2(path, backup_path)

        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(bot.db, f, indent=2)

        os.replace(temp_path, path)
    except Exception as e:
        print(f"Failed to save DB: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)


# Example usage of the new classes (compatible with both ctx and interactions):
# 
# # Create a UserProfile with commands.Context
# profile = await UserProfile.create(bot, ctx, "123456789")
# if profile:
#     embed = await profile.build_summary_embed()
#     await ctx.send(embed=embed)
# 
# # Create a UserProfile with discord.Interaction
# profile = await UserProfile.create(interaction.client, interaction, "123456789")
# if profile:
#     embed = await profile.build_summary_embed()
#     await interaction.response.send_message(embed=embed)
#     
#     # Add a modlog entry
#     entry = ModLogEntry(
#         entry_type="Warning",
#         reason="Inappropriate behavior",
#         author=interaction.user.name,
#         author_id=str(interaction.user.id)
#     )
#     await profile.add_modlog_entry(entry)
#     
#     # Get modlog entries
#     entries = await profile.get_modlog_entries()
#     for entry in entries:
#         if entry.is_visible():
#             print(f"Entry: {entry.type} - {entry.reason}")
# 
# # Using standalone functions
# # For ctx:
# embed = await build_user_summary_embed(bot, ctx, member, user)
# # For interaction:
# embed = await build_user_summary_embed(interaction.client, interaction, member, user)


async def resolve_user(ctx_or_interaction: Union[discord.Interaction, commands.Context],
                       user_id: str,
                       bot: commands.Bot
                       ) -> Tuple[Optional[discord.Member], Optional[discord.User], Optional[str]]:
    try:
        # also strip mention chars if present
        user_id_int = int(user_id.strip("<@!>"))
    except ValueError:
        return None, None, None
    guild = ctx_or_interaction.guild
    member = None
    user = None

    if guild:
        member = guild.get_member(user_id_int)
        if member is None:
            try:
                member = await guild.fetch_member(user_id_int)
            except (discord.NotFound, discord.HTTPException):
                member = None

    if member:
        return member, member, str(member.id)
    try:
        user = bot.get_user(user_id_int)
        if user is None:
            user = await bot.fetch_user(user_id_int)
        return None, user, str(user.id)
    except (discord.NotFound, discord.HTTPException):
        return None, None, None


async def get_user_status(ctx_or_interaction: Union[commands.Context, discord.Interaction], guild_id: str, member: Optional[discord.Member], user: Optional[discord.User]):
    bot = get_bot(ctx_or_interaction)
    db = bot.db
    user_id = str((member or user).id)
    
    # Get guild object from either ctx or interaction
    guild = getattr(ctx_or_interaction, 'guild', None)
    if not guild:
        return {
            "muted": False,
            "unmute_date": None,
            "voice_muted": False,
            "voice_unmute_date": None,
            "timeout": False,
            "banned": False,
            "unban_date": None
        }

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
        mute_role: discord.Role = guild.get_role(int(mute_role_id))
        if mute_role and mute_role in member.roles:
            muted = True

        voice_role_id: str = db['voice_mutes'].get(guild_id, {}).get('role', 0)
        voice_role: discord.Role = guild.get_role(int(voice_role_id))
        if voice_role and voice_role in member.roles:
            voice_muted = True

    timeout = member.is_timed_out() if member else False

    banned = False
    unban_date = None
    if user:
        try:
            await guild.fetch_ban(user)
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


def get_bot(ctx_or_interaction) -> commands.Bot:
    return getattr(ctx_or_interaction, "bot", None) or getattr(ctx_or_interaction, "client", None)


def get_author_id(obj) -> discord.abc.User:
    """
    Given a Context or Interaction, return the author/user.

    :param obj: commands.Context or discord.Interaction
    :return: discord.User or discord.Member
    """
    if hasattr(obj, "author"):
        return obj.author.id  # commands.Context
    if hasattr(obj, "user"):
        return obj.user.id    # discord.Interaction
    else:
        raise AttributeError("Object has no author or user attribute")


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
        if isinstance(entry['date'], int):
            value = f"<t:{entry['date']}:f>\n"
        else:
            converted_date = hf.convert_to_datetime(entry['date'])
            if converted_date:
                value = f"<t:{int(converted_date.timestamp())}:f>\n"
            else:
                value = f"Date: {entry['date']}\n"
        if entry['length']:
            value += f"*For {entry['length']}*\n"
        if entry['reason']:
            value += f"__Reason__: {entry['reason']}\n"
        if entry['jump_url']:
            value += f"[Jump URL]({entry['jump_url']})\n"

        fields.append((name, value[:1024]))

    return fields


async def build_modlog_embed(bot, ctx_or_interaction: Union[commands.Context, discord.Interaction], user: discord.User, page: Optional[int] = None) -> Tuple[discord.Embed, int]:
    guild = getattr(ctx_or_interaction, 'guild', None)
    if not guild or not user:
        return utils.red_embed("User or guild not found"), 0
        
    user_id = str(user.id)
    guild_id = str(guild.id)
    config = bot.db['modlog'].get(guild_id, {})

    emb = utils.green_embed("")
    if not emb.description:
        emb.description = ""
        
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
    if page is None:
        page = total_pages - 1
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

    return emb, total_pages-1


async def build_user_summary_embed(bot, ctx_or_interaction: Union[commands.Context, discord.Interaction], member: Optional[discord.Member], user: Optional[discord.User]) -> discord.Embed:
    guild = getattr(ctx_or_interaction, 'guild', None)
    if not guild or not user:
        return utils.red_embed("User or guild not found")
        
    guild_id = str(guild.id)
    user_id = str(user.id)

    # ==== Basic Embed Setup ====
    emb = utils.green_embed("")
    if not emb.description:
        emb.description = ""
        
    name = f"Username: {str(user)}\nDisplay name: {getattr(user, 'nick', '')}\n{user_id}" if getattr(
        user, "nick", None) else f"{str(user)}\n{user_id}"
    emb.set_author(name=name,
                   #    icon_url=user.display_avatar.replace(static_format="png").url
                   )
    emb.set_thumbnail(url=user.display_avatar.url)

    # ==== User Status ====
    status = await get_user_status(ctx_or_interaction, guild_id, member, user)

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
        if member and member.timed_out_until:
            emb.description += f"**`Current Status`** Timed out (expires <t:{int(member.timed_out_until.timestamp())}:R>)\n"
    elif not member:
        emb.color = utils.grey_embed("").color
        emb.description += "**`Current Status`** : User is not in server\n"
    else:
        emb.description += "**`Current Status`** : No active incidents\n"

    # ==== Stats ====
    if member:
        stats = get_user_stats(bot, guild_id, member)
        emb.description += f"\n**`# of messages M | W`** : {stats['month']} | {stats['week']}"
        emb.description += f"\n**`Time in voice`** : {stats['voice']}"
        if stats['sentiment']:
            emb.description += f"\n**`Recent sentiment ({stats['sentiment_count']} msgs)`** : {stats['sentiment']}"

    # ==== Log count====
    modlog_config = bot.db.get("modlog", {}).get(str(guild.id), {})
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
        # Only attempt to fix join history for commands.Context
        if isinstance(ctx_or_interaction, commands.Context):
            if member and member.joined_at and datetime(2021, 6, 25, tzinfo=timezone.utc) <= member.joined_at <= datetime(2022, 7, 24, tzinfo=timezone.utc):
                join_history = await cm.fix_join_history_invite(ctx_or_interaction, int(user_id), join_history)
            else:
                join_history = await cm.fix_join_history_invite(ctx_or_interaction, int(user_id), join_history)

        if invite := join_history.get('invite'):
            if invite not in ['Through server discovery', guild.vanity_url_code]:
                invite_creator_id = join_history.get('invite_creator')
                if not invite_creator_id:
                    invite_obj = discord.utils.find(lambda i: i.code == invite, await guild.invites())
                    if not invite_obj and invite == guild.vanity_url_code:
                        invite_obj = await guild.vanity_invite()
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
        try:
            excessive = await hf.excessive_dm_activity(guild.id, int(user_id))
            spammy = await hf.suspected_spam_activity_flag(guild.id, int(user_id))
            if excessive or spammy:
                emb.description += "\n⚠️ **__User Flags__** ⚠️\n"
            if excessive:
                emb.description += "**`Excessive DMs`** : User has been flagged for excessive DMs\n"
            if spammy:
                emb.description += "**`Suspected Spam`** : User has been flagged for suspected spam activity\n"
        except Exception:
            # If there's an error with flag checking, just skip it
            pass

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
        if isinstance(entry['date'], int):
            embed.add_field(name='Date', value=f"<t:{entry['date']}:f>\n")
        else:
            converted_date = hf.convert_to_datetime(entry['date'])
            if converted_date:
                embed.add_field(name='Date', value=f"<t:{int(converted_date.timestamp())}:f>\n")
            else:
                embed.add_field(name='Date', value=f"Date: {entry['date']}\n")
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
