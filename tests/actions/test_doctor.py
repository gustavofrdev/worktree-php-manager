from pathlib import Path

from tests.fakes import CannedHttpProbe, Sandbox, make_sandbox
from wtp.actions.doctor import CheckStatus, Doctor
from wtp.actions.provision import NewOptions, provision
from wtp.adapters.http_probe import HttpReply

HOST = "hotfix.agenda.localhost"


def _ready(tmp_path: Path) -> Sandbox:
    box = make_sandbox(tmp_path)
    provision(box.services, box.services.target("outserv_agenda", "hotfix"), NewOptions())
    return box


def _statuses(box: Sandbox, probe: CannedHttpProbe) -> dict[str, CheckStatus]:
    results = Doctor(box.services, probe).check(box.services.target("outserv_agenda", "hotfix"))
    return {result.label: result.status for result in results}


def _login_probe(asset_host: str = HOST) -> CannedHttpProbe:
    page = f'<link href="http://{asset_host}/public/assets/css/app.css">'
    return CannedHttpProbe(
        {
            (HOST, "/"): HttpReply(307, f"http://{HOST}/acesso/login"),
            (HOST, "/acesso/login"): HttpReply(200, body=page),
            (HOST, "/public/assets/css/app.css"): HttpReply(200),
        }
    )


def test_ready_worktree_passes_everything_but_socket(tmp_path: Path) -> None:
    statuses = _statuses(_ready(tmp_path), _login_probe())
    assert statuses[".env e baseURL"] is CheckStatus.OK
    assert statuses["vhost"] is CheckStatus.OK
    assert statuses["vhost habilitado"] is CheckStatus.OK
    assert statuses["pastas graváveis"] is CheckStatus.OK
    assert statuses["HTTP"] is CheckStatus.OK
    assert statuses["assets"] is CheckStatus.OK


def test_assets_pointing_to_main_host_fail(tmp_path: Path) -> None:
    statuses = _statuses(_ready(tmp_path), _login_probe(asset_host="agenda.localhost"))
    assert statuses["assets"] is CheckStatus.FAIL


def test_wrong_base_url_fails(tmp_path: Path) -> None:
    box = _ready(tmp_path)
    env = tmp_path / "Projects" / "outserv_agenda-hotfix" / ".env"
    env.write_text(env.read_text().replace("hotfix.agenda", "agenda"))
    assert _statuses(box, _login_probe())[".env e baseURL"] is CheckStatus.FAIL


def test_missing_worktree_is_a_single_failure(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    results = Doctor(box.services, CannedHttpProbe()).check(
        box.services.target("outserv_agenda", "x")
    )
    assert [r.status for r in results] == [CheckStatus.FAIL]


def test_missing_local_file_fails(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path, copy_files=("app/Config/Constants.php",))
    provision(box.services, box.services.target("outserv_agenda", "hotfix"), NewOptions())
    statuses = _statuses(box, _login_probe())
    assert statuses["arquivos locais (copy_files)"] is CheckStatus.FAIL


def test_unknown_base_url_key_is_a_warning(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path, base_url_key="")
    provision(box.services, box.services.target("outserv_agenda", "hotfix"), NewOptions())
    assert _statuses(box, _login_probe())[".env e baseURL"] is CheckStatus.WARN


def test_laravel_config_cache_is_flagged(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path, framework="laravel")
    provision(box.services, box.services.target("outserv_agenda", "hotfix"), NewOptions())
    cache = tmp_path / "Projects" / "outserv_agenda-hotfix" / "bootstrap" / "cache" / "config.php"
    cache.parent.mkdir(parents=True)
    cache.write_text("<?php return [];")
    assert _statuses(box, _login_probe())["cache de config do Laravel"] is CheckStatus.WARN
