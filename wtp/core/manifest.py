"""Registro do que o wtp criou em cada worktree, para o rm desfazer só isso."""

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from wtp.core.errors import WtpError


@dataclass
class Manifest:
    project: str
    name: str
    path: str
    branch: str
    created_worktree: bool = False
    created_branch: bool = False
    created_env: bool = False
    created_vhost: bool = False
    db_override: str = ""
    # Ref de onde a branch saiu; o rm só apaga a branch se ela estiver contida aqui.
    base_ref: str = ""
    copied_files: list[str] = field(default_factory=list)
    created_dirs: list[str] = field(default_factory=list)
    # Verdadeiro entre o início e o fim do composer install; se sobrar, roda de novo.
    composer_running: bool = False

    @property
    def slug(self) -> str:
        return f"{self.project}-{self.name}"


def _read_manifest(file: Path) -> Manifest:
    try:
        return Manifest(**json.loads(file.read_text()))
    except (ValueError, TypeError) as exc:
        raise WtpError(
            f"Manifesto corrompido em {file}: {exc}.",
            hint="Confira o arquivo à mão; se o worktree não existe mais, apague esse JSON.",
        ) from exc


def default_state_dir() -> Path:
    """Diretório de estado do wtp, respeitando XDG_STATE_HOME.

    Exemplo:
        default_state_dir()  # ~/.local/state/wtp
    """
    base = os.environ.get("XDG_STATE_HOME", str(Path("~/.local/state").expanduser()))
    return Path(base) / "wtp"


class ManifestStore:
    """Um JSON por worktree em ~/.local/state/wtp/worktrees.

    Exemplo:
        store = ManifestStore(default_state_dir())
        store.load("outserv_agenda-hotfix")
    """

    def __init__(self, state_dir: Path) -> None:
        self.directory = state_dir / "worktrees"

    def _file(self, slug: str) -> Path:
        return self.directory / f"{slug}.json"

    def load(self, slug: str) -> Manifest | None:
        """Lê o manifesto de um worktree, ou None se o wtp não conhece esse worktree.

        Exemplo:
            store.load("outserv_agenda-hotfix").created_worktree  # False (adotado)
        """
        file = self._file(slug)
        return _read_manifest(file) if file.exists() else None

    def save(self, manifest: Manifest) -> None:
        """Grava o manifesto de forma atômica (arquivo temporário e rename).

        Exemplo:
            store.save(manifest)
        """
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self._file(manifest.slug).with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(manifest), indent=2) + "\n")
        temporary.replace(self._file(manifest.slug))

    def delete(self, slug: str) -> None:
        """Apaga o manifesto; não reclama se não existe.

        Exemplo:
            store.delete("outserv_agenda-x")
        """
        self._file(slug).unlink(missing_ok=True)

    def all_for(self, project: str | None) -> list[Manifest]:
        """Todos os manifestos, ou só os de um projeto.

        Exemplo:
            store.all_for("outserv_agenda")
        """
        files = sorted(self.directory.glob("*.json")) if self.directory.exists() else []
        manifests = [_read_manifest(f) for f in files]
        return [m for m in manifests if project is None or m.project == project]
