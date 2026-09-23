from wtp.core.envfile import (
    ENV_MARKER,
    build_worktree_env,
    is_wtp_env,
    read_env_value,
    set_env_value,
)

MAIN_ENV = "CI_ENVIRONMENT = development\n# app.baseURL = 'old'\napp.baseURL = 'http://agenda.localhost/'\n"


def test_set_env_value_replaces_active_line_only() -> None:
    result = set_env_value(MAIN_ENV, "app.baseURL", "http://x.agenda.localhost/")
    assert "# app.baseURL = 'old'" in result
    assert "app.baseURL = 'http://x.agenda.localhost/'" in result
    assert "http://agenda.localhost/" not in result


def test_set_env_value_appends_missing_key() -> None:
    result = set_env_value("A = 1", "database.dbportal.database", "TEST")
    assert result == "A = 1\ndatabase.dbportal.database = 'TEST'\n"


def test_read_env_value_strips_quotes_and_ignores_comments() -> None:
    assert read_env_value(MAIN_ENV, "app.baseURL") == "http://agenda.localhost/"
    assert read_env_value(MAIN_ENV, "missing") is None


def test_build_worktree_env_marks_file_and_is_idempotent() -> None:
    overrides = {"app.baseURL": "http://x.agenda.localhost/"}
    once = build_worktree_env(MAIN_ENV, overrides)
    assert once.startswith(ENV_MARKER) and is_wtp_env(once)
    assert build_worktree_env(once, overrides) == once


def test_set_env_value_keeps_laravel_plain_style() -> None:
    # Regressão: APP_URL=x virava APP_URL = 'x', fora do estilo do arquivo.
    text = "APP_NAME=Portal\nAPP_URL=http://localhost:8443\n"
    result = set_env_value(text, "APP_URL", "http://x.produto-main.localhost/")
    assert result == "APP_NAME=Portal\nAPP_URL=http://x.produto-main.localhost/\n"


def test_set_env_value_keeps_double_quotes() -> None:
    assert set_env_value('APP_URL="a"\n', "APP_URL", "b") == 'APP_URL="b"\n'


def test_appended_key_follows_file_style() -> None:
    assert set_env_value("A=1\nB=2\n", "DB_DATABASE", "X") == "A=1\nB=2\nDB_DATABASE=X\n"
    assert set_env_value("a = '1'\n", "b.c", "X") == "a = '1'\nb.c = 'X'\n"
