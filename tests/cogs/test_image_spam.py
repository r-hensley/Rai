import asyncio
import io
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from cogs import image_spam
from cogs.utils import helper_functions as hf
from tests.discord_fakes import (
    make_attachment, make_bot, make_channel, make_guild, make_member,
    make_message, make_thread,
)


def http_error(status=403):
    return discord.HTTPException(
        SimpleNamespace(status=status, reason='Test failure'),
        {'code': 50013, 'message': 'Test failure'},
    )


@pytest.fixture
def spam_case(monkeypatch):
    guild = make_guild(owner_id=999)
    guild.me = SimpleNamespace(
        top_role=10,
        guild_permissions=SimpleNamespace(moderate_members=True, ban_members=True),
    )
    member = make_member(
        guild=guild, top_role=1, avatar=None,
        joined_at=datetime(2025, 1, 1, tzinfo=timezone.utc), timeout=AsyncMock(),
    )
    channels = [make_channel(channel_id=i, guild=guild) for i in (100, 101)]
    alert_channel = make_channel(channel_id=102, guild=guild, send=AsyncMock())
    thread = make_thread(
        guild=guild, parent=alert_channel, send=AsyncMock(), delete=AsyncMock(),
    )
    rai = make_member(member_id=777, guild=guild, bot=True)
    alert = make_message(
        channel=alert_channel, guild=guild, author=rai, edit=AsyncMock(),
        create_thread=AsyncMock(return_value=thread),
    )
    evidence = make_message(message_id=12345, channel=alert_channel, guild=guild, author=rai)
    alert_channel.send.side_effect = [alert, evidence]
    messages = []
    for i, channel in enumerate(channels):
        attachment = make_attachment(
            attachment_id=200+i, filename=f'image{i}.png', content_type='image/png',
            read=AsyncMock(return_value=b'image'),
        )
        msg = make_message(
            message_id=300+i, author=member, channel=channel, guild=guild,
            attachments=[attachment], delete=AsyncMock(),
        )
        channel.fetch_message = AsyncMock(return_value=msg)
        messages.append(msg)
    bot = make_bot(guilds=[guild], db={'image_spam': {str(guild.id): {
        'enabled': True, 'channel': alert_channel.id, 'limit': 2, 'timeframe': 10,
    }}})
    cog = image_spam.ImageSpam(bot)
    cog.thread_to_image = AsyncMock(return_value=io.BytesIO(b'evidence'))
    auto_ban = AsyncMock(return_value=True)
    monkeypatch.setattr(image_spam.hf, 'auto_ban', auto_ban)
    monkeypatch.setattr(image_spam, 'EVIDENCE_DELAY_SECONDS', 0, raising=False)
    return SimpleNamespace(
        cog=cog, guild=guild, member=member, messages=messages, alert=alert,
        thread=thread, auto_ban=auto_ban, evidence=evidence,
    )


async def trigger(case):
    for message in case.messages:
        await case.cog.on_message(message)


def final_status(case):
    return case.alert.edit.await_args.kwargs['embed'].fields[0].value


@pytest.mark.asyncio
async def test_success_bans_once_and_confirms_result(spam_case):
    await trigger(spam_case)
    spam_case.auto_ban.assert_awaited_once_with(
        member=spam_case.member, evidence_msg=spam_case.evidence)
    assert final_status(spam_case) == '✅ Banned'
    spam_case.thread.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_thread_upload_does_not_strand_ban(spam_case):
    spam_case.thread.send.side_effect = http_error()
    await trigger(spam_case)
    spam_case.auto_ban.assert_awaited_once()
    assert final_status(spam_case) == '✅ Banned'
    spam_case.thread.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_ban_failure_is_visible_and_keeps_evidence(spam_case):
    spam_case.auto_ban.side_effect = http_error()
    await trigger(spam_case)
    assert 'failed' in final_status(spam_case).lower()
    assert '✅' not in final_status(spam_case)
    spam_case.thread.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_ban_permission_is_required(spam_case):
    spam_case.guild.me.guild_permissions.ban_members = False
    await trigger(spam_case)
    spam_case.auto_ban.assert_not_awaited()
    assert 'Ban Members' in final_status(spam_case)


@pytest.mark.asyncio
async def test_ban_does_not_require_timeout_permission(spam_case):
    spam_case.guild.me.guild_permissions.moderate_members = False
    await trigger(spam_case)
    spam_case.member.timeout.assert_not_awaited()
    spam_case.auto_ban.assert_awaited_once()
    assert 'was timed out' not in spam_case.alert.edit.await_args.kwargs['embed'].description


@pytest.mark.asyncio
async def test_stalled_evidence_has_a_deadline(spam_case, monkeypatch):
    async def never_finishes(*args, **kwargs):
        await asyncio.Event().wait()

    spam_case.cog.thread_to_image.side_effect = never_finishes
    monkeypatch.setattr(image_spam, 'EVIDENCE_TIMEOUT_SECONDS', 0.02, raising=False)
    await asyncio.wait_for(trigger(spam_case), 0.5)
    spam_case.auto_ban.assert_awaited_once()
    assert final_status(spam_case) == '✅ Banned'


