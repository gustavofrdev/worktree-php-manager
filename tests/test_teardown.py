from pathlib import Path

import pytest

from tests.fakes import Sandbox, make_sandbox
from wtp.errors import WtpError
from wtp.provision import NewOptions, provision
from wtp.teardown import TeardownReport, teardown


def _new(box: Sandbox, adopt: bool = False) -> None:
    provision(
        box.services, box.services.target("outserv_agenda", "hotfix"), NewOptions(adopt=adopt)
    )


def _rm(box: Sandbox, delete_branch: bool = False) -> TeardownReport:
    return teardown(box.services, box.services.target("outserv_agenda", "hotfix"), delete_branch)


def test_rm_undoes_everything_new_created(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    _new(box)
    _rm(box, delete_branch=True)
    assert not (tmp_path / "Projects" / "outserv_agenda-hotfix").exists()
    assert not box.services.apache.exists("wtp-outserv_agenda-hotfix")
    assert box.runner.count("--is-ancestor", "refs/heads/wtp/hotfix", "origin/main") == 1
    assert box.runner.count("update-ref", "-d", "refs/heads/wtp/hotfix", "0f99c7f") == 1
    assert box.services.manifests.load("outserv_agenda-hotfix") is None


def test_rm_keeps_branch_with_own_commits_and_can_be_rerun(tmp_path: Path) -> None:
    # Regressão: branch -d comparava com o HEAD do checkout principal, não com a base.
    box = make_sandbox(tmp_path)
    _new(box)
    box.git.unmerged.add("wtp/hotfix")
    with pytest.raises(WtpError, match="commits que origin/main não tem"):
        _rm(box, delete_branch=True)
    assert box.runner.count("update-ref") == 0
    assert box.services.manifests.load("outserv_agenda-hotfix") is not None
    _rm(box)
    assert box.services.manifests.load("outserv_agenda-hotfix") is None


def test_rm_refuses_dirty_worktree_and_keeps_everything(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    _new(box)
    box.git.dirty[tmp_path / "Projects" / "outserv_agenda-hotfix"] = [" M app/x.php"]
    with pytest.raises(WtpError, match="não commitadas"):
        _rm(box)
    assert box.services.apache.exists("wtp-outserv_agenda-hotfix")


def test_rm_on_adopted_worktree_keeps_worktree_and_branch(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    path = tmp_path / "Projects" / "outserv_agenda-hotfix"
    (path / "writable").mkdir(parents=True)
    box.git.worktrees[path] = "hotfix/select2"
    box.git.dirty[path] = [" M public/assets/js/x.js"]
    _new(box, adopt=True)
    report = _rm(box, delete_branch=True)
    assert path.exists() and not (path / ".env").exists()
    assert box.runner.count("branch", "-d") == 0
    assert "não foi criada pelo wtp" in report.warnings[0]


def test_rm_cleans_orphan_vhost_without_manifest(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    _new(box)
    box.services.manifests.delete("outserv_agenda-hotfix")
    _rm(box)
    assert not box.services.apache.exists("wtp-outserv_agenda-hotfix")


def test_rm_unknown_worktree_points_to_ls(tmp_path: Path) -> None:
    with pytest.raises(WtpError) as caught:
        _rm(make_sandbox(tmp_path))
    assert "wtp ls" in caught.value.hint


def test_rm_on_adopted_worktree_removes_copied_files(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path, copy_files=("app/Config/App.php",))
    source = box.project.main_checkout / "app" / "Config" / "App.php"
    source.parent.mkdir(parents=True)
    source.write_text("<?php\n")
    path = tmp_path / "Projects" / "outserv_agenda-hotfix"
    (path / "writable").mkdir(parents=True)
    box.git.worktrees[path] = "hotfix/select2"
    _new(box, adopt=True)
    assert (path / "app" / "Config" / "App.php").exists()
    _rm(box)
    assert not (path / "app" / "Config" / "App.php").exists()


def test_rm_never_deletes_outside_worktree_from_tampered_manifest(tmp_path: Path) -> None:
    # Regressão: copied_files vem do manifesto em disco; um "../" apagava fora do worktree.
    box = make_sandbox(tmp_path)
    path = tmp_path / "Projects" / "outserv_agenda-hotfix"
    (path / "writable").mkdir(parents=True)
    box.git.worktrees[path] = "hotfix/select2"
    _new(box, adopt=True)
    outside = tmp_path / "precioso.txt"
    outside.write_text("não apagar")
    manifest = box.services.manifests.load("outserv_agenda-hotfix")
    assert manifest is not None
    manifest.copied_files = ["../../precioso.txt"]
    box.services.manifests.save(manifest)
    report = _rm(box)
    assert outside.exists()
    assert "fora do worktree" in report.warnings[0]
