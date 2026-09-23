"""Cópia e reescrita do .env de um worktree."""

import re

ENV_MARKER = "# wtp: gerado pelo wtp a partir do .env do checkout principal"


def _key_pattern(key: str) -> re.Pattern[str]:
    return re.compile(rf"^[ \t]*{re.escape(key)}[ \t]*=.*$", re.MULTILINE)


def set_env_value(text: str, key: str, value: str) -> str:
    """Troca (ou acrescenta) uma chave ativa do .env, preservando o resto.

    Exemplo:
        set_env_value("app.baseURL = 'x'\\n", "app.baseURL", "http://a/")
    """
    line = f"{key} = '{value}'"
    pattern = _key_pattern(key)
    if pattern.search(text):
        return pattern.sub(lambda _: line, text, count=1)
    separator = "" if text.endswith("\n") or not text else "\n"
    return f"{text}{separator}{line}\n"


def read_env_value(text: str, key: str) -> str | None:
    """Lê o valor de uma chave ativa, sem aspas.

    Exemplo:
        read_env_value("app.baseURL = 'http://a/'", "app.baseURL")  # 'http://a/'
    """
    match = _key_pattern(key).search(text)
    if match is None:
        return None
    raw = match.group(0).split("=", 1)[1].strip()
    return raw.strip("'\"")


def build_worktree_env(source: str, overrides: dict[str, str]) -> str:
    """Monta o .env do worktree: marca no topo e chaves sobrescritas.

    Exemplo:
        build_worktree_env(main_env, {"app.baseURL": "http://hotfix.agenda.localhost/"})
    """
    body = source.removeprefix(f"{ENV_MARKER}\n")
    for key, value in overrides.items():
        body = set_env_value(body, key, value)
    return f"{ENV_MARKER}\n{body}"


def is_wtp_env(text: str) -> bool:
    """Diz se o .env foi gerado pelo wtp (tem a marca no topo).

    Exemplo:
        is_wtp_env(Path('.env').read_text())
    """
    return text.startswith(ENV_MARKER)
