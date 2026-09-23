"""Cópia e reescrita do .env de um worktree."""

import re

ENV_MARKER = "# wtp: gerado pelo wtp a partir do .env do checkout principal"


# Grupos: recuo, chave, espaço antes do =, espaço depois, aspas de abertura.
STYLED_LINE = r"^([ \t]*)({key})([ \t]*)=([ \t]*)(['\"]?).*$"
ACTIVE_LINE = re.compile(r"^[ \t]*[A-Za-z_][\w.]*([ \t]*)=([ \t]*)(['\"]?)", re.MULTILINE)


def _key_pattern(key: str) -> re.Pattern[str]:
    return re.compile(STYLED_LINE.format(key=re.escape(key)), re.MULTILINE)


def set_env_value(text: str, key: str, value: str) -> str:
    """Troca (ou acrescenta) uma chave ativa do .env, no estilo do próprio arquivo.

    CodeIgniter usa `app.baseURL = 'x'`; Laravel usa `APP_URL=x`. A linha trocada
    mantém espaços e aspas da original; uma chave nova segue o estilo da maioria.

    Exemplo:
        set_env_value("APP_URL=http://old\\n", "APP_URL", "http://a/")  # 'APP_URL=http://a/\\n'
    """
    pattern = _key_pattern(key)
    match = pattern.search(text)
    if match:
        indent, _, before, after, quote = match.groups()
        line = f"{indent}{key}{before}={after}{quote}{value}{quote}"
        return pattern.sub(lambda _: line, text, count=1)
    separator = "" if text.endswith("\n") or not text else "\n"
    return f"{text}{separator}{_new_line(text, key, value)}\n"


def _new_line(text: str, key: str, value: str) -> str:
    styles = ACTIVE_LINE.findall(text)
    plain = sum(1 for before, after, quote in styles if not before and not after and not quote)
    if styles and plain * 2 > len(styles):
        return f"{key}={value}"
    return f"{key} = '{value}'"


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
