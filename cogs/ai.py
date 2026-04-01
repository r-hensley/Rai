import asyncio
import logging
import os
import re
import traceback
from typing import Any, Union

import discord
import openai
from discord.ext import commands
from lingua import Language
from openai import AsyncOpenAI

from cogs.utils.BotUtils import bot_utils as utils
from .utils import helper_functions as hf

SP_SERVER_ID = 243838819743432704
JP_SERVER_ID = 189571157446492161


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
    except openai.BadRequestError as e:
        if log_channel_id:
            await hf.segment_send(log_channel_id, messages)
        moderation_result = None
        ignore_strings = ["invalid_image_format", "image_url_unavailable", "file_too_large", "Failed to download"]
        if any(ignore_string in str(e) for ignore_string in ignore_strings):
            filtered_messages = [m for m in messages if m.get("type") != "image_url"]
            if len(filtered_messages) != len(messages):
                moderation_result = await openai_request(
                    lambda: bot.openai.moderations.create(model=model, input=filtered_messages)
                )
        if not moderation_result:
            raise
        return moderation_result


class AI(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, msg_in: discord.Message):
        if not msg_in.guild:
            return
        msg = hf.RaiMessage(msg_in)
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
        if msg.channel.id == 817074401680818186:
            return
        if getattr(msg.channel, "parent", None):
            if msg.channel.parent.id == 1141761988012290179:
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


async def setup(bot: commands.Bot):
    await bot.add_cog(AI(bot))
