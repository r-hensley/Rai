import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock

from discord.ext.commands import Bot
import pytest

import Rai as rai_module
from cogs.utils.BotUtils.bot_control import send_request


@pytest.mark.skipif(os.name != 'posix', reason='Requires a Unix socket')
@pytest.mark.asyncio
async def test_rai_controls_a_real_cog_over_its_private_socket(monkeypatch, tmp_path):
    monkeypatch.setattr(rai_module, 'dir_path', str(tmp_path))
    monkeypatch.setattr(rai_module, 'INITIAL_EXTENSIONS', ('math',))
    monkeypatch.setattr(rai_module.utils, 'load_db', lambda bot, name: None)
    monkeypatch.setattr(rai_module.utils, 'setup', lambda **kwargs: None)
    monkeypatch.setattr(rai_module.hf, 'setup', lambda **kwargs: None)
    monkeypatch.setattr(rai_module, 'create_database_tables', AsyncMock())

    with TemporaryDirectory(prefix='rai-control-') as directory:
        path = Path(directory) / '.control' / 'control.sock'
        monkeypatch.setenv('RAI_CONTROL_SOCKET', str(path))
        bot = rai_module.Rai()
        async with bot:
            await bot.setup_hook()
            assert path.parent.stat().st_mode & 0o777 == 0o700
            assert path.stat().st_mode & 0o777 == 0o600
            assert await send_request(path, 'status', []) == {'ok': True, 'loaded': ['math']}

            previous_cog = bot.get_cog('Math')
            assert previous_cog is not None
            assert not (await send_request(path, 'reload', ['math', 'database']))['ok']
            assert bot.get_cog('Math') is previous_cog

            for action in ('reload', 'unload', 'load'):
                assert await send_request(path, action, ['math']) == {'ok': True, 'completed': ['math']}
                assert ('cogs.math' in bot.extensions) == (action != 'unload')
            assert bot.get_cog('Math') is not previous_cog

        assert not path.exists()


@pytest.mark.asyncio
async def test_web_admin_reload_restores_package_after_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(rai_module, 'dir_path', str(tmp_path))
    original_modules = {
        'web_admin': object(),
        'web_admin.public': object(),
        'web_admin_extra': object(),
        'cogs.web_admin': object(),
    }
    module_cache = original_modules.copy()
    monkeypatch.setattr(rai_module, 'sys', SimpleNamespace(modules=module_cache))
    monkeypatch.setattr(rai_module.Rai, 'extensions', {'cogs.web_admin': object()})

    async def fail_reload(_bot, name, *, package=None):
        assert name == 'cogs.web_admin'
        assert set(module_cache) == {'web_admin_extra', 'cogs.web_admin'}
        module_cache['web_admin.partial'] = object()
        raise RuntimeError('reload failed')

    monkeypatch.setattr(Bot, 'reload_extension', fail_reload)
    with pytest.raises(RuntimeError, match='reload failed'):
        await rai_module.Rai().reload_extension('cogs.web_admin')
    assert module_cache == original_modules


@pytest.mark.asyncio
async def test_reloading_interactions_syncs_the_new_cog(monkeypatch, tmp_path):
    monkeypatch.setattr(rai_module, 'dir_path', str(tmp_path))
    reload_cog = AsyncMock()
    monkeypatch.setattr(Bot, 'reload_extension', reload_cog)
    bot = rai_module.Rai()
    interactions = SimpleNamespace(sync_main=AsyncMock())
    monkeypatch.setattr(bot, 'get_cog', {'Interactions': interactions}.get)
    monkeypatch.setattr(bot, 'is_ready', lambda: True)

    await bot.reload_extension('cogs.interactions')

    reload_cog.assert_awaited_once_with('cogs.interactions', package=None)
    interactions.sync_main.assert_awaited_once_with()
