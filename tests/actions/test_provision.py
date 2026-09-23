from pathlib import Path

import pytest

from tests.fakes import Sandbox, make_sandbox
from wtp.actions.provision import NewOptions, ProvisionReport, provision
from wtp.adapters.permissions import GRANT_SCRIPT
from wtp.adapters.runner import CommandResult
from wtp.core.envfile import ENV_MARKER, read_env_value
from wtp.core.errors import WtpError


def _new(
    box: Sandbox,
    name: str = "hotfix",
    branch: str | None = None,
    db: str | None = None,
    adopt: bool = False,
) -> ProvisionReport:
    target = box.services.target("outserv_agenda", name)
    return provision(box.services, target, NewOptions(branch=branch, db=db, adopt=adopt))


def test_new_creates_worktree_env_vhost_and_manifest(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    _new(box)
    path = tmp_path / "Projects" / "outserv_agenda-hotfix"
    env = (path / ".env").read_text()
    assert env.startswith(ENV_MARKER)
    assert read_env_value(env, "app.baseURL") == "http://hotfix.agenda.localhost/"
    assert box.runner.count("worktree", "add", "--no-track", "-b", "wtp/hotfix") == 1
    assert box.runner.count("origin/main") == 1
    assert box.services.apache.is_enabled("wtp-outserv_agenda-hotfix")
    manifest = box.services.manifests.load("outserv_agenda-hotfix")
    assert manifest is not None and manifest.created_worktree and manifest.created_branch
    assert manifest.base_ref == "origin/main"


def test_new_twice_is_idempotent(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    _new(box)
    _new(box)
    assert box.runner.count("worktree", "add") == 1
    assert box.runner.count("sudo") == 1


def test_new_uses_existing_local_branch_without_owning_it(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    box.git.branches.add("feat/x")
    _new(box, branch="feat/x")
    manifest = box.services.manifests.load("outserv_agenda-hotfix")
    assert manifest is not None and not manifest.created_branch
    assert box.runner.count("worktree", "add", "-b") == 0


def test_new_on_unmanaged_worktree_suggests_adopt(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    path = tmp_path / "Projects" / "outserv_agenda-hotfix"
    path.mkdir()
    box.git.worktrees[path] = "hotfix/select2"
    with pytest.raises(WtpError) as caught:
        _new(box)
    assert "wtp adopt outserv_agenda hotfix" in caught.value.hint


def test_adopt_serves_existing_worktree_without_creating_it(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    path = tmp_path / "Projects" / "outserv_agenda-hotfix"
    (path / "writable").mkdir(parents=True)
    box.git.worktrees[path] = "hotfix/select2"
    _new(box, adopt=True)
    manifest = box.services.manifests.load("outserv_agenda-hotfix")
    assert manifest is not None and not manifest.created_worktree
    assert manifest.branch == "hotfix/select2" and manifest.created_env
    assert box.runner.count("worktree", "add") == 0


def test_declined_confirmation_changes_nothing(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path, assume_yes=False)
    with pytest.raises(WtpError, match="Parei antes"):
        _new(box)
    assert box.runner.count("worktree", "add") == 0
    assert "--yes" in box.console_output.getvalue()


def test_db_override_is_written_to_env(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    _new(box, db="AGENDA_X")
    env = (tmp_path / "Projects" / "outserv_agenda-hotfix" / ".env").read_text()
    assert read_env_value(env, "database.dbportal.database") == "AGENDA_X"


def test_new_migrations_trigger_shared_database_warning(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    box.runner.reply("--diff-filter=A", stdout="app/Database/Migrations/2026_x.php\n")
    report = _new(box)
    assert "banco é compartilhado" in report.warnings[0]


def test_composer_runs_only_when_vendor_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("wtp.adapters.composer.shutil.which", lambda _name: None)
    box = make_sandbox(tmp_path)
    path = tmp_path / "Projects" / "outserv_agenda-hotfix"
    (path / "writable").mkdir(parents=True)
    (path / "composer.json").write_text("{}")
    box.git.worktrees[path] = "hotfix/select2"
    _new(box, adopt=True)
    assert box.runner.count("composer", "install") == 1


def test_foreign_pool_user_gets_group_write(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path, pool_user="root")
    _new(box)
    assert box.runner.count(GRANT_SCRIPT, "wtp", "root") == 1


def test_local_config_files_are_copied_and_recorded(tmp_path: Path) -> None:
    # Regressão: app/Config/Constants.php é ignorado pelo git e o worktree dava HTTP 500.
    box = make_sandbox(tmp_path, copy_files=("app/Config/Constants.php",))
    source = box.project.main_checkout / "app" / "Config" / "Constants.php"
    source.parent.mkdir(parents=True)
    source.write_text("<?php define('DB', 'x');\n")
    _new(box)
    copied = tmp_path / "Projects" / "outserv_agenda-hotfix" / "app" / "Config" / "Constants.php"
    assert copied.read_text() == source.read_text()
    manifest = box.services.manifests.load("outserv_agenda-hotfix")
    assert manifest is not None and manifest.copied_files == ["app/Config/Constants.php"]


def test_missing_local_file_in_main_is_a_warning(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path, copy_files=("app/Config/Nope.php",))
    report = _new(box)
    assert "app/Config/Nope.php" in report.warnings[0]


def test_option_like_branch_is_rejected_before_git(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    with pytest.raises(WtpError, match="Branch inválida"):
        _new(box, branch="--force")
    assert box.runner.count("worktree", "add") == 0


def test_env_keeps_source_permissions(tmp_path: Path) -> None:
    # O .env tem credenciais: a cópia não pode ficar mais aberta que o original.
    box = make_sandbox(tmp_path)
    (box.project.main_checkout / ".env").chmod(0o600)
    _new(box)
    env = tmp_path / "Projects" / "outserv_agenda-hotfix" / ".env"
    assert env.stat().st_mode & 0o777 == 0o600


def test_project_without_base_url_key_asks_user_to_set_url(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path, base_url_key="")
    report = _new(box)
    env = (tmp_path / "Projects" / "outserv_agenda-hotfix" / ".env").read_text()
    assert "hotfix.agenda.localhost" not in env
    assert "http://hotfix.agenda.localhost/" in report.warnings[0]
    assert "URL base" in report.warnings[0]


def test_base_url_key_missing_from_main_env_is_reported(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    (box.project.main_checkout / ".env").write_text("CI_ENVIRONMENT = development\n")
    report = _new(box)
    assert any("não existia" in warning for warning in report.warnings)


def test_ensure_dirs_are_created_and_recorded(tmp_path: Path) -> None:
    box = make_sandbox(
        tmp_path, ensure_dirs=("storage/framework/views", "storage/framework/sessions")
    )
    _new(box)
    views = tmp_path / "Projects" / "outserv_agenda-hotfix" / "storage" / "framework" / "views"
    assert views.is_dir()
    manifest = box.services.manifests.load("outserv_agenda-hotfix")
    assert manifest is not None
    # storage/ não existia: é a pasta mais alta que o wtp criou.
    assert manifest.created_dirs == ["storage", "storage/framework/sessions"]


def test_composer_uses_project_php_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Regressão: o composer rodava com o php padrão da máquina, e o package:discover
    # do Laravel quebrava quando o projeto exige outra versão.
    monkeypatch.setattr("wtp.adapters.composer.shutil.which", lambda name: f"/usr/bin/{name}")
    box = make_sandbox(tmp_path)
    path = tmp_path / "Projects" / "outserv_agenda-hotfix"
    (path / "writable").mkdir(parents=True)
    (path / "composer.json").write_text("{}")
    box.git.worktrees[path] = "hotfix/select2"
    _new(box, adopt=True)
    assert box.runner.count("/usr/bin/php8.1", "/usr/bin/composer", "install") == 1


def test_ensure_dirs_exist_before_composer_runs(tmp_path: Path) -> None:
    # Regressão: o package:discover do Laravel, que roda dentro do composer install,
    # falhava com "Please provide a valid cache path" porque storage/framework/views
    # só era criado depois do composer.
    box = make_sandbox(tmp_path, ensure_dirs=("storage/framework/views",))
    path = tmp_path / "Projects" / "outserv_agenda-hotfix"
    (path / "writable").mkdir(parents=True)
    (path / "composer.json").write_text("{}")
    box.git.worktrees[path] = "hotfix/select2"
    seen: list[bool] = []

    def composer(args: tuple[str, ...], _cwd: Path | None) -> CommandResult:
        seen.append((path / "storage" / "framework" / "views").is_dir())
        return CommandResult(args, 0)

    box.runner.on("install", "--no-interaction", effect=composer)
    _new(box, adopt=True)
    assert seen == [True]


def test_interrupted_composer_runs_again(tmp_path: Path) -> None:
    # Regressão: um composer install que falhou deixava vendor/ pela metade, e o
    # próximo wtp new pulava o composer porque vendor/ já existia.
    box = make_sandbox(tmp_path)
    path = tmp_path / "Projects" / "outserv_agenda-hotfix"
    (path / "writable").mkdir(parents=True)
    (path / "composer.json").write_text("{}")
    box.git.worktrees[path] = "hotfix/select2"

    def broken(args: tuple[str, ...], _cwd: Path | None) -> CommandResult:
        (path / "vendor").mkdir(exist_ok=True)
        return CommandResult(args, 1, "", "package:discover falhou")

    box.runner.on("install", "--no-interaction", effect=broken)
    with pytest.raises(WtpError, match="composer install"):
        _new(box, adopt=True)
    box.runner.reply("install", "--no-interaction")
    _new(box, adopt=True)
    assert box.runner.count("install", "--no-interaction") == 2
