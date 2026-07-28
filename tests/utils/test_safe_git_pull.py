import asyncio
import os
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from cogs.utils.BotUtils.git_utils import safe_git_pull


REPO_ROOT = Path(__file__).resolve().parents[2]


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed in {cwd}:\n"
            f"{result.stderr or result.stdout}"
        )
    return result.stdout.rstrip()


def initialize_repo(path: Path, *, bare: bool = False) -> None:
    path.mkdir()
    args = ["init", "--initial-branch=main"]
    if bare:
        args.append("--bare")
    git(path, *args)
    if not bare:
        git(path, "config", "user.email", "tests@example.com")
        git(path, "config", "user.name", "Rai Tests")


@dataclass
class GitWorld:
    child_source: Path
    parent_source: Path
    worktree: Path
    child_a: str
    child_b: str

    @property
    def child_worktree(self) -> Path:
        return self.worktree / "deps" / "child"


def build_git_world(root: Path) -> GitWorld:
    child_source = root / "child-source"
    child_remote = root / "child.git"
    initialize_repo(child_source)
    initialize_repo(child_remote, bare=True)

    (child_source / "lib.py").write_text("VERSION = 'a'\n", encoding="utf-8")
    git(child_source, "add", "lib.py")
    git(child_source, "commit", "-m", "child a")
    child_a = git(child_source, "rev-parse", "HEAD")
    git(child_source, "remote", "add", "origin", str(child_remote))
    git(child_source, "push", "--set-upstream", "origin", "main")

    parent_source = root / "parent-source"
    parent_remote = root / "parent.git"
    initialize_repo(parent_source)
    initialize_repo(parent_remote, bare=True)

    (parent_source / "app.py").write_text("VERSION = 'a'\n", encoding="utf-8")
    git(
        parent_source,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        str(child_remote),
        "deps/child",
    )
    shutil.copyfile(REPO_ROOT / ".gitignore", parent_source / ".gitignore")
    git(parent_source, "add", "app.py")
    git(parent_source, "add", "--force", ".gitignore")
    git(parent_source, "commit", "-m", "parent a")
    git(parent_source, "remote", "add", "origin", str(parent_remote))
    git(parent_source, "push", "--set-upstream", "origin", "main")

    worktree = root / "worktree"
    git(root, "clone", str(parent_remote), str(worktree))
    git(
        worktree,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "update",
        "--init",
        "--recursive",
    )

    (child_source / "lib.py").write_text("VERSION = 'b'\n", encoding="utf-8")
    git(child_source, "add", "lib.py")
    git(child_source, "commit", "-m", "child b")
    child_b = git(child_source, "rev-parse", "HEAD")
    git(child_source, "push", "origin", "main")

    return GitWorld(
        child_source=child_source,
        parent_source=parent_source,
        worktree=worktree,
        child_a=child_a,
        child_b=child_b,
    )


