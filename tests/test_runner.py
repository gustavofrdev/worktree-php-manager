import pytest

from wtp.errors import WtpError
from wtp.runner import MISSING_BINARY_CODE, CommandResult, SubprocessRunner, require_ok


def test_subprocess_runner_captures_output() -> None:
    result = SubprocessRunner().run(["sh", "-c", "echo oi; echo erro >&2; exit 3"])
    assert (result.returncode, result.stdout, result.stderr) == (3, "oi\n", "erro\n")


def test_missing_binary_becomes_result_not_exception() -> None:
    result = SubprocessRunner().run(["wtp-comando-que-nao-existe"])
    assert result.returncode == MISSING_BINARY_CODE and "não encontrado" in result.stderr


def test_require_ok_explains_failure_with_command() -> None:
    failed = CommandResult(("git", "fetch"), 128, "", "fatal: sem rede")
    with pytest.raises(WtpError, match="Não consegui buscar: fatal: sem rede") as caught:
        require_ok(failed, "buscar")
    assert caught.value.hint == "Comando que falhou: git fetch"
