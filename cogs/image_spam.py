import discord
from discord.ext import commands
from discord import app_commands

import time
import asyncio
import io
from datetime import datetime, timedelta, timezone

from PIL import Image
from io import BytesIO

class SolvedView(discord.ui.View):
    """
    Discord UI View that provides a button to mark an image spam alert as solved.

    When the button is pressed by a moderator, the alert embed is updated,
    the associated thread is deleted, and the alert lock is released so the
    user can be flagged again in the future.
    """
    def __init__(self, cog, thread, key):
        """
        Initialize the SolvedView.

        Parameters:
        - cog: Reference to the ImageSpam cog.
        - thread: The Discord thread containing evidence images.
        - key: Tuple (guild_id, user_id) used to track active alerts.
        """
        super().__init__(timeout=None)
        self.cog = cog
        self.thread = thread
        self.key = key

    @discord.ui.button(
        label="Mark as solved",
        style=discord.ButtonStyle.secondary,
        custom_id="solved_button"
    )
    async def solved(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Callback executed when the 'Mark as solved' button is pressed.

        - Updates the alert embed status
        - Deletes the evidence thread
        - Releases the alert lock for the user
        """
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message(
                "You don't have permission to do this.",
                ephemeral=True
            )
            return

        embed = interaction.message.embeds[0]

        for i, field in enumerate(embed.fields):
            if field.name == "Status":
                embed.set_field_at(
                    i,
                    name="Status",
                    value="✅ Solved",
                    inline=True
                )
                break

        embed.add_field(
            name=" ",
            value=(
                f"Solved by {interaction.user.mention} · "
                f"{datetime.now().strftime('%d/%m/%Y %H:%M')}"
            ),
            inline=False
        )

        button.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

        if self.thread:
            try:
                await self.thread.delete()
            except Exception as e:
                print("Error while solving alert:", e)

        # Reseting lock after solving the alert
        if self.key in self.cog.active_alerts:
            self.cog.active_alerts[self.key]["lock_alert"] = None


class ImageSpam(commands.Cog):
    """
    Cog responsible for detecting and handling image spam across multiple channels.

    The system tracks how many images a user sends within a configurable timeframe
    and triggers moderation actions (timeout, alerts, evidence) when
    spam behavior is detected.
    """
    def __init__(self, bot: commands.Bot):
        """
        Initialize the ImageSpam cog.

        Parameters:
        - bot: The main Discord bot instance.
        """
        self.bot = bot
        self.image_spam = {}

        # Tracks users with active spam alerts
        # Key: (guild_id, user_id) - Value: {"lock_user": asyncio.Lock(), "lock_alert": alert_msg_id or None}
        self.active_alerts = {}

        if "image_spam" not in self.bot.db:
            self.bot.db["image_spam"] = {}

    async def thread_to_image(self, thread: discord.Thread) -> io.BytesIO | None:
        """
        Combines all images posted in a thread into a single vertical image.

        Parameters:
        - thread: The Discord thread containing image attachments.

        Returns:
        - BytesIO object containing the merged image, or None if no images exist.
        """
        images = []

        async for msg in thread.history(oldest_first=True):
            for att in msg.attachments:
                if att.content_type and att.content_type.startswith("image/"):
                    data = await att.read()
                    img = Image.open(BytesIO(data)).convert("RGB")
                    images.append(img)

        if not images:
            return None

        max_width = max(img.width for img in images)
        total_height = sum(img.height for img in images)

        final = Image.new(
            "RGB",
            (max_width, total_height),
            (255, 255, 255)
        )

        y = 0
        for img in images:
            if img.width != max_width:
                ratio = max_width / img.width
                img = img.resize((max_width, int(img.height * ratio)))
            final.paste(img, (0, y))
            y += img.height

        buffer = BytesIO()
        final.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    @app_commands.command(
        name="spam_enable",
        description="Enable image spam detection"
    )
    @discord.app_commands.describe(
        channel="The text channel where alerts for flagged users will be sent",
        limit="The number of images required to trigger spam detection",
        timeframe="The time interval (in seconds) between images used to detect spam",
        timeout="The duration (in minutes) the user will be punished for spamming"
    )
    @app_commands.default_permissions(administrator=True)
    async def spam_enable(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        limit: int = 2,
        timeframe: int = 10,
        timeout: int = 60
    ):
        """
        Enables image spam detection for the guild and stores configuration.

        Parameters:
        - channel: Channel where alerts will be sent.
        - limit: Number of images required to trigger detection.
        - timeframe: Time window (seconds) to count images.
        - timeout: Duration (minutes) of the user timeout.
        """
        g_id = str(interaction.guild.id)

        config = self.bot.db["image_spam"].setdefault(g_id, {})

        config.update({
            "enabled": True,
            "channel": channel.id,
            "limit": limit,
            "timeframe": timeframe,
            "timeout": timeout
        })

        embed = discord.Embed(
            title="⚠️ Image Spam Module",
            description=f"The module is now enabled. Alerts will be sent in {channel.mention}.",
            color=discord.Color.blue()
        )

        embed.add_field(name="Limit", value=f"{limit} images", inline=True)
        embed.add_field(name="Timeframe", value=f"{timeframe} seconds", inline=True)
        embed.add_field(name="Timeout", value=f"{timeout // 60} hour(s)", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="spam_disable",
        description="Disable image spam detection"
    )
    @app_commands.default_permissions(administrator=True)
    async def spam_disable(self, interaction: discord.Interaction):
        """
        Disables image spam detection for the current guild.
        """
        g_id = str(interaction.guild.id)
        config = self.bot.db.get("image_spam", {})

        if g_id in config:
            config[g_id]["enabled"] = False

        embed = discord.Embed(
            title="⚠️ Image Spam Module",
            description="The module is currently disabled for this guild.",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Use /spam_enable to enable image spam detection")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Listens for new messages and detects image spam behavior.

        If spam is detected:
        - Times out the user
        - Sends an alert embed
        - Collects image evidence
        - Deletes spam messages
        """
        if message.author.bot or not message.guild:
            return

        g_id = str(message.guild.id)
        config = self.bot.db.get("image_spam", {}).get(g_id)
        if not config or not config.get("enabled"):
            return

        images = [
            a for a in message.attachments
            if a.content_type and a.content_type.startswith("image/")
        ]
        if not images:
            return

        key = (message.guild.id, message.author.id)
        now = time.time()

        self.image_spam.setdefault(key, [])
        self.image_spam[key].extend((now, message.channel.id, message.id, att) for att in images)
        self.image_spam[key] = [x for x in self.image_spam[key] if now - x[0] <= config["timeframe"]]

        channels_used = {}
        for _, ch, _, _ in self.image_spam[key]:
            channels_used[ch] = channels_used.get(ch, 0) + 1

        if len(self.image_spam[key]) <= config["limit"] or len(channels_used) <= 1:
            return

        if key not in self.active_alerts:
            self.active_alerts[key] = {
                "lock_user": asyncio.Lock(),
                "lock_alert": None
            }

        async with self.active_alerts[key]["lock_user"]:
            # Already under alert?
            if self.active_alerts[key]["lock_alert"]:
                return

            alert_channel = self.bot.get_channel(config["channel"])
            if not alert_channel:
                return

            until = datetime.now(timezone.utc) + timedelta(minutes=config["timeout"])
            bot_member = message.guild.me

            try:
                if bot_member.guild_permissions.moderate_members and message.author.top_role < bot_member.top_role:
                    await message.author.timeout(until, reason="Automated detection of image spam")
            except Exception:
                pass

            total_images = len(self.image_spam[key])
            top_channels = sorted(channels_used.items(), key=lambda x: x[1], reverse=True)
            top_channels_mentions = "\n".join(
                f"・<#{ch_id}> ({(count / total_images) * 100:.1f}%)" for ch_id, count in top_channels
            )

            joined_at = message.author.joined_at.strftime("%d/%m/%Y %H:%M") if message.author.joined_at else "Unknown"
            timed_time = int(datetime.now().timestamp())

            embed = discord.Embed(
                title="⚠️ Image Spam Detected",
                description=f"{message.author.mention} was **timed out** <t:{timed_time}:R> for **{config['timeout'] // 60} hour(s)**",
                color=discord.Color.blue()
            )
            embed.add_field(name="Status", value="❌ Unsolved", inline=True)
            embed.add_field(name="Rate", value=f"{total_images} images / {config['timeframe']} seconds", inline=True)
            embed.add_field(name="Top Spammed", value=top_channels_mentions, inline=True)
            embed.set_footer(
                text=f"Joined: {joined_at}",
                icon_url=(message.author.avatar.url if message.author.avatar else None)
            )

            alert_msg = await alert_channel.send(content=str(message.author.id), embed=embed)

            files = []
            seen = set()
            top_channel = top_channels[0][0]
            for _, ch, _, att in self.image_spam[key]:
                if ch == top_channel and att.filename not in seen:
                    seen.add(att.filename)
                    data = await att.read()
                    files.append(discord.File(io.BytesIO(data), filename=att.filename))

            thread = await alert_msg.create_thread(name=f"Spam by {message.author.name} - {message.author.id}")
            await asyncio.gather(*(thread.send(file=f) for f in files))

            await alert_msg.edit(view=SolvedView(self, thread, key))

            self.active_alerts[key]["lock_alert"] = alert_msg.id

            # Delete spam messages
            for _, ch, msg_id, _ in self.image_spam[key]:
                try:
                    channel = self.bot.get_channel(ch)
                    if channel:
                        msg = await channel.fetch_message(msg_id)
                        await msg.delete()
                except:
                    pass

            self.image_spam[key] = []

            try:
                await asyncio.sleep(1.5)
                evidence = await self.thread_to_image(thread)
                if evidence:
                    await alert_channel.send(
                        content="**Evidence**",
                        file=discord.File(evidence, filename=f"{message.author.id}_evidence_spam.png")
                    )
            except Exception as e:
                print("Evidence generation failed:", e)

async def setup(bot: commands.Bot):
    """
    Loads the ImageSpam cog into the bot.
    """
    await bot.add_cog(ImageSpam(bot))
