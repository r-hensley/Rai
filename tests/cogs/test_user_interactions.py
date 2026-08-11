from types import SimpleNamespace
import sqlite3

import pytest

from cogs import database
from cogs.user_interactions import direct_mention_ids, reply_target, timestamp_ms
from tests.discord_fakes import make_member, make_message, make_message_reference


def test_direct_mention_ids_excludes_roles_and_deduplicates_users():
    assert direct_mention_ids("<@12345678901234567> <@!12345678901234567> <@&12345678901234567>") == {
        12345678901234567
    }


def test_reply_target_uses_resolved_message_before_cache():
    resolved_author = make_member(member_id=2)
    resolved_message = make_message(message_id=3, author=resolved_author)
    message = make_message(
        reference=make_message_reference(resolved=resolved_message),
    )

    assert reply_target(message, []) is resolved_author


def test_reply_target_falls_back_to_cached_message():
    cached_author = make_member(member_id=4)
    message = make_message(reference=make_message_reference(message_id=3))
    cached_messages = [make_message(message_id=3, author=cached_author)]

    assert reply_target(message, cached_messages) is cached_author


def test_timestamp_ms_preserves_milliseconds():
    assert timestamp_ms(SimpleNamespace(timestamp=lambda: 123.456)) == 123456


@pytest.mark.asyncio
async def test_social_interaction_batch_is_deduplicated(tmp_path, monkeypatch):
    database_path = tmp_path / "social.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(database_path))

    await database.create_social_interaction_tables()
    messages = [(1, 10, 20, 30, 40, 50, 60)]
    interactions = [(1, "reply", 31, 51, 61), (1, "mention", 32, 52, 62)]
    arrivals = [(10, 30, 50, 60, 70)]
    await database.store_social_interaction_batch(messages, interactions, arrivals)
    await database.store_social_interaction_batch(messages, interactions, arrivals)

    with sqlite3.connect(database_path) as db:
        message_count = db.execute("SELECT COUNT(*) FROM social_messages").fetchone()
        interaction_count = db.execute("SELECT COUNT(*) FROM social_interactions").fetchone()
        arrival_count = db.execute("SELECT COUNT(*) FROM member_arrivals").fetchone()

    assert message_count == (1,)
    assert interaction_count == (2,)
    assert arrival_count == (1,)
