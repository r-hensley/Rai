from datetime import datetime, timezone
import random

import discord
from discord.ext import commands, tasks
from cogs.utils.BotUtils import bot_utils as utils
from .ai import chat_completion_text, setup_openai_client


class ButtonModule:
    jp_serv_id = 189571157446492161
    jp_category = 360571352102600704

    sp_serv_id = 243838819743432704
    sp_category = 685445597121216524
    sp_category_2 = 1369719925421375498

    server_configs = {
        jp_serv_id: {
            "category_ids": [jp_category],
            "counter_key": "jp",
        },
        sp_serv_id: {
            "category_ids": [sp_category, sp_category_2],
            "counter_key": "sp",
        },
    }

    messages_per_button = 100
    button_request_messages = [
        "Warning: If you push this button the server gets deleted.",
        "Quick! Push this button!",
        "Emergency! This button requires immediate poking!",
        "Press the scary red button. Nothing bad will probably happen.",
        "Attention please: dramatic button-pushing is now required.",
        "Rapid response needed. Slam the button.",
        "Urgent April protocol: push the button!",
        "This button looks lonely. Fix that.",
        "Warning: the red button demands a hero.",
        "Oye, rapido, pulsa este boton!",
        "Boton importante. Casi seguramente. Presionalo.",
        "たすけて! このボタンを押して!",
        "緊急です! 赤いボタンを押してください!",
    ]
    first_press_responses = [
        "Ah, thanks.",
        "Excellent. Crisis averted.",
        "Perfect timing. The button gods are pleased.",
        "Much appreciated. That was deeply official.",
        "Thank you for your brave service.",
        "Nice. That looked important.",
        "Gracias. Eso era absolutamente necesario.",
        "Gracias por oprimir el boton aterrador.",
        "助かりました。ありがとう。",
        "ありがとう。とてもボタンでした。",
    ]
    repeat_press_responses = [
        "Ah, thanks for your repeated assistance. You've pushed it {count} times.",
        "Back again. Excellent. You've saved us {count} times now.",
        "Reliable as ever. This is push number {count} for you.",
        "Your continued button support is noted. Total pushes: {count}.",
        "Impressive dedication. You've pressed the thing {count} times.",
        "You keep answering the call. Lifetime pushes: {count}.",
        "Gracias otra vez. Ya llevas {count} pulsaciones.",
        "Tu asistencia continua es admirable. Total: {count}.",
        "また助けてくれてありがとう。これで{count}回目です。",
        "いつもありがとう。このボタンはもう{count}回押されました。",
    ]

    class PanicButtonView(discord.ui.View):
        def __init__(self, module: "ButtonModule"):
            super().__init__(timeout=70)
            self.module = module
            self.pressed = False
            self.message: discord.Message | None = None

        @discord.ui.button(label="PUSH THE BUTTON", style=discord.ButtonStyle.danger)
        async def push_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.pressed:
                await interaction.response.send_message("Too late.", ephemeral=True)
                return

            config = interaction.client.db.setdefault("april_button", {})
            user_id = str(interaction.user.id)
            push_count = config.get(user_id, 0) + 1
            config[user_id] = push_count

            self.pressed = True
            button.disabled = True
            await interaction.response.edit_message(view=self)
            if push_count > 1:
                thank_you = random.choice(self.module.repeat_press_responses).format(count=push_count)
            else:
                thank_you = random.choice(self.module.first_press_responses)

            await interaction.followup.send(f"{interaction.user.mention}\n{thank_you}")
            self.stop()

        async def on_timeout(self):
            if not self.message or self.pressed:
                return

            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True

            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def is_april_fools() -> bool:
        now = datetime.now()
        return now.month == 4 and now.day == 1

    @staticmethod
    def message_is_in_target_categories(msg: discord.Message, category_ids: list[int]) -> bool:
        channel = msg.channel
        if isinstance(channel, discord.Thread):
            parent = channel.parent
            return bool(parent and getattr(parent.category, "id", None) in category_ids)
        return getattr(channel.category, "id", None) in category_ids

    async def send_button_prompt(self, channel: discord.abc.Messageable):
        view = self.PanicButtonView(self)
        try:
            message = await channel.send(random.choice(self.button_request_messages), view=view)
        except discord.HTTPException:
            return

        view.message = message

    async def on_message(self, msg: discord.Message):
        if not self.is_april_fools():
            return
        if msg.author.bot or not msg.guild:
            return

        server_config = self.server_configs.get(msg.guild.id)
        if not server_config:
            return
        if not self.message_is_in_target_categories(msg, server_config["category_ids"]):
            return

        counts = self.bot.db.setdefault("april_button_message_counts", {})
        counter_key = server_config["counter_key"]
        existing_counts = counts.get(counter_key, {})
        if isinstance(existing_counts, int):
            # Migrate legacy per-server integer counters to per-channel storage.
            existing_counts = {"_legacy": existing_counts}
            counts[counter_key] = existing_counts
        server_counts = existing_counts
        channel_key = str(msg.channel.id)
        count = server_counts.get(channel_key, 0) + 1
        server_counts[channel_key] = count

        if count % self.messages_per_button == 0:
            await self.send_button_prompt(msg.channel)

    async def status(self) -> str:
        counts = self.bot.db.get("april_button_message_counts", {})

        def total_for(server_key: str) -> int:
            value = counts.get(server_key, {})
            if isinstance(value, int):
                return value
            return sum(value.values())

        jp_total = total_for("jp")
        sp_total = total_for("sp")
        return f"JP total: {jp_total} | SP total: {sp_total}"


