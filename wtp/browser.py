"""Abre uma URL no navegador do Windows a partir do WSL."""

import shutil

from wtp.errors import WtpError
from wtp.runner import CommandRunner

# explorer.exe devolve código 1 mesmo quando abre a URL, então o código não é conferido.
LAUNCHERS = ("wslview", "explorer.exe", "xdg-open")


class BrowserLauncher:
    """Escolhe o primeiro lançador disponível no PATH.

    Exemplo:
        BrowserLauncher(SubprocessRunner()).open("http://hotfix.agenda.localhost/")
    """

    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def open(self, url: str) -> str:
        """Abre a URL e diz qual lançador usou.

        Exemplo:
            launcher.open("http://x.agenda.localhost/")  # 'explorer.exe'
        """
        for launcher in LAUNCHERS:
            if shutil.which(launcher):
                self.runner.run([launcher, url])
                return launcher
        raise WtpError(
            f"Não achei como abrir {url}: nenhum de {', '.join(LAUNCHERS)} está no PATH.",
            hint="Abra a URL à mão no navegador.",
        )
