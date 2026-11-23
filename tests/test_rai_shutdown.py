import asyncio
import json
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import Rai as rai_module
from cogs.background import Background


@pytest.fixture
def local_state(monkeypatch, tmp_path):
    utils = rai_module.utils
    monkeypatch.setattr(rai_module, 'dir_path', str(tmp_path))
    monkeypatch.setattr(utils, 'dir_path', str(tmp_path))
    monkeypatch.setattr(utils, '_lock', asyncio.Lock())
    monkeypatch.setattr(utils, 'here', SimpleNamespace(bot=None))
    monkeypatch.setattr(utils, 'setup', lambda bot, loop: setattr(utils.here, 'bot', bot))
    monkeypatch.setattr(rai_module.hf, 'setup', lambda **kwargs: None)
    monkeypatch.setattr(rai_module, 'INITIAL_EXTENSIONS', ())
    monkeypatch.setattr(rai_module, 'create_database_tables', AsyncMock())
    monkeypatch.delenv('RAI_CONTROL_SOCKET', raising=False)

    for name, data in {'db': {'pending': 'old'}, 'stats': {'count': 1}, 'message_queue': []}.items():
        (tmp_path / f'{name}.json').write_text(json.dumps(data), encoding='utf-8')
    return tmp_path


@pytest.mark.asyncio
async def test_close_waits_for_cancelled_autosave_and_writes_latest_state(local_state, monkeypatch):
    bot = rai_module.Rai()
    utils = rai_module.utils
    loop = asyncio.get_running_loop()
    writing = asyncio.Event()
    release_write = Event()
    discord_closing = asyncio.Event()
    control_close = AsyncMock()
    bot.control = SimpleNamespace(close=control_close)
    write_json = utils._write_json_dump
    writes = []

    def record_write(name, data):
        if name == 'db' and data['pending'] == 'old':
            loop.call_soon_threadsafe(writing.set)
            if not release_write.wait(5):
                raise TimeoutError('Test did not release autosave')
        write_json(name, data)
        writes.append(name)

    async def close_http():
        discord_closing.set()

    monkeypatch.setattr(utils, '_write_json_dump', record_write)
    monkeypatch.setattr(bot.http, 'close', close_http)
    await bot.__aenter__()
    await bot.setup_hook()
    background = Background.__new__(Background)
    background.bot = bot
    bot.bg_tasks = {background.save_db}
    bot.running_tasks = [background.save_db]
    await bot.add_cog(background)
    autosave = background.save_db.start()

    try:
        await asyncio.wait_for(writing.wait(), 5)
        bot.db['pending'] = 'new'
        bot.stats['count'] = 2
        bot.message_queue.append(rai_module.hf.MiniMessage(1, 'pending message', 2, 3, 4))

        first_close = asyncio.create_task(bot.close())
        await asyncio.wait_for(discord_closing.wait(), 5)
        await bot._closing_task
        assert autosave.cancelled()
        context_exit = asyncio.create_task(bot.__aexit__(None, None, None))
        await asyncio.sleep(0)
        assert not first_close.done()
        assert not context_exit.done()
    finally:
        release_write.set()

    await asyncio.wait_for(asyncio.gather(first_close, context_exit), 5)
    await bot.close()
    control_close.assert_awaited_once()
    assert writes == ['db', 'db', 'stats', 'message_queue']

    reloaded = SimpleNamespace()
    for name in rai_module.JSON_STATE:
        assert utils.load_db(reloaded, name)
    assert reloaded.db == {'pending': 'new'}
    assert reloaded.stats == {'count': 2}
    assert [message.content for message in reloaded.message_queue] == ['pending message']


@pytest.mark.asyncio
@pytest.mark.parametrize('startup', ['before_load', 'load_failed', 'placeholder'])
async def test_incomplete_json_load_leaves_disk_untouched(local_state, startup):
    stats = local_state / 'stats.json'
    if startup == 'load_failed':
        stats.write_text('{broken', encoding='utf-8')
    elif startup == 'placeholder':
        stats.write_text('', encoding='utf-8')
    before = {path: path.read_bytes() for path in local_state.glob('*.json')}

    async with rai_module.Rai() as bot:
        if startup == 'load_failed':
            with pytest.raises(json.JSONDecodeError):
                await bot.setup_hook()
        elif startup == 'placeholder':
            await bot.setup_hook()

    assert bot.is_closed()
    assert {path: path.read_bytes() for path in local_state.glob('*.json')} == before


@pytest.mark.asyncio
async def test_close_logs_write_failure_and_saves_other_files(local_state, caplog, monkeypatch):
    bot = rai_module.Rai()
    control_close = AsyncMock()
    discord_close = AsyncMock()
    bot.control = SimpleNamespace(close=control_close)
    monkeypatch.setattr(bot.http, 'close', discord_close)

    async with bot:
        await bot.setup_hook()
        bot.db['pending'] = object()
        bot.stats['count'] = 2
        bot.message_queue.append(rai_module.hf.MiniMessage(1, 'pending message', 2, 3, 4))

    control_close.assert_awaited_once()
    discord_close.assert_awaited_once()
    assert 'Could not save db.json during shutdown' in caplog.text
    assert json.loads((local_state / 'db.json').read_text()) == {'pending': 'old'}
    assert json.loads((local_state / 'stats.json').read_text()) == {'count': 2}
    assert json.loads((local_state / 'message_queue.json').read_text())[0]['content'] == 'pending message'
