"""Validação de tudo que vem de fora e acaba no git, no shell do sudo ou no vhost."""

import re
from pathlib import PurePosixPath

from wtp.errors import WtpError

# Caminhos relativos: sem espaço, aspas ou quebra de linha, que viram diretiva no vhost.
RELATIVE_PATH = re.compile(r"^[A-Za-z0-9._@+-]+(?:/[A-Za-z0-9._@+-]+)*$")
SAFE_ABSOLUTE = re.compile(r"^/[^\s\"'\\]*$")
DNS_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
DOMAIN = re.compile(rf"^{DNS_LABEL}(?:\.{DNS_LABEL})+$")
PHP_VERSION = re.compile(r"^\d+\.\d+$")
DB_NAME = re.compile(r"^[A-Za-z0-9_]{1,64}$")
BRANCH_PART = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")


def ensure_relative_path(value: str, label: str) -> str:
    """Aceita só caminho relativo que fica dentro do worktree.

    Exemplo:
        ensure_relative_path("app/Config/App.php", "copy_files")  # 'app/Config/App.php'
    """
    parts = PurePosixPath(value).parts
    if RELATIVE_PATH.fullmatch(value) and ".." not in parts:
        return value
    raise WtpError(
        f"{label} = {value!r} não é um caminho relativo dentro do worktree.",
        hint="Use algo como app/Config/App.php: sem '..', sem '/' no início, sem espaço ou aspas.",
    )


def ensure_safe_absolute(value: str, label: str) -> str:
    """Aceita caminho absoluto que pode ir cru para o vhost.

    Exemplo:
        ensure_safe_absolute("/home/nk/Projects/outserv_agenda", "main_checkout")
    """
    if SAFE_ABSOLUTE.fullmatch(value):
        return value
    raise WtpError(
        f"{label} = {value!r} tem espaço, aspas ou barra invertida.",
        hint="O caminho vai para o DocumentRoot do Apache; use um caminho sem esses caracteres.",
    )


def ensure_domain(value: str) -> str:
    """Aceita domínio com pelo menos dois rótulos DNS, em minúsculas.

    Exemplo:
        ensure_domain("agenda.localhost")  # 'agenda.localhost'
    """
    if DOMAIN.fullmatch(value):
        return value
    raise WtpError(
        f"domain = {value!r} não é um domínio válido.",
        hint="Formato esperado: <projeto>.localhost, por exemplo agenda.localhost.",
    )


def ensure_php_version(value: str) -> str:
    """Aceita versão no formato maior.menor, que vira o nome do socket do FPM.

    Exemplo:
        ensure_php_version("8.1")  # '8.1'
    """
    if PHP_VERSION.fullmatch(value):
        return value
    raise WtpError(
        f"php_version = {value!r} não está no formato esperado.",
        hint='Use texto entre aspas, por exemplo php_version = "8.1".',
    )


def ensure_db_name(value: str) -> str:
    """Aceita nome de banco que cabe entre aspas simples no .env.

    Exemplo:
        ensure_db_name("CRMRAT_QA")  # 'CRMRAT_QA'
    """
    if DB_NAME.fullmatch(value):
        return value
    raise WtpError(
        f"--db {value!r} não é um nome de banco aceito.",
        hint="Use de 1 a 64 caracteres entre letras, dígitos e _.",
    )


def validate_branch(branch: str) -> str:
    """Recusa branch que o git leria como opção ou que não é ref válida.

    Exemplo:
        validate_branch("feat/relatorio-horas")  # 'feat/relatorio-horas'
    """
    parts = branch.split("/")
    if all(_is_branch_part(part) for part in parts):
        return branch
    raise WtpError(
        f"Branch inválida: {branch!r}.",
        hint="Use partes separadas por '/', com letras, dígitos, '.', '_' e '-', sem começar "
        "com '-' ou '.', sem '..' e sem terminar em .lock. Exemplo: feat/relatorio-horas.",
    )


def _is_branch_part(part: str) -> bool:
    return bool(BRANCH_PART.fullmatch(part)) and ".." not in part and not part.endswith(".lock")
