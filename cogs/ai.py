import asyncio
import json
import logging
import os
import re
import traceback
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Union

import aiohttp
import discord
import openai
from discord.ext import commands, tasks
from lingua import Language
from openai import AsyncOpenAI

from cogs.utils.BotUtils import bot_utils as utils
from .utils import helper_functions as hf

SP_SERVER_ID = 243838819743432704
JP_SERVER_ID = 189571157446492161
SUMMARY_SOURCE_CHANNEL_ID = 296013414755598346
SUMMARY_DESTINATION_CHANNEL_ID = 1490594218798743572
SUMMARY_LOG_CHANNEL_ID = 1351956893119283270
SUMMARY_HEADER = "**4-Hour Summary**"
SUMMARY_WINDOW_HOURS = 4
SUMMARY_MAX_MESSAGES = 1200
SUMMARY_MAX_TRANSCRIPT_CHARS = 100_000


def _format_ts(ts: int | float | None) -> str:
    if ts is None:
        return "unknown"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _get_openai_admin_key() -> tuple[str | None, str]:
    admin_key = os.getenv("OPENAI_ADMIN_KEY")
    if admin_key:
        return admin_key, "OPENAI_ADMIN_KEY"
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return api_key, "OPENAI_API_KEY"
    return None, "none"


async def fetch_openai_admin_json(path: str, *, params: dict[str, Any] | None = None) -> tuple[int, str, Any]:
    api_key, key_source = _get_openai_admin_key()
    if not api_key:
        return 0, "Missing OPENAI_ADMIN_KEY / OPENAI_API_KEY.", {"key_source": key_source}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.openai.com/v1{path}", headers=headers, params=params) as resp:
            text = await resp.text()
            try:
                payload = await resp.json()
            except aiohttp.ContentTypeError:
                payload = {"raw_text": text}
            return resp.status, key_source, payload


def summarize_cost_buckets(data: dict[str, Any]) -> str:
    buckets = data.get("data", [])
    if not buckets:
        return "No cost data returned."

    total_cost = 0.0
    bucket_count = 0
    for bucket in buckets:
        bucket_count += 1
        for result in bucket.get("results", []):
            amount = result.get("amount", {})
            total_cost += float(amount.get("value") or 0.0)

    start_time = buckets[0].get("start_time")
    end_time = buckets[-1].get("end_time")
    return (
        f"${total_cost:.4f} total across {bucket_count} bucket(s) "
        f"from {_format_ts(start_time)} to {_format_ts(end_time)}"
    )


def summarize_usage_buckets(data: dict[str, Any], *, label: str, metric_keys: list[str]) -> str:
    buckets = data.get("data", [])
    if not buckets:
        return f"{label}: no data returned."

    total_requests = 0
    totals: dict[str, float] = defaultdict(float)
    for bucket in buckets:
        for result in bucket.get("results", []):
            total_requests += int(result.get("num_model_requests") or 0)
            for key in metric_keys:
                totals[key] += float(result.get(key) or 0.0)

    parts = [f"{label}: {total_requests} request(s)"]
    for key in metric_keys:
        if totals[key]:
            parts.append(f"{key}={totals[key]:.0f}")

    start_time = buckets[0].get("start_time")
    end_time = buckets[-1].get("end_time")
    parts.append(f"window={_format_ts(start_time)} to {_format_ts(end_time)}")
    return ", ".join(parts)


async def openai_request(coro_func, *, retries: int = 3, base_delay: float = 2.0) -> Any:
    last_error = None
    for attempt in range(retries):
        try:
            return await coro_func()
        except openai.RateLimitError as e:
            last_error = e
            if attempt == retries - 1:
                raise
            await asyncio.sleep(base_delay * (attempt + 1))
    if last_error:
        raise last_error
    raise RuntimeError("openai_request failed without an exception")


def setup_openai_client(bot: Any) -> None:
    if hasattr(bot, "openai"):
        if bot.openai:
            return

    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    open_ai_key = os.getenv("OPENAI_API_KEY")
    if open_ai_key:
        bot.openai = AsyncOpenAI(api_key=open_ai_key)
    else:
        bot.openai = None


async def chat_completion(
    bot: Any,
    *,
    messages: list[dict[str, Any]],
    model: str = "gpt-4o-mini",
) -> Any:
    if not getattr(bot, "openai", None):
        return None
    return await openai_request(
        lambda: bot.openai.chat.completions.create(model=model, messages=messages)
    )


async def chat_completion_text(
    bot: Any,
    *,
    messages: list[dict[str, Any]],
    model: str = "gpt-4o-mini",
    log_channel_id: int | None = None,
) -> tuple[Any, str]:
    completion = await chat_completion(bot, model=model, messages=messages)
    if log_channel_id:
        await hf.segment_send(log_channel_id, messages)
        await hf.segment_send(log_channel_id, completion)
    response_text = completion.choices[0].message.content
    return completion, response_text


