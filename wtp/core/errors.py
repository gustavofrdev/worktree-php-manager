"""Erros esperados, que a CLI mostra sem traceback."""


class WtpError(Exception):
    """Falha que a pessoa consegue resolver sozinha.

    Exemplo:
        raise WtpError("Projeto 'x' não existe.", hint="Veja ~/.config/wtp/config.toml")
    """

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
