from pathlib import Path

import pytest

from tests.fakes import ScriptedRunner
from wtp.core.errors import WtpError
from wtp.detection.detect import (
    ProjectDetector,
    base_url_key,
    db_override_key,
    parse_vhost,
    pick_domain,
)

AGENDA_VHOST = """<VirtualHost *:80>
    ServerName agenda.local
    ServerAlias agenda.localhost
    DocumentRoot {root}/public
    <FilesMatch \\.php$>
        SetHandler "proxy:unix:/run/php/php8.1-fpm.sock|fcgi://localhost"
    </FilesMatch>
</VirtualHost>
"""


def test_parse_vhost_reads_names_root_and_php() -> None:
    info = parse_vhost(AGENDA_VHOST.format(root="/p/agenda"))
    assert info is not None
    assert info.server_names == ["agenda.local", "agenda.localhost"]
    assert (info.document_root, info.php_version) == (Path("/p/agenda/public"), "8.1")


def test_parse_vhost_without_document_root() -> None:
    assert parse_vhost("<VirtualHost *:80>\nServerName x\n</VirtualHost>") is None


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        (["agenda.local", "agenda.localhost"], "agenda.localhost"),
        (["portal-rh.local"], "portal-rh.localhost"),
        ([], "outserv-agenda.localhost"),
    ],
)
def test_pick_domain_prefers_localhost(names: list[str], expected: str) -> None:
    assert pick_domain(names, "outserv_agenda") == expected


def test_base_url_key_only_for_known_frameworks() -> None:
    assert base_url_key("app.baseURL = 'http://x/'\n") == "app.baseURL"
    assert base_url_key("APP_URL=http://x\n") == "APP_URL"
    assert base_url_key("SITE=http://x\n") is None


def test_db_override_key_from_codeigniter_default_group(tmp_path: Path) -> None:
    config = tmp_path / "app" / "Config"
    config.mkdir(parents=True)
    (config / "Database.php").write_text("public $defaultGroup = 'dbportal';\n")
    assert db_override_key(tmp_path, "") == "database.dbportal.database"
    assert db_override_key(tmp_path / "none", "DB_DATABASE=x\n") == "DB_DATABASE"
    assert db_override_key(tmp_path / "none", "") == ""


def _checkout(tmp_path: Path) -> Path:
    root = tmp_path / "Projects" / "outserv_agenda"
    (root / "public").mkdir(parents=True)
    (root / "writable").mkdir()
    (root / "app" / "Database" / "Migrations").mkdir(parents=True)
    (root / ".env").write_text("app.baseURL = 'http://agenda.localhost/'\n")
    sites = tmp_path / "sites-available"
    sites.mkdir()
    (sites / "agenda.local.conf").write_text(AGENDA_VHOST.format(root=root))
    (sites / "wtp-outserv_agenda-x.conf").write_text(AGENDA_VHOST.format(root=root / "x"))
    return root


def _runner(root: Path) -> ScriptedRunner:
    runner = ScriptedRunner()
    runner.reply("--git-common-dir", stdout=f"{root / '.git'}\n")
    runner.reply("symbolic-ref", stdout="origin/main\n")
    runner.reply(
        "--ignored", stdout="app/Config/Constants.php\napp/Config/App.php\n.env\nvendor/x.php\n"
    )
    return runner


def test_detect_builds_project_from_checkout_and_vhost(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    detector = ProjectDetector(_runner(root), tmp_path / "sites-available", tmp_path / "run")
    project = detector.detect(root / "app").project
    assert (project.key, project.main_checkout, project.domain) == (
        "outserv_agenda",
        root,
        "agenda.localhost",
    )
    assert (project.php_version, project.document_root, project.main_branch) == (
        "8.1",
        "public",
        "main",
    )
    assert project.base_url_key == "app.baseURL"
    assert project.copy_files == ("app/Config/App.php", "app/Config/Constants.php")


def test_detect_without_vhost_uses_newest_fpm_socket(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    (tmp_path / "sites-available" / "agenda.local.conf").unlink()
    run = tmp_path / "run"
    run.mkdir()
    for version in ("8.1", "8.4", "8.2"):
        (run / f"php{version}-fpm.sock").touch()
    found = ProjectDetector(_runner(root), tmp_path / "sites-available", run).detect(root)
    assert (found.project.php_version, found.project.domain) == ("8.4", "outserv-agenda.localhost")
    assert any("domínio" in note for note in found.notes)


def test_unknown_base_url_becomes_task_for_agent(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    (root / ".env").write_text("SITE_ADDRESS=http://agenda.localhost/\n")
    found = ProjectDetector(_runner(root), tmp_path / "sites-available", tmp_path).detect(root)
    assert found.project.base_url_key == ""
    assert "--base-url-key" in found.agent_tasks[0]
    assert "Só pergunte ao usuário se o código não mostrar" in found.agent_tasks[0]


def test_explicit_base_url_key_skips_question(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    (root / ".env").write_text("SITE_ADDRESS=http://agenda.localhost/\n")
    detector = ProjectDetector(_runner(root), tmp_path / "sites-available", tmp_path)
    found = detector.detect(root, base_url_key="SITE_ADDRESS")
    assert (found.project.base_url_key, found.agent_tasks) == ("SITE_ADDRESS", [])


def test_detect_outside_git_explains(tmp_path: Path) -> None:
    runner = ScriptedRunner()
    runner.reply("--git-common-dir", returncode=128)
    with pytest.raises(WtpError, match="não é um repositório git"):
        ProjectDetector(runner, tmp_path, tmp_path).detect(tmp_path)
