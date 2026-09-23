"""Locks de arquivo, para vários agentes rodarem o wtp ao mesmo tempo."""

import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    """Espera o lock e o segura até o fim do bloco.

    Exemplo:
        with exclusive_lock(state_dir / "apache.lock"):
            reload_apache()
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
