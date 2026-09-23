"""Escrita no writable/ pelo usuário do pool do PHP-FPM."""

import grp
import pwd
import stat
from pathlib import Path

from wtp.adapters.fpm import PoolIdentity
from wtp.adapters.runner import CommandRunner, require_ok

# -h -P: symlink versionado em writable/ não pode levar o chgrp (root) para fora dele.
# O chmod -R já ignora symlinks encontrados na recursão.
GRANT_SCRIPT = 'chgrp -R -h -P "$1" "$2" && chmod -R g+rwX "$2"'


def pool_can_write(directory: Path, identity: PoolIdentity) -> bool:
    """Diz se o usuário do pool grava em directory, pelo dono ou pelo grupo.

    Exemplo:
        pool_can_write(Path("writable"), PoolIdentity("nk", "nk"))
    """
    info = directory.stat()
    if _uid(identity.user) == info.st_uid:
        return bool(info.st_mode & stat.S_IWUSR)
    if _gid(identity.group) == info.st_gid:
        return bool(info.st_mode & stat.S_IWGRP)
    return bool(info.st_mode & stat.S_IWOTH)


def grant_group_write(runner: CommandRunner, directory: Path, identity: PoolIdentity) -> None:
    """Dá escrita ao grupo do pool em directory, com um sudo.

    Exemplo:
        grant_group_write(runner, Path("writable"), identity)
    """
    result = runner.run(
        ["sudo", "-n", "bash", "-c", GRANT_SCRIPT, "wtp", identity.group, str(directory)]
    )
    require_ok(result, f"dar escrita ao grupo {identity.group} em {directory}")


def _uid(user: str) -> int:
    try:
        return pwd.getpwnam(user).pw_uid
    except KeyError:
        return -1


def _gid(group: str) -> int:
    try:
        return grp.getgrnam(group).gr_gid
    except KeyError:
        return -1
