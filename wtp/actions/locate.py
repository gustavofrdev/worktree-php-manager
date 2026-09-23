"""wtp which: descobre projeto e worktree a partir de um diretório qualquer."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from wtp.actions.services import Services
from wtp.adapters.git_ops import common_checkout, toplevel
from wtp.core.errors import WtpError
from wtp.core.naming import NAME_PATTERN, WorktreeTarget


@dataclass(frozen=True)
class Location:
    project: str
    main_checkout: str
    worktree: str | None
    path: str
    url: str | None

    def as_dict(self) -> dict[str, Any]:
        """Resultado pronto para o --json.

        Exemplo:
            json.dumps(location.as_dict())
        """
        return asdict(self)


def locate(services: Services, path: Path) -> Location:
    """Diz de qual projeto do config é o diretório, e de qual worktree do wtp.

    Exemplo:
        locate(services, Path.cwd()).project  # 'outserv_agenda'
    """
    main = common_checkout(services.runner, path)
    project = services.config.project_for_checkout(main) if main else None
    if project is None:
        raise WtpError(
            f"{path} não pertence a nenhum projeto do config do wtp.",
            hint=f"Projetos conhecidos estão em {services.config.source}.",
        )
    top = toplevel(services.runner, path) or path
    name = _worktree_name(top, project.key, services.config.worktrees_dir)
    target = WorktreeTarget(project, name, services.config.worktrees_dir) if name else None
    url = target.url if target and services.manifests.load(target.slug) else None
    return Location(project.key, str(project.main_checkout), name, str(top), url)


def _worktree_name(top: Path, project_key: str, worktrees_dir: Path) -> str | None:
    prefix = f"{project_key}-"
    if top.parent != worktrees_dir or not top.name.startswith(prefix):
        return None
    name = top.name.removeprefix(prefix)
    return name if NAME_PATTERN.fullmatch(name) else None
