import pytest

from wtp.errors import WtpError
from wtp.validation import (
    ensure_db_name,
    ensure_domain,
    ensure_php_version,
    ensure_relative_path,
    ensure_safe_absolute,
    validate_branch,
)


@pytest.mark.parametrize(
    "branch", ["feat/x", "hotfix/select2-filtros-projetos", "test/agente-a_1.2"]
)
def test_validate_branch_accepts_usual_names(branch: str) -> None:
    assert validate_branch(branch) == branch


@pytest.mark.parametrize(
    "branch", ["-x", "--force", "a..b", "a b", "a/", "/a", "x.lock", "a//b", "a~1", "a:b", ""]
)
def test_validate_branch_rejects_option_like_and_invalid_refs(branch: str) -> None:
    # Regressão: "--force" chegava ao git worktree add como opção.
    with pytest.raises(WtpError, match="Branch inválida"):
        validate_branch(branch)


@pytest.mark.parametrize("value", ["app/Config/App.php", ".env", "public", "writable"])
def test_relative_path_accepts_paths_inside(value: str) -> None:
    assert ensure_relative_path(value, "copy_files") == value


@pytest.mark.parametrize("value", ["../x", "a/../../x", "/etc/passwd", "", "a\nb", "a b", "a'b"])
def test_relative_path_rejects_escape_and_odd_chars(value: str) -> None:
    with pytest.raises(WtpError, match="copy_files"):
        ensure_relative_path(value, "copy_files")


@pytest.mark.parametrize("value", ["agenda.localhost", "a-b.c.localhost"])
def test_domain_accepts_dns_names(value: str) -> None:
    assert ensure_domain(value) == value


@pytest.mark.parametrize("value", ["localhost", "a b.localhost", "x.localhost\nRedirect /", "-a.b"])
def test_domain_rejects_injection(value: str) -> None:
    # Regressão: domain entra cru no ServerName do vhost, que roda como root.
    with pytest.raises(WtpError, match="domain"):
        ensure_domain(value)


def test_php_version_format() -> None:
    assert ensure_php_version("8.1") == "8.1"
    with pytest.raises(WtpError, match="php_version"):
        ensure_php_version("8.1-fpm.sock|x")


def test_safe_absolute_rejects_quotes_and_spaces() -> None:
    with pytest.raises(WtpError, match="main_checkout"):
        ensure_safe_absolute("/home/nk/My Projects", "main_checkout")


def test_db_name_rejects_quote() -> None:
    assert ensure_db_name("CRMRAT_QA") == "CRMRAT_QA"
    with pytest.raises(WtpError, match="--db"):
        ensure_db_name("x'; DROP")
