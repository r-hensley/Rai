from datetime import datetime
import random

import discord
from discord.ext import commands
from cogs.utils.BotUtils import bot_utils as utils

jp_serv_id = 189571157446492161
jp_category = 360571352102600704

sp_serv_id = 243838819743432704
sp_category = 685445597121216524

SERVER_CONFIGS = {
    jp_serv_id: {
        "category_id": jp_category,
        "counter_key": "jp",
    },
    sp_serv_id: {
        "category_id": sp_category,
        "counter_key": "sp",
    },
}

MESSAGES_PER_BUTTON = 100
BUTTON_REQUEST_MESSAGES = [
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
FIRST_PRESS_RESPONSES = [
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
REPEAT_PRESS_RESPONSES = [
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
    def __init__(self):
        super().__init__(timeout=70)
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
            thank_you = random.choice(REPEAT_PRESS_RESPONSES).format(count=push_count)
        else:
            thank_you = random.choice(FIRST_PRESS_RESPONSES)

        await interaction.followup.send(thank_you)
        await utils.dump_json("db")
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


class April(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def is_april_fools() -> bool:
        now = datetime.now()
        return now.month == 4 and now.day == 1

    @staticmethod
    def message_is_in_target_category(msg: discord.Message, category_id: int) -> bool:
        channel = msg.channel
        if isinstance(channel, discord.Thread):
            parent = channel.parent
            return bool(parent and getattr(parent.category, "id", None) == category_id)
        return getattr(channel.category, "id", None) == category_id

    async def send_button_prompt(self, channel: discord.abc.Messageable):
        view = PanicButtonView()
        try:
            message = await channel.send(random.choice(BUTTON_REQUEST_MESSAGES), view=view)
        except discord.HTTPException:
            return

        view.message = message

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if not self.is_april_fools():
            return
        if msg.author.bot or not msg.guild:
            return

        server_config = SERVER_CONFIGS.get(msg.guild.id)
        if not server_config:
            return
        if not self.message_is_in_target_category(msg, server_config["category_id"]):
            return

        counts = self.bot.db.setdefault("april_button_message_counts", {})
        counter_key = server_config["counter_key"]
        count = counts.get(counter_key, 0) + 1
        counts[counter_key] = count

        if count % MESSAGES_PER_BUTTON == 0:
            await self.send_button_prompt(msg.channel)

        if count % 25 == 0 or count % MESSAGES_PER_BUTTON == 0:
            await utils.dump_json("db")

    @commands.command(name="april")
    async def april(self, ctx):
        counts = self.bot.db.get("april_button_message_counts", {})
        await ctx.send(
            f"JP count: {counts.get('jp', 0)} | SP count: {counts.get('sp', 0)}"
        )


async def setup(bot):
    await bot.add_cog(April(bot))