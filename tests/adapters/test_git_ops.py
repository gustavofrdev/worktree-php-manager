from pathlib import Path

from tests.fakes import ScriptedRunner
from wtp.adapters.git_ops import GitRepo, parse_worktree_porcelain

PORCELAIN = """worktree /p/main
HEAD aaa
branch refs/heads/main

worktree /p/main-x
HEAD bbb
detached
"""


def test_parse_worktree_porcelain_reads_branch_and_detached() -> None:
    entries = parse_worktree_porcelain(PORCELAIN)
    assert [(e.path, e.branch) for e in entries] == [
        (Path("/p/main"), "main"),
        (Path("/p/main-x"), ""),
    ]


def test_ahead_behind_reads_left_right_counts() -> None:
    runner = ScriptedRunner()
    runner.reply("rev-list", stdout="3\t5\n")
    assert GitRepo(runner, Path("/p")).ahead_behind(Path("/p/x"), "origin/main") == (5, 3)


def test_ahead_behind_is_none_without_base() -> None:
    runner = ScriptedRunner()
    runner.reply("rev-list", returncode=128)
    assert GitRepo(runner, Path("/p")).ahead_behind(Path("/p/x"), "origin/nope") is None


def test_delete_branch_uses_expected_sha_and_never_forces() -> None:
    runner = ScriptedRunner()
    runner.reply("rev-parse", "--verify", stdout="abc123\n")
    GitRepo(runner, Path("/p")).delete_branch_contained_in("wtp/x", "origin/main")
    assert runner.calls[-1][-4:] == ("update-ref", "-d", "refs/heads/wtp/x", "abc123")
    assert runner.count("-D") == 0


def test_files_added_since_merges_committed_and_untracked() -> None:
    runner = ScriptedRunner()
    runner.reply("diff", stdout="m/2.php\nm/1.php\n")
    runner.reply("ls-files", stdout="m/3.php\nm/1.php\n")
    added = GitRepo(runner, Path("/p")).files_added_since(Path("/p/x"), "origin/main", "m")
    assert added == ["m/1.php", "m/2.php", "m/3.php"]
