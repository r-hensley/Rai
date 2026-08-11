from cogs.utils import helper_functions as hf
from tests.discord_fakes import make_bot, make_guild


def test_get_recent_language_message_links_returns_newest_cached_links_first():
    old_bot = hf.here.bot
    hf.here.bot = make_bot(
        stats={
            "123": {
                "messages": {
                    "20260514": {
                        "456": {
                            "lang_messages": {
                                "en": ["older-en-1", "older-en-2"],
                                "es": ["older-es-1"],
                            },
                        },
                    },
                    "20260515": {
                        "456": {
                            "lang_messages": {
                                "en": ["newer-en-1", "newer-en-2"],
                                "es": ["newer-es-1", "newer-es-2"],
                            },
                        },
                    },
                },
            },
        },
    )

    try:
        guild = make_guild(guild_id=123)

        assert hf.get_recent_language_message_links(456, guild, "en", 3) == [
            "newer-en-2",
            "newer-en-1",
            "older-en-2",
        ]
        assert hf.get_recent_language_message_links(456, guild, "es", 5) == [
            "newer-es-2",
            "newer-es-1",
            "older-es-1",
        ]
    finally:
        hf.here.bot = old_bot


def test_get_recent_language_message_links_handles_missing_cache():
    old_bot = hf.here.bot
    hf.here.bot = make_bot(
        stats={
            "123": {
                "messages": {
                    "20260515": {
                        "456": {"lang": {"en": 23}},
                    },
                },
            },
        },
    )

    try:
        guild = make_guild(guild_id=123)

        assert hf.get_recent_language_message_links(456, guild, "en", 5) == []
        assert hf.get_recent_language_message_links(456, guild, "es", 5) == []
    finally:
        hf.here.bot = old_bot
