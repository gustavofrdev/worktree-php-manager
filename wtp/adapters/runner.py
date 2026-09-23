"""Execução de comandos externos, isolada para os testes trocarem por um falso."""

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from wtp.core.errors import WtpError

MISSING_BINARY_CODE = 127


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def output_text(self) -> str:
        """Saída de erro (ou a normal) para mensagens, cortada em 2000 caracteres.

        Exemplo:
            result.output_text()
        """
        return (self.stderr.strip() or self.stdout.strip())[-2000:]


class CommandRunner(Protocol):
    def run(self, args: Sequence[str], cwd: Path | None = None) -> CommandResult:
        """Roda um comando e devolve o resultado, sem levantar exceção.

        Exemplo:
            runner.run(["git", "status"])
        """
        ...


class SubprocessRunner:
    """Roda comandos de verdade, sempre capturando a saída e sem levantar exceção.

    Exemplo:
        SubprocessRunner().run(["git", "status"], cwd=Path("~/Projects/x"))
    """

    def run(self, args: Sequence[str], cwd: Path | None = None) -> CommandResult:
        """Roda de verdade; binário ausente vira código 127.

        Exemplo:
            SubprocessRunner().run(["true"]).ok  # True
        """
        try:
            done = subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            return CommandResult(
                tuple(args), MISSING_BINARY_CODE, stderr=f"{args[0]}: não encontrado"
            )
        return CommandResult(tuple(args), done.returncode, done.stdout, done.stderr)


def require_ok(result: CommandResult, action: str) -> CommandResult:
    """Transforma um comando que falhou num WtpError legível.

    Exemplo:
        require_ok(runner.run(["git", "fetch"]), "buscar o remoto")
    """
    if result.ok:
        return result
    raise WtpError(
        f"Não consegui {action}: {result.output_text()}",
        hint=f"Comando que falhou: {' '.join(result.args)}",
    )
