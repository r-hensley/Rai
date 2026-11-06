"""Git revisions of the code loaded by Rai, including partial cog reloads."""
from contextlib import asynccontextmanager
import asyncio
import json
from pathlib import Path
import subprocess
import sys
from types import CodeType


BOTUTILS = "cogs/utils/BotUtils/"
REPORTER = BOTUTILS + "bot_utils.py"
STAMP = "__rai_traceback_revision__"


def _module_code(module):
    # An in-place reload keeps the globals dict of older, still-running functions.
    # Only attribute a frame to the new SHA if its code matches the reloaded module.
    try:
        root = module.__spec__.loader.get_code(module.__name__)
    except (AttributeError, ImportError, OSError, SyntaxError):
        return set()
    pending = [root] if root is not None else []
    codes = set()
    while pending:
        code = pending.pop()
        codes.add(code)
        pending.extend(const for const in code.co_consts if isinstance(const, CodeType))
    return codes


def _revision(repo):
    try:
        # Check the toplevel too: a missing submodule can resolve to its parent.
        top, head = subprocess.check_output(
            ["git", "-C", repo, "rev-parse", "--show-toplevel", "HEAD"],
            text=True, stderr=subprocess.DEVNULL, timeout=3,
        ).splitlines()
        if Path(top).resolve() == repo:
            changes = subprocess.check_output(
                ["git", "--no-optional-locks", "-C", repo, "status", "--porcelain",
                 "--untracked-files=all", "--ignore-submodules=all", "--", "*.py"],
                stderr=subprocess.DEVNULL, timeout=3,
            )
            if not changes:
                return head
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


def _modules(root):
    result = {}
    for name, module in sys.modules.copy().items():
        if name in ("Rai", "__main__") or name.startswith(("cogs.", "web_admin.")) or name == "web_admin":
            path = Path(getattr(module, "__file__", None) or "")
            if path.is_relative_to(root):
                # discord.py replaces the module; importlib.reload replaces its spec.
                result[path.relative_to(root).as_posix()] = (module, module.__spec__)
    return result


class LoadedRevisions:
    def __init__(self, root):
        self.root = root
        self.base = self.heads()
        self.reporter = self.base[1]
        self.pending = 0

    def heads(self):
        return _revision(self.root), _revision(self.root / BOTUTILS)

    @asynccontextmanager
    async def loading(self):
        heads = await asyncio.to_thread(self.heads)
        before = _modules(self.root)
        self.pending += 1
        succeeded = False
        try:
            yield
            succeeded = True
        finally:
            try:
                after = _modules(self.root)
                final_heads = await asyncio.to_thread(self.heads)
                for path, (module, spec) in after.items():
                    old = before.get(path)
                    in_place = old is not None and module is old[0]
                    if in_place and spec is old[1]:
                        continue
                    repo = int(path.startswith(BOTUTILS))
                    revision = heads[repo] if succeeded and heads[repo] == final_heads[repo] else None
                    codes = _module_code(module) if in_place and revision is not None else None
                    setattr(module, STAMP, (revision, codes))
                    if path == REPORTER:
                        self.reporter = revision
            finally:
                self.pending -= 1

    def snapshot(self):
        if self.pending:
            return None
        return self.base, self.reporter


def frame_revision(frame, file, snapshot):
    if snapshot is None:
        return None
    base, _ = snapshot
    revision, codes = frame.f_globals.get(STAMP, (base[int(file.startswith(BOTUTILS))], None))
    return revision if codes is None or frame.f_code in codes else None


def event_revisions(versions, snapshot):
    if snapshot is None:
        return None, None, None
    base, reporter = snapshot
    # Stacks are visited outermost first, then their chained causes. Prefer the
    # innermost affected file for each repo and retain any mixed-version frames.
    frames = dict.fromkeys(reversed(versions))
    rai = next((rev for file, rev in frames if not file.startswith(BOTUTILS)), base[0])
    botutils = next((rev for file, rev in frames if file.startswith(BOTUTILS)), reporter)
    mixed = [(file, rev) for file, rev in frames if rev != (botutils if file.startswith(BOTUTILS) else rai)]
    return rai, botutils, json.dumps(mixed) if mixed else None
