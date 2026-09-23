from pathlib import Path

import pytest

from tests.fakes import make_sandbox
from wtp.adapters.apache import VHOST_MARKER, render_vhost
from wtp.core.errors import WtpError


def test_render_vhost_follows_reference_template(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    target = box.services.target("outserv_agenda", "hotfix")
    text = render_vhost(target)
    assert text.splitlines()[0] == VHOST_MARKER
    assert "ServerName hotfix.agenda.localhost" in text
    assert f"DocumentRoot {target.path}/public" in text
    assert "proxy:unix:/run/php/php8.1-fpm.sock|fcgi://localhost" in text
    assert "${APACHE_LOG_DIR}/hotfix.agenda.localhost-error.log" in text


def test_install_uses_a_single_sudo_call(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    target = box.services.target("outserv_agenda", "hotfix")
    box.services.apache.install(target)
    assert box.runner.count("sudo") == 1
    assert box.services.apache.is_ours(target.vhost_name)
    assert box.services.apache.is_enabled(target.vhost_name)


def test_configtest_failure_is_reported_without_reload(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    box.apache.configtest_ok = False
    with pytest.raises(WtpError, match="configtest falhou"):
        box.services.apache.install(box.services.target("outserv_agenda", "hotfix"))
    assert not box.services.apache.exists("wtp-outserv_agenda-hotfix")


def test_refuses_names_without_prefix(tmp_path: Path) -> None:
    with pytest.raises(WtpError, match="só mexe em wtp-"):
        make_sandbox(tmp_path).services.apache.remove("agenda.local")


def test_refuses_unmarked_file_with_our_prefix(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    (box.apache.paths.sites_available / "wtp-outserv_agenda-x.conf").write_text("<VirtualHost>\n")
    with pytest.raises(WtpError, match="não tem a marca"):
        box.services.apache.remove("wtp-outserv_agenda-x")
    assert box.runner.count("sudo") == 0
