import tomllib
from pathlib import Path

import pytest

from tests.fakes import make_project
from wtp.core.config import load_config
from wtp.core.errors import WtpError
from wtp.detection.config_writer import add_project, render_project


def test_render_project_round_trips_through_load_config(tmp_path: Path) -> None:
    project = make_project(tmp_path / "outserv_agenda", ("app/Config/App.php",))
    file = tmp_path / "config.toml"
    add_project(file, project, tmp_path)
    loaded = load_config(file).project("outserv_agenda")
    assert loaded == project


def test_add_project_appends_without_touching_existing(tmp_path: Path) -> None:
    file = tmp_path / "config.toml"
    add_project(file, make_project(tmp_path / "a"), tmp_path)
    before = file.read_text()
    other = make_project(tmp_path / "b").__class__(
        key="produto_main",
        main_checkout=tmp_path / "b",
        domain="produto.localhost",
        php_version="8.4",
    )
    add_project(file, other, tmp_path)
    assert file.read_text().startswith(before)
    assert set(tomllib.loads(file.read_text())["projects"]) == {"outserv_agenda", "produto_main"}


def test_add_project_refuses_existing_key(tmp_path: Path) -> None:
    file = tmp_path / "config.toml"
    add_project(file, make_project(tmp_path / "a"), tmp_path)
    with pytest.raises(WtpError, match="já está"):
        add_project(file, make_project(tmp_path / "a"), tmp_path)


def test_render_escapes_strings() -> None:
    text = render_project(make_project(Path('/p/a"b')))
    assert 'main_checkout = "/p/a\\"b"' in text
