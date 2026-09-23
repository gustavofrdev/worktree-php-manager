"""Roda os scripts que vão para o sudo, com os comandos do Apache trocados por stubs."""

import os
import subprocess
from pathlib import Path

from wtp.adapters.apache import CONFIGTEST_FAILED, INSTALL_SCRIPT, REMOVE_SCRIPT, VHOST_MARKER

STUBS = {
    "a2ensite": 'ln -sf "../sites-available/$2.conf" "$WTP_TEST_ENABLED/$2.conf"',
    "a2dissite": 'rm -f "$WTP_TEST_ENABLED/$2.conf"',
    "apache2ctl": 'exit "${WTP_TEST_CONFIGTEST:-0}"',
    "systemctl": 'echo "$@" >> "$WTP_TEST_RELOADS"',
    # install -m 644 -o root -g root SRC DEST: sem root, só copia.
    "install": 'cp "$7" "$8"',
}


def _stub_bin(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in STUBS.items():
        script = bin_dir / name
        script.write_text(f"#!/bin/sh\n{body}\n")
        script.chmod(0o755)
    return bin_dir


def _run(tmp_path: Path, script: str, *args: str, configtest: int = 0) -> int:
    sites = tmp_path / "sites-available"
    enabled = tmp_path / "sites-enabled"
    sites.mkdir(exist_ok=True)
    enabled.mkdir(exist_ok=True)
    bin_dir = tmp_path / "bin" if (tmp_path / "bin").exists() else _stub_bin(tmp_path)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "WTP_TEST_ENABLED": str(enabled),
        "WTP_TEST_RELOADS": str(tmp_path / "reloads"),
        "WTP_TEST_CONFIGTEST": str(configtest),
    }
    done = subprocess.run(
        ["bash", "-c", script, "wtp", *args], env=env, capture_output=True, check=False
    )
    return done.returncode


def _staged(tmp_path: Path) -> str:
    staged = tmp_path / "staged.conf"
    staged.write_text(f"{VHOST_MARKER}\n<VirtualHost *:80>\n</VirtualHost>\n")
    return str(staged)


def test_install_then_remove_round_trip(tmp_path: Path) -> None:
    sites = str(tmp_path / "sites-available")
    assert _run(tmp_path, INSTALL_SCRIPT, _staged(tmp_path), "wtp-a-x", sites, VHOST_MARKER) == 0
    assert (tmp_path / "sites-enabled" / "wtp-a-x.conf").exists()
    assert _run(tmp_path, REMOVE_SCRIPT, "wtp-a-x", sites, VHOST_MARKER) == 0
    assert not (tmp_path / "sites-available" / "wtp-a-x.conf").exists()
    assert (tmp_path / "reloads").read_text().count("reload apache2") == 2


def test_scripts_refuse_names_outside_prefix(tmp_path: Path) -> None:
    # O guard do Python pode ser contornado; o script que roda como root confere de novo.
    sites = str(tmp_path / "sites-available")
    assert (
        _run(tmp_path, INSTALL_SCRIPT, _staged(tmp_path), "agenda.local", sites, VHOST_MARKER) == 4
    )
    assert _run(tmp_path, REMOVE_SCRIPT, "agenda.local", sites, VHOST_MARKER) == 4


def test_scripts_refuse_unmarked_file(tmp_path: Path) -> None:
    sites = tmp_path / "sites-available"
    sites.mkdir()
    foreign = sites / "wtp-a-x.conf"
    foreign.write_text("<VirtualHost *:80>\n")
    assert _run(tmp_path, REMOVE_SCRIPT, "wtp-a-x", str(sites), VHOST_MARKER) == 4
    assert (
        _run(tmp_path, INSTALL_SCRIPT, _staged(tmp_path), "wtp-a-x", str(sites), VHOST_MARKER) == 4
    )
    assert foreign.read_text() == "<VirtualHost *:80>\n"


def test_failed_configtest_undoes_new_file_and_skips_reload(tmp_path: Path) -> None:
    sites = str(tmp_path / "sites-available")
    code = _run(
        tmp_path, INSTALL_SCRIPT, _staged(tmp_path), "wtp-a-x", sites, VHOST_MARKER, configtest=1
    )
    assert code == CONFIGTEST_FAILED
    assert not (tmp_path / "sites-available" / "wtp-a-x.conf").exists()
    assert not (tmp_path / "sites-enabled" / "wtp-a-x.conf").exists()
    assert not (tmp_path / "reloads").exists()