@pytest.mark.asyncio
async def test_ban_timeout_is_unconfirmed_not_success(spam_case, monkeypatch):
    async def never_finishes(*args, **kwargs):
        await asyncio.Event().wait()

    spam_case.auto_ban.side_effect = never_finishes
    monkeypatch.setattr(image_spam, 'BAN_TIMEOUT_SECONDS', 0.02, raising=False)
    await asyncio.wait_for(trigger(spam_case), 0.5)
    assert 'unconfirmed' in final_status(spam_case).lower()
    spam_case.thread.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_failure_cannot_hide_confirmed_ban(spam_case):
    spam_case.thread.delete.side_effect = http_error()
    await trigger(spam_case)
    assert final_status(spam_case) == '✅ Banned'


@pytest.mark.asyncio
@pytest.mark.parametrize('target', ['owner', 'higher_role'])
async def test_unbannable_member_is_reported(spam_case, target):
    if target == 'owner':
        spam_case.guild.owner_id = spam_case.member.id
    else:
        spam_case.member.top_role = 11
    await trigger(spam_case)
    spam_case.auto_ban.assert_not_awaited()
    assert 'Not banned' in final_status(spam_case)


@pytest.mark.asyncio
async def test_overlapping_messages_only_ban_once(spam_case):
    started, finish = asyncio.Event(), asyncio.Event()

    async def evidence(*args):
        started.set()
        await finish.wait()
        return io.BytesIO(b'evidence')

    spam_case.cog.thread_to_image.side_effect = evidence
    await spam_case.cog.on_message(spam_case.messages[0])
    first = asyncio.create_task(spam_case.cog.on_message(spam_case.messages[1]))
    await asyncio.wait_for(started.wait(), 1)
    second = asyncio.create_task(spam_case.cog.on_message(spam_case.messages[1]))
    await asyncio.sleep(0)
    finish.set()
    await asyncio.wait_for(asyncio.gather(first, second), 1)
    spam_case.auto_ban.assert_awaited_once()


@pytest.mark.asyncio
async def test_alert_edit_failure_does_not_block_ban(spam_case):
    spam_case.alert.edit.side_effect = http_error()
    await trigger(spam_case)
    spam_case.auto_ban.assert_awaited_once()


@pytest.mark.asyncio
async def test_waiting_listener_rechecks_threshold_after_previous_incident(spam_case):
    key = (spam_case.guild.id, spam_case.member.id)
    lock = asyncio.Lock()
    await lock.acquire()
    spam_case.cog.active_alerts[key] = {'lock_user': lock, 'lock_alert': None}
    await spam_case.cog.on_message(spam_case.messages[0])
    waiting = asyncio.create_task(spam_case.cog.on_message(spam_case.messages[1]))
    await asyncio.sleep(0)
    # A completed incident consumes its messages; one fresh message is not spam.
    spam_case.cog.image_spam[key] = []
    await spam_case.cog.on_message(spam_case.messages[0])
    lock.release()
    await asyncio.wait_for(waiting, 1)
    spam_case.auto_ban.assert_not_awaited()
    spam_case.alert.edit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('reason', ['previous unrelated warning', hf.HACKED_ACCOUNT_BAN_REASON])
async def test_existing_modlog_does_not_prevent_new_ban(monkeypatch, reason):
    guild = make_guild()
    member = make_member(guild=guild, send=AsyncMock(), ban=AsyncMock())
    bot = make_bot(db={'modlog': {str(guild.id): {str(member.id): [
        {'type': 'Ban', 'reason': reason},
    ]}}})
    monkeypatch.setattr(hf.here, 'bot', bot)
    add_modlog = Mock()
    monkeypatch.setattr(hf, 'add_to_modlog', add_modlog)
    await hf.auto_ban(member)
    member.ban.assert_awaited_once()
    add_modlog.assert_called_once()


@pytest.mark.asyncio
async def test_dm_http_failure_does_not_prevent_ban(monkeypatch):
    guild = make_guild()
    member = make_member(guild=guild, send=AsyncMock(side_effect=http_error(500)), ban=AsyncMock())
    monkeypatch.setattr(hf.here, 'bot', make_bot(db={'modlog': {}}))
    monkeypatch.setattr(hf, 'add_to_modlog', Mock())
    await hf.auto_ban(member)
    member.ban.assert_awaited_once()


@pytest.mark.asyncio
async def test_stalled_dm_does_not_prevent_ban(monkeypatch):
    async def never_finishes(*args, **kwargs):
        await asyncio.Event().wait()

    guild = make_guild()
    member = make_member(guild=guild, send=AsyncMock(side_effect=never_finishes), ban=AsyncMock())
    monkeypatch.setattr(hf.here, 'bot', make_bot(db={'modlog': {}}))
    monkeypatch.setattr(hf, 'add_to_modlog', Mock())
    monkeypatch.setattr(hf, 'AUTO_BAN_DM_TIMEOUT_SECONDS', 0.02)
    await asyncio.wait_for(hf.auto_ban(member), 0.5)
    member.ban.assert_awaited_once()