class SafeGitPullTests(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_git_allow_protocol = os.environ.get("GIT_ALLOW_PROTOCOL")
        os.environ["GIT_ALLOW_PROTOCOL"] = "file"
        self._temporary_directory = tempfile.TemporaryDirectory(prefix="rai-safe-pull-tests-")
        self.world = build_git_world(Path(self._temporary_directory.name))

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()
        if self._previous_git_allow_protocol is None:
            os.environ.pop("GIT_ALLOW_PROTOCOL", None)
        else:
            os.environ["GIT_ALLOW_PROTOCOL"] = self._previous_git_allow_protocol

    def test_ignored_sqlite_sidecars_do_not_block_pull(self) -> None:
        sidecars = (
            "database.db",
            "database.db-shm",
            "database.db-wal",
            "database.db-journal",
        )
        for filename in sidecars:
            (self.world.worktree / filename).write_text("runtime data", encoding="utf-8")
            git(self.world.worktree, "check-ignore", "--quiet", filename)

        self.assertEqual(git(self.world.worktree, "status", "--porcelain"), "")

        result = asyncio.run(safe_git_pull(cwd=str(self.world.worktree)))

        self.assertIn("Already up to date on main.", result)
        self.assertEqual(git(self.world.worktree, "status", "--porcelain"), "")
        self.assertTrue(
            all((self.world.worktree / filename).exists() for filename in sidecars)
        )

    def test_clean_submodule_mismatch_is_reconciled_when_parent_is_current(self) -> None:
        git(self.world.child_worktree, "fetch", "origin")
        git(self.world.child_worktree, "checkout", "--detach", self.world.child_b)

        self.assertEqual(git(self.world.child_worktree, "status", "--porcelain"), "")
        self.assertEqual(
            git(self.world.worktree, "status", "--porcelain"),
            " M deps/child",
        )
        parent_head = git(self.world.worktree, "rev-parse", "HEAD")

        asyncio.run(safe_git_pull(cwd=str(self.world.worktree)))

        self.assertEqual(git(self.world.worktree, "rev-parse", "HEAD"), parent_head)
        self.assertEqual(
            git(self.world.child_worktree, "rev-parse", "HEAD"),
            self.world.child_a,
        )
        self.assertEqual(git(self.world.worktree, "status", "--porcelain"), "")

    def test_clean_submodule_at_incoming_commit_does_not_block_pull(self) -> None:
        parent_child = self.world.parent_source / "deps" / "child"
        git(parent_child, "fetch", "origin")
        git(parent_child, "checkout", "--detach", self.world.child_b)
        git(self.world.parent_source, "add", "deps/child")
        git(self.world.parent_source, "commit", "-m", "pin child b")
        git(self.world.parent_source, "push", "origin", "main")

        git(self.world.child_worktree, "fetch", "origin")
        git(self.world.child_worktree, "checkout", "--detach", self.world.child_b)
        self.assertEqual(
            git(self.world.worktree, "status", "--porcelain"),
            " M deps/child",
        )

        asyncio.run(safe_git_pull(cwd=str(self.world.worktree)))

        self.assertEqual(
            git(self.world.child_worktree, "rev-parse", "HEAD"),
            self.world.child_b,
        )
        self.assertEqual(git(self.world.worktree, "status", "--porcelain"), "")

    def test_dirty_submodule_content_is_preserved_and_rejected(self) -> None:
        self._assert_dirty_submodule_is_preserved(force=False)

    def test_force_preserves_and_rejects_dirty_submodule_content(self) -> None:
        self._assert_dirty_submodule_is_preserved(force=True)

    def test_unreferenced_detached_submodule_commit_is_preserved_and_rejected(
            self) -> None:
        git(self.world.child_worktree, "config", "user.email", "tests@example.com")
        git(self.world.child_worktree, "config", "user.name", "Rai Tests")
        git(
            self.world.child_worktree,
            "commit",
            "--allow-empty",
            "-m",
            "local detached commit",
        )
        detached_commit = git(self.world.child_worktree, "rev-parse", "HEAD")
        self.assertEqual(
            git(
                self.world.child_worktree,
                "for-each-ref",
                "--format=%(refname)",
                "--contains",
                "HEAD",
            ),
            "",
        )

        with self.assertRaisesRegex(RuntimeError, "uncommitted or untracked changes"):
            asyncio.run(safe_git_pull(cwd=str(self.world.worktree)))

        self.assertEqual(
            git(self.world.child_worktree, "rev-parse", "HEAD"),
            detached_commit,
        )

    def test_staged_nested_submodule_gitlink_is_preserved_and_rejected(self) -> None:
        root = Path(self._temporary_directory.name)
        leaf_source = root / "leaf-source"
        leaf_remote = root / "leaf.git"
        initialize_repo(leaf_source)
        initialize_repo(leaf_remote, bare=True)

        (leaf_source / "leaf.py").write_text("VERSION = 'a'\n", encoding="utf-8")
        git(leaf_source, "add", "leaf.py")
        git(leaf_source, "commit", "-m", "leaf a")
        git(leaf_source, "remote", "add", "origin", str(leaf_remote))
        git(leaf_source, "push", "--set-upstream", "origin", "main")

        git(self.world.child_worktree, "config", "user.email", "tests@example.com")
        git(self.world.child_worktree, "config", "user.name", "Rai Tests")
        git(
            self.world.child_worktree,
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            str(leaf_remote),
            "deps/leaf",
        )
        git(self.world.child_worktree, "add", ".gitmodules", "deps/leaf")
        git(self.world.child_worktree, "commit", "-m", "add nested submodule")
        child_commit = git(self.world.child_worktree, "rev-parse", "HEAD")
        git(self.world.child_worktree, "branch", "protect-local-commit", child_commit)

        (leaf_source / "leaf.py").write_text("VERSION = 'b'\n", encoding="utf-8")
        git(leaf_source, "add", "leaf.py")
        git(leaf_source, "commit", "-m", "leaf b")
        leaf_b = git(leaf_source, "rev-parse", "HEAD")
        git(leaf_source, "push", "origin", "main")

        leaf_worktree = self.world.child_worktree / "deps" / "leaf"
        git(leaf_worktree, "fetch", "origin")
        git(leaf_worktree, "checkout", "--detach", leaf_b)
        git(self.world.child_worktree, "add", "deps/leaf")
        self.assertEqual(
            git(
                self.world.child_worktree,
                "diff",
                "--cached",
                "--name-only",
                "HEAD",
                "--",
            ),
            "deps/leaf",
        )

        with self.assertRaisesRegex(RuntimeError, "uncommitted or untracked changes"):
            asyncio.run(safe_git_pull(cwd=str(self.world.worktree)))

        self.assertEqual(
            git(self.world.child_worktree, "rev-parse", "HEAD"),
            child_commit,
        )
        self.assertEqual(git(leaf_worktree, "rev-parse", "HEAD"), leaf_b)
        self.assertEqual(
            git(
                self.world.child_worktree,
                "diff",
                "--cached",
                "--name-only",
                "HEAD",
                "--",
            ),
            "deps/leaf",
        )

    def _assert_dirty_submodule_is_preserved(self, *, force: bool) -> None:
        local_contents = "VERSION = 'local edit'\n"
        child_file = self.world.child_worktree / "lib.py"
        child_file.write_text(local_contents, encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "uncommitted or untracked changes"):
            asyncio.run(safe_git_pull(cwd=str(self.world.worktree), force=force))

        self.assertEqual(child_file.read_text(encoding="utf-8"), local_contents)
        self.assertEqual(
            git(self.world.child_worktree, "rev-parse", "HEAD"),
            self.world.child_a,
        )

    def test_force_resets_tracked_parent_changes(self) -> None:
        app_file = self.world.worktree / "app.py"
        app_file.write_text("VERSION = 'local edit'\n", encoding="utf-8")
        ignored_database = self.world.worktree / "database.db"
        ignored_database.write_text("runtime data\n", encoding="utf-8")

        asyncio.run(safe_git_pull(cwd=str(self.world.worktree), force=True))

        self.assertEqual(app_file.read_text(encoding="utf-8"), "VERSION = 'a'\n")
        self.assertEqual(ignored_database.read_text(encoding="utf-8"), "runtime data\n")
        self.assertEqual(git(self.world.worktree, "status", "--porcelain"), "")

    def test_force_preserves_and_rejects_untracked_parent_files(self) -> None:
        local_file = self.world.worktree / "local-note.md"
        local_file.write_text("keep me\n", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "uncommitted or untracked changes"):
            asyncio.run(safe_git_pull(cwd=str(self.world.worktree), force=True))

        self.assertEqual(local_file.read_text(encoding="utf-8"), "keep me\n")

    def test_force_preserves_ignored_files_that_obstruct_a_reset(self) -> None:
        tracked_path = self.world.worktree / "app.py"
        tracked_path.unlink()
        tracked_path.mkdir()
        ignored_database = tracked_path / "database.db"
        ignored_database.write_text("keep me\n", encoding="utf-8")
        self.assertEqual(
            git(self.world.worktree, "check-ignore", "--quiet", "app.py/database.db"),
            "",
        )

        with self.assertRaisesRegex(RuntimeError, "uncommitted or untracked changes"):
            asyncio.run(safe_git_pull(cwd=str(self.world.worktree), force=True))

        self.assertTrue(tracked_path.is_dir())
        self.assertEqual(ignored_database.read_text(encoding="utf-8"), "keep me\n")


if __name__ == "__main__":
    unittest.main()
