from datetime import datetime
import random

import discord
from discord.ext import commands
from cogs.utils.BotUtils import bot_utils as utils


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


class April(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.modules = [
            ButtonModule(bot),
            WorryBusinessModule(bot),
        ]

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
