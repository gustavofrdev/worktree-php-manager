"""Saída para quem usa a CLI e confirmação de passos que exigem sudo."""

import sys
from dataclasses import dataclass, field
from typing import TextIO


@dataclass
class Console:
    """Fala com a pessoa. Em modo JSON, as mensagens vão para stderr.

    Exemplo:
        Console(assume_yes=True).confirm("Recarregar o Apache?")
    """

    assume_yes: bool = False
    quiet: bool = False
    out: TextIO = field(default_factory=lambda: sys.stderr)
    answer_source: TextIO = field(default_factory=lambda: sys.stdin)

    def info(self, message: str) -> None:
        """Mensagem de andamento; some com quiet.

        Exemplo:
            console.info("Buscando o origin...")
        """
        if not self.quiet:
            print(message, file=self.out)

    def warn(self, message: str) -> None:
        """Aviso que a pessoa precisa ler, sempre mostrado.

        Exemplo:
            console.warn("banco compartilhado")
        """
        print(f"aviso: {message}", file=self.out)

    def confirm(self, question: str) -> bool:
        """Pergunta sim ou não; sem terminal e sem --yes, responde não.

        Exemplo:
            console.confirm("Recarregar o Apache?")
        """
        if self.assume_yes:
            return True
        if not self.answer_source.isatty():
            self.warn(f"{question} Sem terminal para confirmar; rode de novo com --yes.")
            return False
        print(f"{question} [s/N] ", end="", file=self.out, flush=True)
        return self.answer_source.readline().strip().lower() in {"s", "sim", "y", "yes"}
