import random
import io
from datetime import datetime, timezone
from typing import Any, Optional

import discord
import yaml
from discord import app_commands
from discord.ext import commands

import cogs.interactions
from cogs.utils.BotUtils import bot_utils as utils
from .utils import helper_functions as hf

RYAN_TEST_SERV_ID = 275146036178059265
SP_SERV_ID = 243838819743432704

class Quotes(commands.Cog):
    """Quote storage, lookup, import/export, and moderation tools.

    Prefix commands:
    `;quoteadd` / `;qa` - Add a quote with a name. Example: `;qa rai Hello there`
    `;quoteprint` / `;qp` - Print a random quote saved under a name. Example: `;qp rai`
    `;quoteid` / `;qid` / `;quotebyid` - Print a quote by numeric ID. Example: `;qid 42`
    `;qinfo` / `;qi` - Show full metadata for a quote, including author, usage, and source message when available.
    `;quotelist` / `;liqu` - List all quotes, or only quotes for one name. Example: `;quotelist rai`
    `;qsearch` / `;qs` - Search quote names and quote text. Example: `;qs hello`
    `;quotedelete` / `;qdel` / `;quotedel` - Delete one or more quote IDs. Authors can delete their own quotes; submods can delete any quote.
    `;dedupequotes` / `;qdedupe` / `;quotesdedupe` / `;quotededupe` - Admin-only duplicate cleanup for identical name/body pairs.
    `;quotesimport` / `;qimport` / `;quotesyamlimport` - Admin-only import of Nadeko quote YAML from an attached or replied-to file.
    `;quotesexport` / `;qexport` - Admin-only export of this server's quotes as YAML.

    Shorthand listeners:
    `.. name quote text` - Quick-add a quote from a normal message.
    `... name` - Print a random quote for that name from a normal message.

    Slash commands:
    `/quotestats` - Admin-only usage totals and used vs. unused percentages.
    `/quoteunused` - Admin-only list of quotes that have never been used.
    `/myquotes` - Show the quotes you created in the current server.
    `/setquotelog` - Admin-only set or clear the log channel for quote create/delete events.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.db.setdefault("quotes", {})

    @staticmethod
    def _normalize_name(name: str) -> str:
        return " ".join(name.strip().split()).lower()

    def _guild_config(self, guild_id: int) -> dict[str, Any]:
        config = self.bot.db["quotes"].setdefault(str(guild_id), {"next_id": 1, "entries": []})
        config.setdefault("log_channel", None)
        return config

    def _all_entries(self, guild_id: int) -> list[dict[str, Any]]:
        entries = self._guild_config(guild_id)["entries"]
        for entry in entries:
            self._ensure_usage_fields(entry)
        return entries

    @staticmethod
    def _ensure_usage_fields(entry: dict[str, Any]) -> dict[str, Any]:
        entry.setdefault("times_used", 0)
        entry.setdefault("last_used_at", None)
        entry.setdefault("source_channel_id", None)
        entry.setdefault("source_message_id", None)
        return entry

    def _find_by_id(self, guild_id: int, quote_id: int) -> Optional[dict[str, Any]]:
        for entry in self._all_entries(guild_id):
            if entry["id"] == quote_id:
                return entry
        return None

    def _find_by_name(self, guild_id: int, name: str) -> list[dict[str, Any]]:
        normalized = self._normalize_name(name)
        return [entry for entry in self._all_entries(guild_id) if entry["name_key"] == normalized]

    def _find_exact_duplicate(self, guild_id: int, name: str, body: str) -> Optional[dict[str, Any]]:
        normalized_name = self._normalize_name(name)
        normalized_body = body.strip()
        for entry in self._all_entries(guild_id):
            if entry["name_key"] == normalized_name and entry["body"] == normalized_body:
                return entry
        return None

    def _add_quote(
        self,
        guild: discord.Guild,
        author: discord.abc.User,
        name: str,
        body: str,
        source_channel_id: Optional[int] = None,
        source_message_id: Optional[int] = None,
    ) -> Optional[dict[str, Any]]:
        if self._find_exact_duplicate(guild.id, name, body):
            return None
        config = self._guild_config(guild.id)
        quote_id = config["next_id"]
        entry = {
            "id": quote_id,
            "name": " ".join(name.strip().split()),
            "name_key": self._normalize_name(name),
            "body": body.strip(),
            "author_id": author.id,
            "author_name": str(author),
            "times_used": 0,
            "last_used_at": None,
            "source_channel_id": source_channel_id,
            "source_message_id": source_message_id,
        }
        config["entries"].append(entry)
        config["next_id"] += 1
        return entry

    def _import_quote(
        self,
        guild: discord.Guild,
        name: str,
        body: str,
        author_id: int = 0,
        author_name: str = "Nadeko Import",
        source_channel_id: Optional[int] = None,
        source_message_id: Optional[int] = None,
    ) -> Optional[dict[str, Any]]:
        if self._find_exact_duplicate(guild.id, name, body):
            return None
        config = self._guild_config(guild.id)
        quote_id = config["next_id"]
        entry = {
            "id": quote_id,
            "name": " ".join(name.strip().split()),
            "name_key": self._normalize_name(name),
            "body": body.strip(),
            "author_id": author_id,
            "author_name": author_name,
            "times_used": 0,
            "last_used_at": None,
            "source_channel_id": source_channel_id,
            "source_message_id": source_message_id,
        }
        config["entries"].append(entry)
        config["next_id"] += 1
        return entry

    def _mark_quote_used(self, entry: dict[str, Any]):
        entry = self._ensure_usage_fields(entry)
        entry["times_used"] += 1
        entry["last_used_at"] = datetime.now(timezone.utc).timestamp()

    @staticmethod
    def _quote_jump_url(guild_id: int, entry: dict[str, Any]) -> Optional[str]:
        channel_id = entry.get("source_channel_id")
        message_id = entry.get("source_message_id")
        if not channel_id or not message_id:
            return None
        return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"

    @staticmethod
    def _quote_created_at(entry: dict[str, Any]) -> Optional[datetime]:
        message_id = entry.get("source_message_id")
        if not message_id:
            return None
        try:
            return discord.utils.snowflake_time(int(message_id))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_attachment_source(ctx: commands.Context) -> Optional[discord.Message]:
        if ctx.message.attachments:
            return ctx.message

        reference = ctx.message.reference
        if not reference:
            return None

        resolved = reference.resolved
        if isinstance(resolved, discord.Message) and resolved.attachments:
            return resolved

        return None

    @staticmethod
    async def _send_quote(destination: discord.abc.Messageable, entry: dict[str, Any]):
        await destination.send(
            f"`#{entry['id']}` {entry['body']}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    def _build_quote_log_embed(
        self,
        entry: dict[str, Any],
        action: str,
        actor: str,
        *,
        color: int,
        extra_text: str = "",
    ) -> discord.Embed:
        embed = discord.Embed(
            description=f"**Quote {action}**",
            colour=color,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Quote", value=f"`#{entry['id']}` `{entry['name']}`", inline=False)
        embed.add_field(name="By", value=actor, inline=False)
        if extra_text:
            embed.add_field(name="Context", value=extra_text, inline=False)

        body = entry["body"]
        body_segments = utils.split_text_into_segments(body, 1024)
        for index, segment in enumerate(body_segments[:2]):
            field_name = "Message" if index == 0 else f"Message (Part {index + 1})"
            embed.add_field(name=field_name, value=segment, inline=False)

        return embed

    async def _log_quote_event(self, guild: discord.Guild, embed: discord.Embed):
        log_channel_id = self._guild_config(guild.id).get("log_channel")
        if not log_channel_id:
            return

        channel = guild.get_channel(log_channel_id) or self.bot.get_channel(log_channel_id)
        if not channel:
            self._guild_config(guild.id)["log_channel"] = None
            return

        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _handle_quote_add(self, message: discord.Message, payload: str):
        payload = payload.strip()
        if not payload:
            return

        parts = payload.split(maxsplit=1)
        if len(parts) < 2:
            await message.channel.send(
                "Usage: `.. quote_name quote_text`",
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        name, body = parts
        entry = self._add_quote(
            message.guild,
            message.author,
            name,
            body,
            source_channel_id=message.channel.id,
            source_message_id=message.id,
        )  # pyright: ignore[reportArgumentType]
        if not entry:
            await message.channel.send(
                "That quote already exists.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        await self._log_quote_event(message.guild, self._build_quote_log_embed(
            entry,
            "created",
            message.author.mention,
            color=0x7BA600,
        ))
        await message.channel.send(
            f"Saved quote ID `{entry['id']}` under `{entry['name']}`. "
            f"Type `... {entry['name']}` to call this quote, "
            f"or `;qdel {entry['id']}` to delete it.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _handle_quote_print(self, message: discord.Message, payload: str):
        name = payload.strip()
        if not name:
            await message.channel.send(
                "Usage: `... quote_name`",
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        matches = self._find_by_name(message.guild.id, name)  # pyright: ignore[reportOptionalMemberAccess]
        if not matches:
            return

        selected = random.choice(matches)
        self._mark_quote_used(selected)
        await self._send_quote(message.channel, selected)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.webhook_id or not message.guild:
            return

        content = message.content.strip()
        if not content:
            return

        if content.startswith(("...", "…")):
            await self._handle_quote_print(message, content[3:])
        elif content.startswith(".."):
            await self._handle_quote_add(message, content[2:])

    @commands.guild_only()
    @commands.command(aliases=["qa"])
    async def quoteadd(self, ctx: commands.Context, name: str, *, body: str):
        """Add a quote with a name."""
        entry = self._add_quote(
            ctx.guild,
            ctx.author,
            name,
            body,
            source_channel_id=ctx.channel.id,
            source_message_id=ctx.message.id,
        )  # pyright: ignore[reportArgumentType]
        if not entry:
            await utils.safe_send(ctx, "That quote already exists.")
            return
        await self._log_quote_event(ctx.guild, self._build_quote_log_embed(
            entry,
            "created",
            ctx.author.mention,
            color=0x7BA600,
        ))
        await utils.safe_send(ctx, f"Saved quote #{entry['id']} under `{entry['name']}`.")

    @commands.guild_only()
    @commands.command(aliases=["qp"])
    async def quoteprint(self, ctx: commands.Context, *, name: str):
        """Print a random quote with the specified name."""
        matches = self._find_by_name(ctx.guild.id, name)  # pyright: ignore[reportOptionalMemberAccess]
        if not matches:
            await utils.safe_send(ctx, f"No quotes found for `{name.strip()}`.")
            return

        selected = random.choice(matches)
        self._mark_quote_used(selected)
        await self._send_quote(ctx, selected)

    @commands.guild_only()
    @commands.command(aliases=["qid", "quotebyid"])
    async def quoteid(self, ctx: commands.Context, quote_id: int):
        """Print a quote by numeric ID."""
        entry = self._find_by_id(ctx.guild.id, quote_id)  # pyright: ignore[reportOptionalMemberAccess]
        if not entry:
            await utils.safe_send(ctx, f"Quote #{quote_id} was not found.")
            return

        self._mark_quote_used(entry)
        await self._send_quote(ctx, entry)

    @commands.guild_only()
    @commands.command(aliases=["qi"])
    async def qinfo(self, ctx: commands.Context, quote_id: int):
        """Show full metadata for a quote."""
        entry = self._find_by_id(ctx.guild.id, quote_id)  # pyright: ignore[reportOptionalMemberAccess]
        if not entry:
            await utils.safe_send(ctx, f"Quote #{quote_id} was not found.")
            return

        created_at = self._quote_created_at(entry)
        jump_url = self._quote_jump_url(ctx.guild.id, entry)  # pyright: ignore[reportOptionalMemberAccess]
        last_used_at = entry.get("last_used_at")

        embed = discord.Embed(
            title=f"Quote #{entry['id']}",
            description=entry["body"] or "(empty)",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Name", value=entry["name"], inline=False)
        embed.add_field(
            name="Author",
            value=f"{entry.get('author_name', 'Unknown')} ({entry.get('author_id', 0)})",
            inline=False,
        )
        embed.add_field(name="Times Used", value=str(entry.get("times_used", 0)), inline=True)
        embed.add_field(
            name="Last Used",
            value=f"<t:{int(last_used_at)}:F>\n<t:{int(last_used_at)}:R>" if last_used_at else "Never",
            inline=True,
        )
        embed.add_field(
            name="Created",
            value=f"<t:{int(created_at.timestamp())}:F>\n<t:{int(created_at.timestamp())}:R>" if created_at else "Unknown",
            inline=True,
        )
        if jump_url:
            embed.add_field(name="Source Message", value=f"[Jump to message]({jump_url})", inline=False)

        await utils.safe_send(ctx, embed=embed)

    @commands.guild_only()
    @commands.command(aliases=["liqu"])
    async def quotelist(self, ctx: commands.Context, *, name: str = ""):
        """List all quotes, or only quotes with a specific name."""
        if name:
            entries = self._find_by_name(ctx.guild.id, name)  # pyright: ignore[reportOptionalMemberAccess]
            title = f"Quotes for {name.strip()}"
        else:
            entries = self._all_entries(ctx.guild.id)  # pyright: ignore[reportOptionalMemberAccess]
            title = "All quotes"

        if not entries:
            await utils.safe_send(ctx, "No matching quotes found.")
            return

        lines = []
        for entry in sorted(entries, key=lambda item: item["id"]):
            preview = entry["body"].replace("\n", " ")
            if len(preview) > 80:
                preview = preview[:77] + "..."
            lines.append(f"`#{entry['id']}` `{entry['name']}` {preview}")

        message = f"**{title}**\n" + "\n".join(lines)
        for chunk in utils.split_text_into_segments(message, 1900):
            await utils.safe_send(ctx, chunk)

    @commands.guild_only()
    @commands.command(aliases=["qs"])
    async def qsearch(self, ctx: commands.Context, *, text: str):
        """Search quote names and bodies for text."""
        search = text.strip().lower()
        if not search:
            await utils.safe_send(ctx, "Usage: `;qsearch <text>`")
            return

        entries = [
            entry for entry in self._all_entries(ctx.guild.id)  # pyright: ignore[reportOptionalMemberAccess]
            if search in entry["name"].lower() or search in entry["body"].lower()
        ]
        if not entries:
            await utils.safe_send(ctx, "No matching quotes found.")
            return

        lines = []
        for entry in sorted(entries, key=lambda item: item["id"]):
            preview = entry["body"].replace("\n", " ")
            if len(preview) > 80:
                preview = preview[:77] + "..."
            lines.append(f"`#{entry['id']}` `{entry['name']}` {preview}")

        message = f"**Search Results**\n" + "\n".join(lines)
        for chunk in utils.split_text_into_segments(message, 1900):
            await utils.safe_send(ctx, chunk)

    @commands.guild_only()
    @commands.command(aliases=["qdel", "quotedel"])
    async def quotedelete(self, ctx: commands.Context, *quote_ids: int):
        """Delete one or more quotes by numeric ID."""
        if not quote_ids:
            await utils.safe_send(ctx, "Usage: `;qdel <quote_id> [quote_id] [...]`")
            return

        guild_entries = self._all_entries(ctx.guild.id)  # pyright: ignore[reportOptionalMemberAccess]
        deleted_ids: list[int] = []
        missing_ids: list[int] = []
        denied_ids: list[int] = []

        for quote_id in quote_ids:
            entry = next((item for item in guild_entries if item["id"] == quote_id), None)
            if not entry:
                missing_ids.append(quote_id)
                continue

            can_delete = (
                ctx.author.id == entry["author_id"]
                or hf.submod_check(ctx)
            )
            if not can_delete:
                denied_ids.append(quote_id)
                continue

            await self._log_quote_event(ctx.guild, self._build_quote_log_embed(
                entry,
                "deleted",
                ctx.author.mention,
                color=0xDB3C3C,
            ))
            guild_entries.remove(entry)
            deleted_ids.append(quote_id)

        result_lines = []
        if deleted_ids:
            result_lines.append(f"Deleted: {', '.join(f'`#{quote_id}`' for quote_id in deleted_ids)}")
        if missing_ids:
            result_lines.append(f"Not found: {', '.join(f'`#{quote_id}`' for quote_id in missing_ids)}")
        if denied_ids:
            result_lines.append(f"No permission: {', '.join(f'`#{quote_id}`' for quote_id in denied_ids)}")

        await utils.safe_send(ctx, "\n".join(result_lines))

    @commands.guild_only()
    @hf.is_admin()
    @commands.command(aliases=["qdedupe", "quotesdedupe", "quotededupe"])
    async def dedupequotes(self, ctx: commands.Context):
        """Delete duplicate quotes with identical name and content."""
        entries = self._all_entries(ctx.guild.id)  # pyright: ignore[reportOptionalMemberAccess]
        seen: dict[tuple[str, str], dict[str, Any]] = {}
        duplicate_ids: list[int] = []

        for entry in sorted(entries, key=lambda item: item["id"]):
            key = (entry["name_key"], entry["body"])
            if key in seen:
                duplicate_ids.append(entry["id"])
            else:
                seen[key] = entry

        if not duplicate_ids:
            await utils.safe_send(ctx, "No duplicate quotes found.")
            return

        duplicate_id_set = set(duplicate_ids)
        duplicate_entries = [entry for entry in entries if entry["id"] in duplicate_id_set]
        self._guild_config(ctx.guild.id)["entries"] = [
            entry for entry in entries if entry["id"] not in duplicate_id_set
        ]
        for entry in duplicate_entries:
            await self._log_quote_event(ctx.guild, self._build_quote_log_embed(
                entry,
                "deleted",
                ctx.author.mention,
                color=0xDB3C3C,
                extra_text="Duplicate cleanup",
            ))
        s = f"Deleted {len(duplicate_ids)} duplicate quotes: " \
            f"{', '.join(f'`#{quote_id}`' for quote_id in duplicate_ids)}"
        
        if len(s) > 1997:
            s = s[:1997] + "..."
        await utils.safe_send(ctx, s)

    @commands.guild_only()
    @hf.is_admin()
    @commands.command(aliases=["qimport", "quotesyamlimport"])
    async def quotesimport(self, ctx: commands.Context):
        """Import Nadeko quotes from a YAML attachment."""
        source_message = self._extract_attachment_source(ctx)
        if not source_message:
            await utils.safe_send(
                ctx,
                "Attach a Nadeko `.yaml` file to this command, or reply to a message that has one attached.",
            )
            return

        attachment = next(
            (item for item in source_message.attachments if item.filename.lower().endswith((".yaml", ".yml"))),
            None,
        )
        if not attachment:
            await utils.safe_send(ctx, "I couldn't find a `.yaml` or `.yml` attachment to import.")
            return

        try:
            raw_bytes = await attachment.read()
        except discord.HTTPException:
            await utils.safe_send(ctx, "I couldn't download that attachment.")
            return

        try:
            parsed = yaml.safe_load(raw_bytes.decode("utf-8"))
        except UnicodeDecodeError:
            await utils.safe_send(ctx, "That file is not valid UTF-8 YAML.")
            return
        except yaml.YAMLError as exc:
            await utils.safe_send(ctx, f"YAML parse error: `{exc}`")
            return

        if not isinstance(parsed, dict):
            await utils.safe_send(ctx, "The YAML root must be a mapping of quote names to quote lists.")
            return
        
        try:
            await ctx.message.add_reaction("⏱️")
        except (discord.Forbidden, discord.HTTPException):
            pass

        imported = 0
        duplicate_count = 0
        skipped = 0
        for keyword, quote_list in parsed.items():
            try:
                keyword = str(keyword)
            except (TypeError, ValueError):
                skipped += 1
                continue
            else:
                if not isinstance(keyword, str) or not keyword.strip():
                    skipped += 1
                    continue

            if not isinstance(quote_list, list):
                skipped += 1
                continue

            for item in quote_list:
                if not isinstance(item, dict):
                    skipped += 1
                    continue

                try:
                    body = str(item.get("txt"))
                except (TypeError, ValueError):
                    skipped += 1
                    continue

                author_name = item.get("an")
                author_id = item.get("aid", 0)
                if not isinstance(author_name, str) or not author_name.strip():
                    author_name = "Nadeko Import"
                try:
                    author_id = int(author_id)
                except (TypeError, ValueError):
                    author_id = 0

                entry = self._import_quote(
                    ctx.guild,
                    keyword,
                    body,
                    author_id=author_id,
                    author_name=author_name,
                    source_channel_id=ctx.channel.id,
                    source_message_id=ctx.message.id,
                )
                if entry:
                    imported += 1
                    await self._log_quote_event(ctx.guild, self._build_quote_log_embed(
                        entry,
                        "created",
                        f"`{entry['author_name']}`",
                        color=0x7BA600,
                        extra_text=f"Imported by {ctx.author.mention}",
                    ))
                else:
                    duplicate_count += 1

        if not imported:
            if duplicate_count:
                await utils.safe_send(ctx, f"No new quotes were imported. Skipped {duplicate_count} duplicates.")
            else:
                await utils.safe_send(ctx, "No valid quotes were found in that YAML file.")
            return

        await utils.safe_send(
            ctx,
            f"Imported {imported} quotes from `{attachment.filename}`." +
            (f" Skipped {duplicate_count} duplicates." if duplicate_count else "") +
            (f" Skipped {skipped} invalid entries." if skipped else ""),
        )

    @app_commands.command(name="quotestats", description="Show quote usage totals and used/unused percentages.")
    @app_commands.guilds(RYAN_TEST_SERV_ID, SP_SERV_ID)
    @app_commands.default_permissions()
    async def quotestats(self, interaction: discord.Interaction):
        if not hf.admin_check(interaction):
            await interaction.response.send_message("You cannot use this command.", ephemeral=True)
            return

        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        entries = self._all_entries(interaction.guild.id)
        total_quotes = len(entries)
        used_quotes = sum(1 for entry in entries if entry.get("times_used", 0) > 0)
        unused_quotes = total_quotes - used_quotes

        if total_quotes:
            used_percent = (used_quotes / total_quotes) * 100
            unused_percent = (unused_quotes / total_quotes) * 100
        else:
            used_percent = 0.0
            unused_percent = 0.0

        embed = discord.Embed(
            title="Quote Usage Stats",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Total Quotes", value=str(total_quotes), inline=False)
        embed.add_field(
            name="Used At Least Once",
            value=f"{used_quotes} ({used_percent:.1f}%)",
            inline=True,
        )
        embed.add_field(
            name="Never Used",
            value=f"{unused_quotes} ({unused_percent:.1f}%)",
            inline=True,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="quoteunused", description="Show unused quotes in this server.")
    @app_commands.guilds(RYAN_TEST_SERV_ID, SP_SERV_ID)
    @app_commands.default_permissions()
    async def quoteunused(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        if not hf.admin_check(interaction):
            await interaction.response.send_message("You cannot use this command.", ephemeral=True)
            return

        entries = [
            entry for entry in sorted(self._all_entries(interaction.guild.id), key=lambda item: item["id"])
            if entry.get("times_used", 0) == 0
        ]
        if not entries:
            await interaction.response.send_message("There are no unused quotes.", ephemeral=True)
            return

        message = "**Unused Quotes**\n"
        for entry in entries:
            preview = entry["body"].replace("\n", " ")
            line = f"`#{entry['id']}` `{entry['name']}` {preview}\n"
            if len(message) + len(line) > 2000:
                break
            message += line

        await interaction.response.send_message(message, ephemeral=False)

    @app_commands.command(name="myquotes", description="Show the quotes you've created in this server.")
    @app_commands.guilds(RYAN_TEST_SERV_ID, SP_SERV_ID)
    async def myquotes(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        entries = [
            entry for entry in self._all_entries(interaction.guild.id)
            if entry.get("author_id") == interaction.user.id
        ]

        if not entries:
            await interaction.response.send_message("You haven't made any quotes in this server.", ephemeral=True)
            return

        lines = []
        for entry in sorted(entries, key=lambda item: item["id"]):
            preview = entry["body"].replace("\n", " ")
            if len(preview) > 80:
                preview = preview[:77] + "..."
            lines.append(f"`#{entry['id']}` `{entry['name']}` {preview}")

        message = f"**Your Quotes**\n" + "\n".join(lines)
        for index, chunk in enumerate(utils.split_text_into_segments(message, 1900)):
            if index == 0:
                await interaction.response.send_message(chunk, ephemeral=True)
            else:
                await interaction.followup.send(chunk, ephemeral=True)

    @app_commands.command(name="setquotelog", description="Set or clear the channel for quote create/delete logs.")
    @app_commands.default_permissions()
    @app_commands.guilds(RYAN_TEST_SERV_ID, SP_SERV_ID)
    @app_commands.describe(channel="Leave blank to disable quote logging for this server")
    async def setquotelog(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        if not hf.admin_check(interaction):
            await interaction.response.send_message("You cannot use this command.", ephemeral=True)
            return

        config = self._guild_config(interaction.guild.id)
        if channel is None:
            config["log_channel"] = None
            await interaction.response.send_message("Quote logging disabled for this server.", ephemeral=True)
            return

        config["log_channel"] = channel.id
        await interaction.response.send_message(
            f"Quote logging channel set to {channel.mention}.",
            ephemeral=True,
        )

    @commands.guild_only()
    @hf.is_admin()
    @commands.command(aliases=["qexport"])
    async def quotesexport(self, ctx: commands.Context):
        """Export this server's quotes as YAML."""
        entries = sorted(self._all_entries(ctx.guild.id), key=lambda item: (item["name_key"], item["id"]))  # pyright: ignore[reportOptionalMemberAccess]
        if not entries:
            await utils.safe_send(ctx, "There are no quotes to export.")
            return

        export_data: dict[str, list[dict[str, Any]]] = {}
        for entry in entries:
            export_data.setdefault(entry["name"], []).append({
                "id": str(entry["id"]),
                "an": entry.get("author_name", "Unknown"),
                "aid": entry.get("author_id", 0),
                "txt": entry["body"],
            })

        yaml_text = yaml.safe_dump(export_data, allow_unicode=True, sort_keys=True)
        file = discord.File(io.BytesIO(yaml_text.encode("utf-8")), filename=f"quotes_{ctx.guild.id}.yaml")
        await utils.safe_send(ctx, "Exported quotes YAML:", file=file)


async def setup(bot: commands.Bot):
    await bot.add_cog(Quotes(bot))
    await bot.wait_until_ready()
    interactions_cog: cogs.interactions.Interactions = bot.get_cog("Interactions")
    if interactions_cog and hasattr(interactions_cog, "sync_main"):
        await interactions_cog.sync_main()
