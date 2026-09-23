"""Nomes derivados de um worktree: caminho, host, URL, arquivo de vhost."""

import re
from dataclasses import dataclass
from pathlib import Path

from wtp.core.config import ProjectConfig
from wtp.core.errors import WtpError

# Vira um rótulo de DNS no host, então segue as regras de rótulo (sem ponto, sem _).
NAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
VHOST_PREFIX = "wtp-"


def validate_name(name: str) -> str:
    """Recusa nomes que não viram um subdomínio válido.

    Exemplo:
        validate_name("hotfix")  # 'hotfix'
    """
    if NAME_PATTERN.fullmatch(name):
        return name
    raise WtpError(
        f"Nome de worktree inválido: '{name}'.",
        hint="Use de 1 a 40 caracteres: letras minúsculas, dígitos e hífen, sem hífen nas pontas.",
    )


@dataclass(frozen=True)
class WorktreeTarget:
    """Tudo que deriva do par (projeto, nome).

    Exemplo:
        WorktreeTarget(project, "hotfix", Path("~/Projects")).url  # 'http://hotfix.agenda.localhost/'
    """

    project: ProjectConfig
    name: str
    worktrees_dir: Path

    @property
    def slug(self) -> str:
        return f"{self.project.key}-{self.name}"

    @property
    def path(self) -> Path:
        return self.worktrees_dir / self.slug

    @property
    def host(self) -> str:
        return f"{self.name}.{self.project.domain}"

    @property
    def url(self) -> str:
        return f"http://{self.host}/"

    @property
    def vhost_name(self) -> str:
        return f"{VHOST_PREFIX}{self.slug}"

    @property
    def default_branch(self) -> str:
        return f"wtp/{self.name}"

    @property
    def document_root(self) -> Path:
        return self.path / self.project.document_root


def make_target(project: ProjectConfig, name: str, worktrees_dir: Path) -> WorktreeTarget:
    """Valida o nome e monta o WorktreeTarget.

    Exemplo:
        make_target(project, "hotfix", Path("/home/nk/Projects"))
    """
    return WorktreeTarget(project, validate_name(name), worktrees_dir)
