from pathlib import Path

import pytest

from tests.fakes import Sandbox, make_sandbox
from wtp.actions.locate import locate
from wtp.core.errors import WtpError


def _git_answers(box: Sandbox, common: Path, top: Path) -> None:
    box.runner.reply("--git-common-dir", stdout=f"{common / '.git'}\n")
    box.runner.reply("--show-toplevel", stdout=f"{top}\n")


def test_locate_inside_wtp_worktree(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    worktree = tmp_path / "Projects" / "outserv_agenda-hotfix"
    _git_answers(box, box.project.main_checkout, worktree)
    found = locate(box.services, worktree / "app")
    assert (found.project, found.worktree, found.url) == ("outserv_agenda", "hotfix", None)


def test_locate_main_checkout_has_no_worktree_name(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    _git_answers(box, box.project.main_checkout, box.project.main_checkout)
    assert locate(box.services, box.project.main_checkout).worktree is None


def test_locate_outside_known_projects(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    box.runner.reply("--git-common-dir", returncode=128)
    with pytest.raises(WtpError, match="não pertence"):
        locate(box.services, tmp_path)