class WorryBusinessModule:
    channel_id = 1488585806775058674
    shame_messages = [
        "🚨 You posted without `worrybusiness`. You are gone from this channel. 🚫",
        "❌ This channel had one rule: include `worrybusiness`. You are removed from this channel. 😤",
        "🙅 No `worrybusiness`? Bold mistake. Channel ban. 🚪",
        "⚠️ You had one job: include `worrybusiness`. You have been removed from this channel. 😠",
        "😑 Disappointing. Please reflect on your lack of `worrybusiness`. Channel exile activated. 🚫",
        "📛 Channel law violated. `worrybusiness` was required. You are banned from this channel. 🚷",
        "🚨 `worrybusiness` を書いてないです。だめです。このチャンネルBANです。🚫",
        "😤 残念です。`worrybusiness` が必要でした。このチャンネルから削除です。🚪",
        "❌ `worrybusiness` がないので失格です。このチャンネル利用禁止です。🙅",
        "📛 このチャンネルでは `worrybusiness` を入れてください。今回はこのチャンネルBANです。⚠️",
    ]

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def is_april_fools() -> bool:
        now = datetime.now()
        return now.month == 4 and now.day == 1

    async def on_message(self, msg: discord.Message):
        if not self.is_april_fools():
            return
        if msg.author.bot or not msg.guild:
            return
        if msg.channel.id != self.channel_id:
            return
        if "worrybusiness" in msg.content.lower():
            return

        try:
            await msg.channel.send(f"{msg.author.mention} {random.choice(self.shame_messages)}")
        except discord.HTTPException:
            pass

        overwrite = msg.channel.overwrites_for(msg.author)
        overwrite.send_messages = False
        try:
            await msg.channel.set_permissions(
                msg.author,
                overwrite=overwrite,
                reason="April Fools worrybusiness enforcement: channel-only send restriction",
            )
        except discord.HTTPException:
            pass


class MysteriousMessageModule:
    channel_id = 296491080881537024
    mysterious_messages = [
        "This user has been saved.",
        "The signal has been received.",
        "Your presence has been noted.",
        "The cycle continues.",
        "They have been chosen.",
        "The record has been updated.",
        "An offering has been accepted.",
        "The alignment is complete.",
        "This soul has been catalogued.",
        "The transaction is finalized.",
        "Their fate has been sealed.",
        "The convergence is approaching.",
        "This one has been marked.",
        "The pattern recognizes you.",
        "Existence confirmed. Proceed.",
        "The archive grows.",
        "Your thread remains unbroken.",
        "The watchers are pleased.",
        "An anomaly has been resolved.",
        "This message has been received by the council.",
        "The process is ongoing.",
        "Sanctuary has been granted.",
        "The ledger has been updated.",
        "You have been witnessed.",
        "The ritual is complete.",
        "This account has been balanced.",
        "The door remains open.",
        "A light has been preserved.",
        "The coordinates have been logged.",
        "This user has been accounted for.",
    ]
    mysterious_messages_es = [
        "Este usuario ha sido rescatado.",
        "La señal ha sido captada.",
        "Su existencia ha sido registrada.",
        "El equilibrio se ha restaurado.",
        "Han sido seleccionados.",
        "El protocolo ha sido activado.",
        "La ofrenda ha sido recibida.",
        "El alineamiento ha concluido.",
        "Esta alma ha sido inscrita.",
        "El intercambio ha sido completado.",
        "Su destino ha quedado sellado.",
        "La convergencia se acerca.",
        "Este individuo ha sido marcado.",
        "El patrón te ha reconocido.",
        "Presencia verificada. Continúe.",
        "El archivo se expande.",
        "Su hilo permanece intacto.",
        "Los observadores están satisfechos.",
        "La anomalía ha sido corregida.",
        "El consejo ha tomado nota.",
        "El proceso avanza sin detenerse.",
        "El refugio ha sido concedido.",
        "El registro ha sido actualizado.",
        "Has sido contemplado.",
        "El rito ha concluido.",
        "La cuenta ha sido saldada.",
        "El umbral permanece abierto.",
        "Una llama ha sido preservada.",
        "Las coordenadas han sido guardadas.",
        "Este usuario ha sido contabilizado.",
    ]

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def is_april_fools() -> bool:
        now = datetime.now()
        return now.month == 4 and now.day == 1

    async def send_mysterious_message(self):
        if not self.is_april_fools():
            return
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            return
        try:
            messages = [msg async for msg in channel.history(limit=1)]
        except discord.HTTPException:
            return
        if not messages:
            return
        try:
            await messages[0].reply(random.choice(self.mysterious_messages + self.mysterious_messages_es))
        except discord.HTTPException:
            pass