async def moderation_with_image_fallback(
    bot: Any,
    *,
    model: str,
    messages: list[dict[str, Any]],
    log_channel_id: int | None = None,
) -> Any:
    if not getattr(bot, "openai", None):
        return None

    try:
        return await openai_request(
            lambda: bot.openai.moderations.create(model=model, input=messages)
        )
    except openai.RateLimitError as e:
        if log_channel_id:
            await hf.segment_send(log_channel_id, f"OpenAI moderation rate-limited: `{e}`")
        return None
    except openai.BadRequestError as e:
        if log_channel_id:
            await hf.segment_send(log_channel_id, messages)
        moderation_result = None
        ignore_strings = ["invalid_image_format", "image_url_unavailable", "file_too_large", "Failed to download"]
        if any(ignore_string in str(e) for ignore_string in ignore_strings):
            filtered_messages = [m for m in messages if m.get("type") != "image_url"]
            if len(filtered_messages) != len(messages):
                try:
                    moderation_result = await openai_request(
                        lambda: bot.openai.moderations.create(model=model, input=filtered_messages)
                    )
                except openai.RateLimitError as inner_e:
                    if log_channel_id:
                        await hf.segment_send(log_channel_id, f"OpenAI moderation rate-limited: `{inner_e}`")
                    return None
        if not moderation_result:
            raise
        return moderation_result


def floor_to_summary_window(dt: datetime) -> datetime:
    """
Floors the given datetime to the nearest previous summary window boundary (e.g., 00:00, 04:00, 08:00, etc. UTC).
    """
    dt = dt.astimezone(timezone.utc)
    floored_hour = dt.hour - (dt.hour % SUMMARY_WINDOW_HOURS)
    return dt.replace(hour=floored_hour, minute=0, second=0, microsecond=0)


def fake_jump_url_for_time(channel: discord.TextChannel, dt: datetime) -> str:
    message_id = discord.utils.time_snowflake(dt.astimezone(timezone.utc))
    return f"https://discord.com/channels/{channel.guild.id}/{channel.id}/{message_id}"


