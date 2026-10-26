import discord
from discord.ext import commands
from discord import app_commands

import time
import asyncio
import io
import logging
from datetime import datetime, timedelta

from PIL import Image
from io import BytesIO
from .utils import helper_functions as hf

log = logging.getLogger(__name__)
EVIDENCE_TIMEOUT_SECONDS = 60
EVIDENCE_DELAY_SECONDS = 1.5
BAN_TIMEOUT_SECONDS = 60
ALERT_TIMEOUT_SECONDS = 10

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

        # consider:
        # with BytesIO() as buffer:
        buffer = BytesIO()
        final.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    async def collect_evidence(self, alert_msg, alert_channel, member, entries, top_channel, state):
        """Collect evidence under the caller's deadline; keep partial threads on failure."""
        files = []
        seen = set()
        try:
            for _, ch, _, att in entries:
                if ch != top_channel or att.filename in seen:
                    continue
                seen.add(att.filename)
                try:
                    data = await att.read()
                except (discord.NotFound, discord.HTTPException):
                    continue
                files.append(discord.File(io.BytesIO(data), filename=att.filename))

            thread = await alert_msg.create_thread(name=f"Spam by {member.name} - {member.id}")
            state['thread'] = thread
            for file in files:
                await thread.send(file=file)

            # Multiple attachments can belong to one message. Delete it only once.
            for ch, msg_id in dict.fromkeys((ch, msg_id) for _, ch, msg_id, _ in entries):
                channel = self.bot.get_channel(ch)
                if channel:
                    try:
                        msg = await channel.fetch_message(msg_id)
                        await msg.delete()
                    except discord.HTTPException:
                        log.warning('Could not delete image-spam message %s', msg_id, exc_info=True)

            await asyncio.sleep(EVIDENCE_DELAY_SECONDS)
            evidence = await self.thread_to_image(thread)
            if evidence:
                file = discord.File(evidence, filename=f"{member.id}_evidence_spam.png", spoiler=True)
                try:
                    state['evidence_msg'] = await alert_channel.send(content="-# Evidence", file=file)
                finally:
                    file.close()
        finally:
            for file in files:
                file.close()

    async def update_alert(self, alert_msg, embed, status):
        embed.set_field_at(0, name="Status", value=status, inline=True)
        try:
            await asyncio.wait_for(alert_msg.edit(embed=embed), ALERT_TIMEOUT_SECONDS)
        except (discord.HTTPException, asyncio.TimeoutError):
            log.warning('Could not update image-spam alert %s to %s', alert_msg.id, status, exc_info=True)

    @app_commands.command(
        name="spam_enable",
        description="Enable image spam detection"
    )
    @discord.app_commands.describe(
        channel="The text channel where alerts for flagged users will be sent",
        limit="The number of images required to trigger spam detection",
        timeframe="The time interval (in seconds) between images used to detect spam",
    )
    @app_commands.default_permissions(administrator=True)
    async def spam_enable(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        limit: int = 2,
        timeframe: int = 10,
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
        })
        config.pop("timeout", None)

        embed = discord.Embed(
            title="⚠️ Image Spam Module",
            description=f"The module is now enabled. Alerts will be sent in {channel.mention}.",
            color=discord.Color.blue()
        )

        embed.add_field(name="Limit", value=f"{limit} images", inline=True)
        embed.add_field(name="Timeframe", value=f"{timeframe} seconds", inline=True)

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
        - Sends an alert embed
        - Collects image evidence
        - Deletes spam messages
        - Ban the user
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

        member = message.author

        key = (message.guild.id, member.id)
        now = time.time()

        self.image_spam.setdefault(key, [])
        self.image_spam[key].extend((now, message.channel.id, message.id, att) for att in images)
        self.image_spam[key] = [x for x in self.image_spam[key] if now - x[0] <= config["timeframe"]]

        channels_used = {}
        for _, ch, _, _ in self.image_spam[key]:
            channels_used[ch] = channels_used.get(ch, 0) + 1

        if len(self.image_spam[key]) < config["limit"] or len(channels_used) <= 1:
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

            # Earlier listeners may have finished handling and cleared these
            # entries while this listener waited for the per-member lock.
            entries = tuple(self.image_spam.get(key, ()))
            if not entries:
                return
            channels_used = {}
            for _, ch, _, _ in entries:
                channels_used[ch] = channels_used.get(ch, 0) + 1
            if len(entries) < config["limit"] or len(channels_used) <= 1:
                return

            alert_channel = self.bot.get_channel(config["channel"])
            if not alert_channel:
                return

            bot_member = message.guild.me

            timeout_seconds = 7 * 24 * 60 * 60  # Timeout 1 week
            timeout_applied = False
            try:
                if bot_member.guild_permissions.moderate_members and member.top_role < bot_member.top_role:
                    await asyncio.wait_for(member.timeout(timedelta(seconds=timeout_seconds)), ALERT_TIMEOUT_SECONDS)
                    timeout_applied = True
            except Exception:
                log.warning('Image-spam timeout failed for %s', key, exc_info=True)

            total_images = len(entries)
            top_channels = sorted(channels_used.items(), key=lambda x: x[1], reverse=True)
            top_channels_mentions = "\n".join(
                f"・<#{ch_id}> ({(count / total_images) * 100:.1f}%)" for ch_id, count in top_channels
            )

            joined_at = message.author.joined_at.strftime("%d/%m/%Y %H:%M") if message.author.joined_at else "Unknown"
            timed_time = int(datetime.now().timestamp())

            embed = discord.Embed(
                title="⚠️ Image Spam Detected",
                description=(f"-# {member.mention} was timed out <t:{timed_time}:R> for 1 week."
                             if timeout_applied else f"-# No timeout was confirmed for {member.mention}."),
                color=discord.Color.blue()
            )
            embed.add_field(name="Status", value="⌛ Collecting evidence...", inline=True)
            embed.add_field(name="Rate", value=f"{total_images} images / {config['timeframe']} seconds", inline=True)
            embed.add_field(name="Top Spammed", value=top_channels_mentions, inline=True)
            embed.set_footer(
                text=f"Joined: {joined_at}",
                icon_url=(message.author.avatar.url if message.author.avatar else None)
            )

            alert_msg = await alert_channel.send(content=str(message.author.id), embed=embed)

            self.active_alerts[key]["lock_alert"] = alert_msg.id
            evidence_state = {'thread': None, 'evidence_msg': None}
            try:
                try:
                    await asyncio.wait_for(
                        self.collect_evidence(
                            alert_msg, alert_channel, member, entries, top_channels[0][0], evidence_state,
                        ),
                        EVIDENCE_TIMEOUT_SECONDS,
                    )
                except Exception:
                    log.exception('Image-spam evidence collection failed for %s', key)
                    embed.add_field(name="Evidence", value="Collection incomplete; partial thread retained.", inline=False)

                banned = False
                if not bot_member.guild_permissions.ban_members:
                    status = "❌ Not banned: Rai needs the Ban Members permission."
                elif member.id == message.guild.owner_id or member.top_role >= bot_member.top_role:
                    status = "❌ Not banned: this member is above Rai in the role hierarchy or owns the server."
                else:
                    await self.update_alert(alert_msg, embed, "⌛ Banning...")
                    try:
                        await asyncio.wait_for(
                            hf.auto_ban(member=member, evidence_msg=evidence_state['evidence_msg']),
                            BAN_TIMEOUT_SECONDS,
                        )
                    except asyncio.TimeoutError:
                        status = "⚠️ Ban unconfirmed: request timed out. Check the server audit log."
                        log.warning('Image-spam ban timed out for %s', key)
                    except discord.HTTPException as exc:
                        status = f"❌ Ban failed: Discord HTTP {exc.status} (code {exc.code}). Check permissions and role hierarchy."
                        log.exception('Image-spam ban failed for %s', key)
                    except Exception:
                        status = "⚠️ Ban unconfirmed: an internal error occurred. Check the server audit log."
                        log.exception('Image-spam ban failed for %s', key)
                    else:
                        banned = True
                        status = "✅ Banned"

                # Report the result before optional cleanup can fail or stall.
                await self.update_alert(alert_msg, embed, status)
                if banned and evidence_state['evidence_msg'] and evidence_state['thread']:
                    try:
                        await asyncio.wait_for(evidence_state['thread'].delete(), ALERT_TIMEOUT_SECONDS)
                    except (discord.HTTPException, asyncio.TimeoutError):
                        log.warning('Image-spam evidence thread cleanup failed for %s', key, exc_info=True)
            finally:
                self.image_spam[key] = []
                self.active_alerts[key]["lock_alert"] = None

async def setup(bot: commands.Bot):
    """
    Loads the ImageSpam cog into the bot.
    """
    await bot.add_cog(ImageSpam(bot))
