import re

import discord


BLACKLIST_CHANNEL_ID = 533863928263082014
BANS_CHANNEL_ID = 329576845949534208
VOTE_CUSTOM_ID = 'rai:gbl:vote'
VOTES_REQUIRED = 3


def vote_view():
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label='Vote to blacklist', style=discord.ButtonStyle.primary,
                                    custom_id=VOTE_CUSTOM_ID))
    # on_interaction handles this custom ID. Keep this view out of discord.py's per-message store.
    view.stop()
    return view


def entry_user_id(embed):
    for field in embed.fields:
        if field.name == 'Account ID':
            return field.value.strip('`') if re.fullmatch(r'`[0-9]{17,22}`', field.value) else None
    legacy_title = re.match(r'([0-9]{17,22}) .* \(\d+ votes?\)$', embed.title or '')
    return legacy_title[1] if legacy_title else None


def set_vote_status(embed, count):
    complete = count >= VOTES_REQUIRED
    status = 'Blacklisted' if complete else 'Voting open'
    embed.description = f'**{status} · {count}/{VOTES_REQUIRED} servers**'
    embed.colour = 0xDD2E44 if complete else 0xF0B232