def parse_json_block(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


class AI(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.channel_summary_loop.start()

    def cog_unload(self):
        self.channel_summary_loop.cancel()

    def ai_features_enabled(self) -> bool:
        config = self.bot.db.setdefault("ai_features", {})
        return config.get("enabled", True)

    async def get_previous_channel_summary(self, channel: discord.TextChannel) -> str:
        async for message in channel.history(limit=20):
            if message.author != self.bot.user:
                continue
            if not message.content.startswith(SUMMARY_HEADER):
                continue
            return message.content
        return "No previous summary available."

    def serialize_summary_message(self, message: discord.Message) -> str | None:
        content_parts = []
        if message.content:
            content_parts.append(re.sub(r"\s+", " ", message.content).strip())
        if message.attachments:
            content_parts.append(f"attachments={', '.join(a.filename for a in message.attachments[:3])}")
        if message.embeds:
            content_parts.append(f"embeds={len(message.embeds)}")
        content = " | ".join(part for part in content_parts if part).strip()
        if not content:
            return None
        if len(content) > 350:
            content = content[:347] + "..."
        created_at = message.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
        author_name = message.author.display_name.replace("\n", " ")
        return f"[id={message.id}][author={author_name}] {content}"

    async def collect_summary_messages(
        self,
        channel: discord.TextChannel,
        start_time: datetime,
        end_time: datetime,
    ) -> tuple[list[discord.Message], str, bool]:
        messages: list[discord.Message] = []
        transcript_lines: list[str] = []
        transcript_chars = 0
        broke_early = False
        async for message in channel.history(limit=None, after=start_time, before=end_time, oldest_first=True):
            serialized = self.serialize_summary_message(message)
            if not serialized:
                continue
            projected_chars = transcript_chars + len(serialized) + 1
            if len(messages) >= SUMMARY_MAX_MESSAGES or projected_chars > SUMMARY_MAX_TRANSCRIPT_CHARS:
                broke_early = True
                break
            messages.append(message)
            transcript_lines.append(serialized)
            transcript_chars = projected_chars
        return messages, "\n".join(transcript_lines), broke_early

    async def build_channel_summary(self, start_time: datetime, end_time: datetime) -> str | None:
        source_channel = self.bot.get_channel(SUMMARY_SOURCE_CHANNEL_ID)
        destination_channel = self.bot.get_channel(SUMMARY_DESTINATION_CHANNEL_ID)
        if not isinstance(source_channel, discord.TextChannel):
            raise ValueError(f"Source channel {SUMMARY_SOURCE_CHANNEL_ID} not found.")
        if not isinstance(destination_channel, discord.TextChannel):
            raise ValueError(f"Destination channel {SUMMARY_DESTINATION_CHANNEL_ID} not found.")

        previous_summary = await self.get_previous_channel_summary(destination_channel)
        source_messages, transcript, broke_early = await self.collect_summary_messages(source_channel, start_time, end_time)
        if not source_messages or not transcript.strip():
            return None

        message_lookup = {message.id: message for message in source_messages}
        prompt = (
            "Previous summary from the summary log channel (don't re-summarize this):\n"
            f"{previous_summary}\n\n"
            f"New transcript covering {start_time.strftime('%Y-%m-%d %H:%M UTC')} to "
            f"{end_time.strftime('%Y-%m-%d %H:%M UTC')} (summarize this):\n"
            f"{transcript}"
        )
        messages = [
            {
                "role": "developer",
                "content": (
                    "You summarize a Discord channel every 4 hours. "
                    "Group the conversation into distinct topics of discussion. "
                    "If needed, use the previous summary for context to continue topics that are ongoing "
                    "instead of restarting them. Do not re-summarize things from the 'previous summary' section. "
                    "Ignore trivial chatter unless it materially affects a topic. "
                    "Return valid JSON only with this schema: "
                    "{\"topics\": [{\"title\": str, \"summary\": str, \"start_message_id\": int}]}. "
                    "Requirements: Choose start_message_id from the transcript exactly, "
                    "order topics by when they started, and keep the entire response compact enough "
                    "that each topic text stays under 2000 characters "
                    "(there is no need to use all 2000 characters if not necessary)."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        _, response_text = await chat_completion_text(
            self.bot,
            messages=messages,
            log_channel_id=SUMMARY_LOG_CHANNEL_ID,
        )
        payload = parse_json_block(response_text)
        topics = payload.get("topics", [])
        if not isinstance(topics, list) or not topics:
            return None

        lines = [
            SUMMARY_HEADER,
            (
                f"[{discord.utils.format_dt(start_time, 'f')}]"
                f"({fake_jump_url_for_time(source_channel, start_time)}) to "
                f"[{discord.utils.format_dt(end_time, 'f')}]"
                f"({fake_jump_url_for_time(source_channel, end_time)})"
            ),
            "",
        ]
        for index, topic in enumerate(topics, start=1):
            if not isinstance(topic, dict):
                continue
            title = str(topic.get("title", "")).strip() or f"Topic {index}"
            summary = str(topic.get("summary", "")).strip()
            try:
                start_message_id = int(topic.get("start_message_id"))
            except (TypeError, ValueError):
                start_message_id = 0

            start_message = message_lookup.get(start_message_id)
            jump_url = start_message.jump_url if start_message else None
            lines.append(f"**{index}. {title}**")
            if jump_url:
                lines.append(f"Started: {jump_url}")
            if summary:
                lines.append(summary)
            lines.append("")

        final_text = "\n".join(lines).strip()
        if final_text == SUMMARY_HEADER:
            return None
        return final_text

    async def maybe_run_channel_summary(self, *, force: bool = False) -> bool:
        if not self.ai_features_enabled():
            return False
        if not self.bot.openai:
            return False

        # Calculate the latest completed summary window end time
        # Example: if it's currently 10:17 UTC and SUMMARY_WINDOW_HOURS is 4, the latest completed window end is 08:00 UTC
        now = discord.utils.utcnow().replace(tzinfo=timezone.utc)
        latest_completed_end = floor_to_summary_window(now)
        if latest_completed_end == now:
            latest_completed_end -= timedelta(hours=SUMMARY_WINDOW_HOURS)

        config = self.bot.db['ai_features']
        last_completed_iso = config.get("last_completed_window_end", None)
        if last_completed_iso:
            next_window_end = datetime.fromisoformat(last_completed_iso)
            if next_window_end.tzinfo is None:
                next_window_end = next_window_end.replace(tzinfo=timezone.utc)
            next_window_end += timedelta(hours=SUMMARY_WINDOW_HOURS)
        else:
            next_window_end = latest_completed_end

        if not force and next_window_end > latest_completed_end:
            return False

        destination_channel = self.bot.get_channel(SUMMARY_DESTINATION_CHANNEL_ID)
        if not isinstance(destination_channel, discord.TextChannel):
            return False

        posted_summary = False
        while next_window_end <= latest_completed_end:
            window_start = next_window_end - timedelta(hours=SUMMARY_WINDOW_HOURS)
            summary_text = await self.build_channel_summary(window_start, next_window_end)
            if summary_text:
                for segment in utils.split_text_into_segments(summary_text, 2000):
                    await utils.safe_send(destination_channel, segment)
                posted_summary = True
            config["last_completed_window_end"] = next_window_end.isoformat()
            next_window_end += timedelta(hours=SUMMARY_WINDOW_HOURS)
            if force:
                break
        return posted_summary

    @tasks.loop(minutes=15)
    async def channel_summary_loop(self):
        try:
            await self.maybe_run_channel_summary()
        except Exception as e:
            traceback_channel_id = int(os.getenv("TRACEBACK_LOGGING_CHANNEL", "0"))
            if traceback_channel_id:
                await hf.segment_send(
                    traceback_channel_id,
                    f"Channel summary loop failed: `{e}`\n```py\n{traceback.format_exc()}\n```",
                )
            raise

    @channel_summary_loop.before_loop
    async def before_channel_summary_loop(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, msg_in: discord.Message):
        if not msg_in.guild:
            return
        if msg_in.author == self.bot.user:
            return
        if msg_in.author.bot:
            return
        
        msg = hf.RaiMessage(msg_in)
        if not self.ai_features_enabled():
            return
        try:
            await self.log_rai_tracebacks(msg)
        except Exception as e:
            print("Exception in log_rai_tracebacks:\n", e, traceback.format_exc())
        await self.mods_ping(msg)
        await self.sp_serv_other_language_detection(msg)
        await self.chatgpt_new_user_moderation(msg)

    async def log_rai_tracebacks(self, msg: hf.RaiMessage):
        new_tracebacks_channel = self.bot.get_channel(1360884895957651496)
        if not new_tracebacks_channel:
            raise Exception("Update the above channel ID")
        old_traceback_channel_id = int(os.getenv("TRACEBACK_LOGGING_CHANNEL", "0"))
        if msg.channel.id != old_traceback_channel_id:
            return
        if not msg.author == self.bot.user:
            return
        if "rai_tracebacks" not in self.bot.db:
            self.bot.db["rai_tracebacks"] = []
        if not self.bot.openai:
            return

        traceback_msg_split = msg.content.split("```py")
        if len(traceback_msg_split) < 2:
            return
        traceback_msg = traceback_msg_split[1][:-3]
        traceback_msg = re.sub(r"\d{17,22}", "ID", traceback_msg)
        traceback_msg = re.sub(r"line \d+", "line LINE", traceback_msg)
        traceback_msg = re.sub(r"File \".+?\"", "File \"FILE\"", traceback_msg)
        traceback_msg = re.sub(r"0x\w+", "0xHEX", traceback_msg)
        traceback_msg = re.sub(r"\d", "#", traceback_msg)

        if traceback_msg in self.bot.db["rai_tracebacks"]:
            return

        messages = [{"role": "system", "content": "Please summarize the following Python traceback to be parsed "
                     "with a bot. All errors will be things happening in a Discord bot, "
                     "so you don't need to state that in the post title:\n"
                     "1) A title for the post for the error "
                     "(100 characters max, plain text)\n"
                     "(New line)"
                     "2) A summary for why the error happened, and which file / line the "
                     "error happened on. Recommendations for fixing "
                     "the error are not needed (2000 characters max, "
                     "new lines and Discord formatting allowed)"},
                    {"role": "user", "content": "< assume traceback content here >"},
                    {"role": "assistant", "content": "HTTPException in on_raw_message_delete from malformed footer URL"
                                                     "\nThis bug comes from an HTTPException in ... "
                                                     "(response continues). It occurred in cogs/modlog.py, line 1234"},
                    {"role": "user", "content": msg.content}]

        _, response_text = await chat_completion_text(self.bot, messages=messages)
        post_name = response_text.split("\n")[0]
        if len(post_name) > 100:
            post_name = post_name[:100]
        post_content = "\n".join(response_text.split("\n")[1:])
        post_content_split = utils.split_text_into_segments(post_content, 1990)

        self.bot.db["rai_tracebacks"].append(traceback_msg)
        try:
            thread = await new_tracebacks_channel.create_thread(name=post_name, content=msg.content, embeds=msg.embeds)
            thread = thread.thread
        except discord.Forbidden as e:
            errmsg = f"Permission denied while creating thread in channel {new_tracebacks_channel.id}"
            e.add_note(errmsg)
            raise
        except discord.HTTPException as e:
            errmsg = f"HTTP error while creating thread: {e}"
            e.add_note(errmsg)
            raise
        for msg_split in post_content_split:
            await thread.send(msg_split)

    async def mods_ping(self, msg: hf.RaiMessage):
        if str(msg.guild.id) not in self.bot.db["staff_ping"]:
            return
        if "channel" not in self.bot.db["staff_ping"][str(msg.guild.id)]:
            return

        config = self.bot.db["staff_ping"][str(msg.guild.id)]
        staff_role_id = config.get("role")
        if not staff_role_id:
            staff_role_id = self.bot.db["mod_role"].get(str(msg.guild.id), {}).get("id")
            if isinstance(staff_role_id, list):
                staff_role_id = staff_role_id[0]
        if not staff_role_id:
            return

        staff_role = msg.guild.get_role(staff_role_id)
        if not staff_role:
            return

        if f"<@&{staff_role_id}>" in msg.content:
            edited_msg = re.sub(rf"<?@?&?{str(staff_role_id)}>? ?", "", msg.content)
        else:
            return

        user_id_regex = r"<?@?!?(\d{17,22})>? ?"
        users = re.findall(user_id_regex, edited_msg)
        users = " ".join(users)
        edited_msg = re.sub(user_id_regex, "", edited_msg)

        interactions = self.bot.get_cog("Interactions")
        if not interactions:
            return
        await msg.get_ctx()
        notif = await interactions.staffping_code(ctx=msg.ctx, users=users, reason=edited_msg)

        if hasattr(self.bot, "synced_reactions"):
            self.bot.synced_reactions.append((notif, msg))
        else:
            self.bot.synced_reactions = [(notif, msg)]

        if not self.bot.openai:
            return
        if msg.guild.id != SP_SERVER_ID:
            return
        if not msg.reference:
            return

        replied_message = msg.reference.cached_message
        if not replied_message and msg.reference.message_id:
            try:
                replied_message = await msg.channel.fetch_message(msg.reference.message_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return
        if not replied_message:
            return

        if not hasattr(self.bot, "chatgpt_summaries"):
            self.bot.chatgpt_summaries = [(msg.channel.id, msg.created_at.timestamp())]
        else:
            for channel_id, timestamp in self.bot.chatgpt_summaries:
                if msg.channel.id == channel_id:
                    if msg.created_at.timestamp() - timestamp > 60 * 10:
                        self.bot.chatgpt_summaries.remove((channel_id, timestamp))
                    else:
                        return
            self.bot.chatgpt_summaries.append((msg.channel.id, msg.created_at.timestamp()))

        instructions = (
            "Someone pinged staff about a potential incident in a Discord text channel by replying to another message. "
            "The replied-to message is the most important context and is most likely the reason staff was pinged. "
            "Focus primarily on that replied-to message, its author, and the surrounding context that explains why the "
            "staff ping happened. There's three possibilities:\n"
            "1) There's a singular issue in the channel. Identify that singular main issue, "
            "and do not explain anything else. Help staff understand what was happening in the channel that directly "
            "caused the staff ping.\n"
            "2) Someone mistakenly pinged staff. If there's no relevant issue in the channel, end your response.\n"
            "3) Multiple people pinged staff: you will see the first staff ping above you. Do not respond in this case."
            "You will receive up to 50 messages above the ping (most of the beginning messages are likely unrelated). "
            "Here are some instructions:\n"
            "- This summary will help mods quickly understand the situation, so keep it VERY concise.\n"
            "- Treat the replied-to message as the likely trigger for the staff ping unless the surrounding context clearly proves otherwise.\n"
            "- Pay special attention to the author of the replied-to message.\n"
            "- Identify the troll or bad actor relevant to the staff ping and describe briefly what they did wrong.\n"
            "- If a problematic discussion or argument caused someone to ping staff, "
            "summarize it, focusing on who's driving the conflict.\n"
            "- Ignore non-problematic or unrelated messages, like greetings or unrelated discussions.\n"
            "- Summarize only one main topic of conflict in your answer\n\n"
            "Examples of the three cases above: \n"
            "1a) [Unrelated messages], [Alice starts spamming messages], [@staff ping], Your response:"
            "'**Alice** is spamming messages and disrupting conversation'\n"
            "1b) [Unrelated messages], [Bob and Charlie start arguing], [@staff ping], Your response: "
            "**Bob** and **Charlie** are arguing about a rule interpretation. In particular, **Bob** "
            "was being particularly aggressive in the discussion, while **Charlie** was trying to deescalate.\n"
            "2) [Unrelated messages], [Nothing particular problematic], [suddenly, @staff ping], Your response: "
            "I could not find any issues in the channel. The ping may have been erroneous.\n"
            "3) [Unrelated messages], [some problem], [@staff ping], [shortly after, a second @staff ping], "
            "Your response: Ignoring second staff ping."
        )

        messages = [{"role": "system", "content": instructions}]
        replied_content = {
            "content": (replied_message.content or "")[:750],
            "author": replied_message.author.display_name,
            "message_id": replied_message.id,
            "jump_url": replied_message.jump_url,
        }
        if replied_message.attachments:
            replied_content["attachments"] = [a.filename for a in replied_message.attachments]
        if replied_message.embeds:
            replied_content["embeds"] = [e.to_dict() for e in replied_message.embeds]
        messages.append({
            "role": "user",
            "content": "THIS IS THE REPLIED-TO MESSAGE THAT MOST LIKELY CAUSED THE STAFF PING:\n"
                       f"{replied_content}",
        })
        temporary_message_queue = []
        async for history_msg in msg.channel.history(limit=50, oldest_first=False):
            if not history_msg.content.strip():
                continue
            to_add_message = {"role": "user"}
            content_dict = {"content": (history_msg.content or "")[:750], "author": history_msg.author.display_name}
            if history_msg.attachments:
                content_dict["attachments"] = [a.filename for a in history_msg.attachments]
            if history_msg.embeds:
                content_dict["embeds"] = [e.to_dict() for e in history_msg.embeds]
            to_add_message["content"] = str(content_dict)
            temporary_message_queue.append(to_add_message)
        messages.extend(temporary_message_queue[::-1])

        chatgpt_log_id = 1351956893119283270
        try:
            _, response_text = await chat_completion_text(
                self.bot,
                messages=messages,
                log_channel_id=chatgpt_log_id,
            )
        except Exception as e:
            await utils.safe_reply(notif, f"Failed to summarize logs. Sorry!\n`{e}`")
            self.bot.chatgpt_summaries.remove((msg.channel.id, msg.created_at.timestamp()))
            raise

        to_send = utils.split_text_into_segments(response_text, 2000)
        if to_send[0].strip().lower().startswith("no summary available"):
            self.bot.chatgpt_summaries.remove((msg.channel.id, msg.created_at.timestamp()))
            return
        for segment in to_send:
            await hf.send_to_test_channel(segment)

        await asyncio.sleep(60)
        self.bot.chatgpt_summaries.remove((msg.channel.id, msg.created_at.timestamp()))

    async def sp_serv_other_language_detection(self, msg: hf.RaiMessage):
        log_channel = self.bot.get_channel(1335631538716545054)
        if not log_channel:
            return
        if not msg.content:
            return
        if msg.guild != log_channel.guild:
            return
        if not self.bot.openai:
            return
        if msg.channel.type == discord.ChannelType.voice:
            return
        ignored_channel_ids = {817074401680818186, 1141761988012290179}
        if msg.channel.id in ignored_channel_ids:
            return
        parent_id = getattr(msg.channel, "parent_id", None)
        if parent_id in ignored_channel_ids:
            return

        message_cog = self.bot.get_cog("Message")
        if not message_cog:
            return
        if not hasattr(message_cog, "lingua_detector_eng_sp") or not hasattr(message_cog, "lingua_detector_full"):
            return

        stripped_content = utils.rem_emoji_url(msg).strip()
        no_duplicates = re.sub(r"(.)\1+", r"\1", stripped_content)
        if len(no_duplicates) < 10:
            return
        if re.search(r"[a-zA-Z]", stripped_content) and stripped_content.count(" ") == 0:
            return

        confidence_levels_two = message_cog.lingua_detector_full.compute_language_confidence_values(stripped_content)
        if confidence_levels_two[0].language not in [Language.ENGLISH, Language.SPANISH] and confidence_levels_two[0].value > 0.9:
            chatgpt_prompt = [{"role": "system",
                               "content": "Please check the language of the following messages. Respond either "
                                          "'en', 'es', 'both' (a mix of English and Spanish), "
                                          "or 'other' if it's another language "
                                          "or 'unknown' if it just looks like gibberish. "
                                          "It's ok if it has one or two "
                                          "words in another language as long as the main content of the message is "
                                          "English or Spanish.\n"
                                          "Some messages have phonetic pronunciations of words, ignore the "
                                          "phonetic pronunciations.\n"
                                          "Since it's an online chatroom, some messages will have gibberish "
                                          "('blpppp'). Ignore those."},
                              {"role": "user", "content": "Hello, this is English"},
                              {"role": "assistant", "content": "en"},
                              {"role": "user", "content": "entonces háblame en català"},
                              {"role": "assistant", "content": "es"},
                              {"role": "user", "content": "virtue - vérchiu\nreconciliation - riconsiliéishon\nseparate - sépareit"},
                              {"role": "assistant", "content": "en"},
                              {"role": "user", "content": "blppppp lets go"},
                              {"role": "assistant", "content": "en"},
                              {"role": "user", "content": "L AS M NO ALSKWLAK / A HAHAGAHA / asfasef"},
                              {"role": "assistant", "content": "unknown"},
                              {"role": "user", "content": stripped_content}]
            chatgpt_log_id = 1351956893119283270
            _, chatgpt_result = await chat_completion_text(
                self.bot,
                messages=chatgpt_prompt,
                log_channel_id=chatgpt_log_id,
            )
            if chatgpt_result != "other":
                return

            is_staff_member = log_channel.permissions_for(msg.author).read_messages
            if is_staff_member:
                author_name = msg.author.name
            else:
                author_name = msg.author.mention

            out = f"__{author_name} in {msg.jump_url}__\n> "
            out += msg.content.replace("\n", "\n> ")
            out += (f"\nSuspected language: {confidence_levels_two[0].language.name.capitalize()} "
                    f"({round(confidence_levels_two[0].value, 3)})")
            if msg.created_at.second % 10 in [0]:
                out += "\n__Information on below emojis__"
                out += "\n- ⚠️ - Format a warning to send to the user"
                out += "\n- ℹ️ - Format a friendlier modbot warning to send to the channel"
                out += "\n- ❌ - Delete this log (it was a mistaken detection)"
            sent_msg = await log_channel.send(out)
        else:
            return

        try:
            await sent_msg.add_reaction("⚠️")
            await sent_msg.add_reaction("ℹ️")
            await sent_msg.add_reaction("❌")
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def chatgpt_new_user_moderation(self, msg: hf.RaiMessage):
        chatgpt_log_id = 1351956893119283270
        if msg.guild.id != SP_SERVER_ID:
            return
        if not self.bot.message_queue:
            return
        if not self.bot.openai:
            return
        messages_in_last_month = hf.count_messages(msg.author.id, msg.guild)
        if messages_in_last_month > 10:
            return

        cached_messages = self.bot.message_queue.find_by_author(msg.author.id)
        if not cached_messages:
            await asyncio.sleep(0.1)
            cached_messages: list[hf.MiniMessage] = self.bot.message_queue.find_by_author(msg.author.id)
            if not cached_messages:
                return

        messages = []
        message_contents = ""
        attachment_url = ""
        for cached_message in cached_messages:
            if cached_message.content:
                message_contents += f"[{cached_message.created_at}]: {cached_message.content}\n"
            for attachment in cached_message.attachments:
                attachment_url = attachment["url"]
        messages.append({"type": "text", "text": message_contents})
        if attachment_url:
            messages.append({"type": "image_url", "image_url": {"url": attachment_url}})
        try:
            moderation_result = await moderation_with_image_fallback(
                self.bot,
                model="omni-moderation-latest",
                messages=messages,
                log_channel_id=chatgpt_log_id,
            )
        except Exception as e:
            await hf.segment_send(chatgpt_log_id, f"ERROR: `{e}`\n{messages}")
            raise

        if not moderation_result:
            return
        result = moderation_result.results[0]
        if not result.flagged:
            return
        await hf.segment_send(chatgpt_log_id, moderation_result)

        flagged_categories = [category[0] for category in result.categories if category[1]]
        out = f"__ChatGPT moderation result__\nby {msg.author.mention} in {msg.jump_url}\n"
        out += "Flagged categories:\n"
        out += "Category scores:\n"
        over_80 = False
        for category, score in result.category_scores:
            if category in flagged_categories:
                out += f"- {category}: {score}\n"
                if score > 0.8:
                    over_80 = True
        out += f"Message content:\n>>> {message_contents}\n"

        if over_80:
            watch_log_channel = self.bot.get_channel(704323978596188180)
            try:
                await utils.safe_send(watch_log_channel, out)  # pyright: ignore[reportArgumentType]
            except discord.Forbidden:
                pass

    @commands.command()
    @commands.is_owner()
    async def summarize(self, ctx: commands.Context, limit_jump_url: str = None, limit_message_number: Union[int] = 500):
        if not self.ai_features_enabled():
            await utils.safe_reply(ctx, "AI features in this module are disabled.")
            return
        if not self.bot.openai:
            await utils.safe_reply(ctx, "OpenAI not initialized")
            return
        if not limit_jump_url:
            await utils.safe_reply(
                ctx,
                "Please give a Discord message link to the message from which you want to summarize.",
            )
            return

        re_result = re.findall(
            r"https://(?:.*\.)?.*\.com/channels/\d{17,22}/(\d{17,22})/(\d{17,22})", limit_jump_url)
        if not re_result:
            await utils.safe_reply(
                ctx,
                "Invalid message link. Please give a message link to the message from which you want to summarize",
            )
            return
        channel_id = int(re_result[0][0])
        message_id = int(re_result[0][1])
        channel = self.bot.get_channel(channel_id)
        if not channel:
            await utils.safe_reply(ctx, "I couldn't find that channel.")
            return
        first_message = await channel.fetch_message(message_id)
        messages = [{"role": "developer",
                     "content": "Please summarize the main points of the conversation given, including the main points of each user. "
                                "Assume there is some important conversation happening, so if it ever looks like there's parts of "
                                "the conversations that get off topic or parts of the conversation where people get sidetracked "
                                "with casual conversation, please ignore those parts. Keep the answer very concise. For a debate or "
                                "discussion, summarize each party's main points with bullet points. If any conclusions were reached, "
                                "specify the conclusion. If the conversation involves messages from 'DM Modbot', messages starting with "
                                "'_' are private messages among moderators that don't get sent to the user."}]
        last_message = None
        async for message in channel.history(limit=limit_message_number, after=first_message.created_at, oldest_first=True):
            content = f"{message.author.display_name}: {message.content}"
            last_message = message
            messages.append({"role": "user", "content": content})

        if not last_message:
            await utils.safe_reply(ctx, "There were no messages after that link to summarize.")
            return

        await utils.safe_reply(ctx, f"Summarizing {len(messages)} messages from "
                               f"{first_message.jump_url} ({first_message.content[:50]}...)"
                               f"to {last_message.jump_url} ({last_message.content[:50]}...)")

        await hf.send_to_test_channel(messages)
        try:
            _, response_text = await chat_completion_text(self.bot, model="gpt-4o", messages=messages)
        except Exception as e:
            await hf.send_to_test_channel(f"Error: `{e}`\n{messages}")
            raise
        to_send = utils.split_text_into_segments(response_text, 2000)
        for message_part in to_send:
            await utils.safe_reply(ctx, message_part)

    @commands.command(name="openai_quota")
    @commands.is_owner()
    async def openai_quota(self, ctx: commands.Context):
        now = datetime.now(timezone.utc)
        last_day = int((now - timedelta(days=1)).timestamp())
        last_week = int((now - timedelta(days=7)).timestamp())

        requests = await asyncio.gather(
            fetch_openai_admin_json("/organization/costs", params={"start_time": last_day}),
            fetch_openai_admin_json(
                "/organization/usage/moderations",
                params={"start_time": last_week, "bucket_width": "1d", "limit": 7},
            ),
            fetch_openai_admin_json(
                "/organization/usage/completions",
                params={"start_time": last_week, "bucket_width": "1d", "limit": 7},
            ),
        )

        costs_status, key_source, costs_data = requests[0]
        moderations_status, _, moderations_data = requests[1]
        completions_status, _, completions_data = requests[2]

        lines = [f"OpenAI quota info using `{key_source}`",
                 "There is no simple 'remaining quota' endpoint here; this command shows org cost/usage endpoints."]

        if costs_status == 200:
            lines.append(f"Costs, last 24h: {summarize_cost_buckets(costs_data)}")
        else:
            lines.append(f"Costs endpoint failed: HTTP {costs_status} | {str(costs_data)[:500]}")

        if moderations_status == 200:
            lines.append(
                summarize_usage_buckets(
                    moderations_data,
                    label="Moderations, last 7d",
                    metric_keys=["input_tokens"],
                )
            )
        else:
            lines.append(f"Moderations usage failed: HTTP {moderations_status} | {str(moderations_data)[:500]}")

        if completions_status == 200:
            lines.append(
                summarize_usage_buckets(
                    completions_data,
                    label="Completions, last 7d",
                    metric_keys=["input_tokens", "output_tokens"],
                )
            )
        else:
            lines.append(f"Completions usage failed: HTTP {completions_status} | {str(completions_data)[:500]}")

        if any(status in [401, 403] for status in [costs_status, moderations_status, completions_status]):
            lines.append("These organization endpoints usually require an admin API key. Set `OPENAI_ADMIN_KEY` if needed.")

        for segment in utils.split_text_into_segments("\n".join(lines), 1900):
            await utils.safe_reply(ctx, segment)

    @commands.command(name="ai")
    @commands.is_owner()
    async def ai_toggle(self, ctx: commands.Context, mode: str = "status"):
        config = self.bot.db.setdefault("ai_features", {})
        current = config.get("enabled", True)
        normalized = mode.strip().lower()

        if normalized in ["status", "state"]:
            await utils.safe_reply(ctx, f"AI features in `cogs.ai` are currently {'enabled' if current else 'disabled'}.")
            return

        if normalized in ["on", "enable", "enabled", "true"]:
            new_state = True
        elif normalized in ["off", "disable", "disabled", "false"]:
            new_state = False
        elif normalized == "toggle":
            new_state = not current
        else:
            await utils.safe_reply(ctx, "Usage: `;ai [status|on|off|toggle]`")
            return

        config["enabled"] = new_state
        await utils.safe_reply(ctx, f"AI features in `cogs.ai` are now {'enabled' if new_state else 'disabled'}.")

    @commands.command(name="summary_now")
    @commands.is_owner()
    async def summary_now(self, ctx: commands.Context):
        if not self.ai_features_enabled():
            await utils.safe_reply(ctx, "AI features in this module are disabled.")
            return
        if not self.bot.openai:
            await utils.safe_reply(ctx, "OpenAI not initialized")
            return

        posted_summary = await self.maybe_run_channel_summary(force=True)
        if posted_summary:
            await utils.safe_reply(ctx, "Posted the latest completed 4-hour summary.")
        else:
            await utils.safe_reply(ctx, "No summary was posted for the latest completed 4-hour window.")


async def setup(bot: commands.Bot):
    await bot.add_cog(AI(bot))
