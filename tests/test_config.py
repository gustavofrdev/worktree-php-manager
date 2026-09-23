from pathlib import Path

import pytest

from wtp.config import load_config
from wtp.errors import WtpError

EXAMPLE = Path(__file__).parent.parent / "config.example.toml"


def test_example_config_loads() -> None:
    config = load_config(EXAMPLE)
    project = config.project("outserv_agenda")
    assert project.domain == "agenda.localhost"
    assert project.main_checkout.is_absolute()
    assert project.db_override_key == "database.dbportal.database"


def test_missing_required_keys_are_reported(tmp_path: Path) -> None:
    file = tmp_path / "c.toml"
    file.write_text('[projects.x]\ndomain = "x.localhost"\n')
    with pytest.raises(WtpError, match="main_checkout, php_version"):
        load_config(file)


def test_unknown_keys_are_reported(tmp_path: Path) -> None:
    file = tmp_path / "c.toml"
    file.write_text(
        '[projects.x]\nmain_checkout="/a"\ndomain="x.localhost"\nphp_version="8.1"\nphp="x"\n'
    )
    with pytest.raises(WtpError, match="desconhecidas: php"):
        load_config(file)


def test_unknown_project_lists_known_ones() -> None:
    with pytest.raises(WtpError, match="Projetos conhecidos: outserv_agenda"):
        load_config(EXAMPLE).project("nope")


def test_missing_file_gives_hint(tmp_path: Path) -> None:
    with pytest.raises(WtpError) as caught:
        load_config(tmp_path / "none.toml")
    assert "config.example.toml" in caught.value.hint


def test_copy_files_is_read_as_tuple() -> None:
    project = load_config(EXAMPLE).project("outserv_agenda")
    assert project.copy_files == ("app/Config/App.php", "app/Config/Constants.php")


def test_copy_files_must_be_a_list_of_strings(tmp_path: Path) -> None:
    file = tmp_path / "c.toml"
    file.write_text(
        '[projects.x]\nmain_checkout="/a"\ndomain="x.localhost"\nphp_version="8.1"\ncopy_files="a"\n'
    )
    with pytest.raises(WtpError, match="copy_files"):
        load_config(file)


def _write(tmp_path: Path, extra: str) -> Path:
    file = tmp_path / "c.toml"
    file.write_text(
        f'[projects.x]\nmain_checkout="/a"\ndomain="x.localhost"\nphp_version="8.1"\n{extra}\n'
    )
    return file


def test_php_version_must_be_text(tmp_path: Path) -> None:
    # Regressão: php_version = 8.10 (número) virava "8.1" sem aviso.
    with pytest.raises(WtpError, match="php_version"):
        load_config(_number_version(tmp_path))


def _number_version(tmp_path: Path) -> Path:
    file = tmp_path / "n.toml"
    file.write_text('[projects.x]\nmain_checkout="/a"\ndomain="x.localhost"\nphp_version=8.10\n')
    return file


def test_copy_files_cannot_escape_worktree(tmp_path: Path) -> None:
    with pytest.raises(WtpError, match="copy_files"):
        load_config(_write(tmp_path, 'copy_files = ["../../.ssh/id_rsa"]'))


def test_writable_dir_cannot_escape_worktree(tmp_path: Path) -> None:
    # Regressão: writable_dir vai para um chgrp -R com sudo.
    with pytest.raises(WtpError, match="writable_dir"):
        load_config(_write(tmp_path, 'writable_dir = "../.."'))