class RaiPingModule:
    """Responds to pings or replies directed at Rai with a sarcastic ChatGPT reply."""

    COOLDOWN_SECONDS = 15
    MAX_CHAIN_LENGTH = 10
    SYSTEM_PROMPT = (
        "You are an extremely sarcastic and mocking assistant. "
        "Respond to every message with heavy sarcasm, condescension, and mockery. "
        "Be witty. Keep your response under 200 words, but a shorter reply is perfectly fine "
        "if it gets the point across — do not pad your response just to reach 200 words. "
        "Vary your response structure and opening every single time — never start two replies "
        "with the same word or phrase. Mix up your tone: sometimes deadpan, sometimes "
        "dramatically over-the-top, sometimes coldly dismissive, sometimes faux-impressed. "
        "If the user's message is in Spanish, you must respond in Spanish. "
        "Otherwise, respond in English."
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_response_time: float = 0.0

    def _strip_bot_mention(self, text: str) -> str:
        """Remove bot mention tokens from a message string."""
        if not self.bot.user:
            return text
        text = text.replace(self.bot.user.mention, "").strip()
        text = text.replace(f"<@!{self.bot.user.id}>", "").strip()
        return text

    async def _build_conversation(self, msg: discord.Message) -> list[dict[str, str]]:
        """
        Walk the reply chain (up to MAX_CHAIN_LENGTH messages) starting from *msg*
        and return an ordered list of {role, content} dicts suitable for the
        ChatGPT messages array (oldest message first, newest last).
        """
        # Each iteration adds one message and follows one reply link upward,
        # so the loop naturally collects at most MAX_CHAIN_LENGTH messages.
        chain: list[dict[str, str]] = []
        current: discord.Message = msg

        for _ in range(self.MAX_CHAIN_LENGTH):
            content = self._strip_bot_mention(current.content) or "(no message)"
            role = "assistant" if (self.bot.user and current.author.id == self.bot.user.id) else "user"
            chain.append({"role": role, "content": content})

            # Follow the reply chain upward.
            if not current.reference or not current.reference.message_id:
                break

            resolved = current.reference.resolved
            if isinstance(resolved, discord.Message):
                current = resolved
            else:
                try:
                    current = await current.channel.fetch_message(current.reference.message_id)
                except discord.HTTPException:
                    break

        chain.reverse()  # oldest first
        return chain

    def _is_reply_to_bot(self, msg: discord.Message) -> bool:
        """Return True if *msg* is a reply whose parent message was sent by the bot."""
        if not msg.reference or not msg.reference.message_id:
            return False
        resolved = msg.reference.resolved
        if isinstance(resolved, discord.Message):
            return bool(self.bot.user and resolved.author.id == self.bot.user.id)
        # If not cached we cannot confirm without a fetch; treated as False.
        return False

    async def on_message(self, msg: discord.Message):
        if msg.author.bot or not msg.guild:
            return
        if not self.bot.user:
            return

        is_ping = self.bot.user in msg.mentions
        is_reply_to_bot = self._is_reply_to_bot(msg)
        if not is_ping and not is_reply_to_bot:
            return

        now = datetime.now(tz=timezone.utc).timestamp()
        if now - self._last_response_time < self.COOLDOWN_SECONDS:
            return
        self._last_response_time = now

        setup_openai_client(self.bot)
        if not getattr(self.bot, "openai", None):
            return

        conversation = await self._build_conversation(msg)
        # Require at least one user-role message so the API call is well-formed.
        if not any(m["role"] == "user" for m in conversation):
            return
        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}] + conversation

        try:
            _, response_text = await chat_completion_text(self.bot, messages=messages)
        except Exception:
            return

        try:
            await msg.reply(response_text)
        except discord.HTTPException:
            pass


class April(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mysterious_module = MysteriousMessageModule(bot)
        self.modules = [
            ButtonModule(bot),
            WorryBusinessModule(bot),
            RaiPingModule(bot),
        ]
        self.mysterious_message_task.start()

    def cog_unload(self):
        self.mysterious_message_task.cancel()

    @tasks.loop(minutes=15)
    async def mysterious_message_task(self):
        await self.mysterious_module.send_mysterious_message()

    @mysterious_message_task.before_loop
    async def before_mysterious_message_task(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        for module in self.modules:
            await module.on_message(msg)

    @commands.command(name="april")
    async def april(self, ctx):
        button_module = next(module for module in self.modules if isinstance(module, ButtonModule))
        await ctx.send(await button_module.status())


async def setup(bot):
    await bot.add_cog(April(bot))
