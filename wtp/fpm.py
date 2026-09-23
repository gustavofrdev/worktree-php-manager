"""Descoberta do usuário do pool do PHP-FPM, que precisa gravar no writable/."""

import re
from dataclasses import dataclass
from pathlib import Path

USER_LINE = re.compile(r"^\s*user\s*=\s*(\S+)", re.MULTILINE)
GROUP_LINE = re.compile(r"^\s*group\s*=\s*(\S+)", re.MULTILINE)


@dataclass(frozen=True)
class PoolIdentity:
    user: str
    group: str


def php_socket(php_version: str) -> str:
    """Socket do PHP-FPM de uma versão.

    Exemplo:
        php_socket("8.1")  # '/run/php/php8.1-fpm.sock'
    """
    return f"/run/php/php{php_version}-fpm.sock"


def parse_pool(text: str) -> PoolIdentity | None:
    """Extrai user e group de um arquivo de pool.

    Exemplo:
        parse_pool("user = nk\\ngroup = nk\\n")  # PoolIdentity('nk', 'nk')
    """
    user = USER_LINE.search(text)
    if user is None:
        return None
    group = GROUP_LINE.search(text)
    return PoolIdentity(user.group(1), group.group(1) if group else user.group(1))


def pool_identity(php_version: str, php_root: Path = Path("/etc/php")) -> PoolIdentity | None:
    """Lê o primeiro pool de /etc/php/<v>/fpm/pool.d que declara user.

    Exemplo:
        pool_identity("8.1")  # PoolIdentity('nk', 'nk') na máquina do nk
    """
    pool_dir = php_root / php_version / "fpm" / "pool.d"
    for conf in sorted(pool_dir.glob("*.conf")):
        identity = parse_pool(conf.read_text(errors="replace"))
        if identity is not None:
            return identity
    return None
