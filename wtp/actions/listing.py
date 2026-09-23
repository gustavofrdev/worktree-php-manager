"""wtp ls: estado de cada worktree dos projetos."""

from dataclasses import asdict, dataclass
from typing import Any

from wtp.actions.services import Services
from wtp.core.config import ProjectConfig
from wtp.core.naming import WorktreeTarget


@dataclass(frozen=True)
class ListingRow:
    project: str
    name: str
    branch: str
    ahead: int | None
    behind: int | None
    dirty: bool
    url: str
    vhost_enabled: bool
    managed: bool
    path: str

    def as_dict(self) -> dict[str, Any]:
        """Linha pronta para o --json.

        Exemplo:
            json.dumps(row.as_dict())
        """
        return asdict(self)


def list_rows(services: Services, project_key: str | None) -> list[ListingRow]:
    """Uma linha por worktree (fora o checkout principal) de cada projeto.

    Exemplo:
        list_rows(services, "outserv_agenda")
    """
    keys = [project_key] if project_key else sorted(services.config.projects)
    rows: list[ListingRow] = []
    for key in keys:
        rows.extend(_project_rows(services, services.config.project(key)))
    return rows


def _project_rows(services: Services, project: ProjectConfig) -> list[ListingRow]:
    git = services.git(project)
    prefix = f"{project.key}-"
    rows: list[ListingRow] = []
    for entry in git.worktrees():
        if entry.path == project.main_checkout:
            continue
        name = entry.path.name.removeprefix(prefix)
        target = WorktreeTarget(project, name, services.config.worktrees_dir)
        rows.append(
            _row(services, target, entry.branch, target.path == entry.path, str(entry.path))
        )
    return rows


def _row(
    services: Services, target: WorktreeTarget, branch: str, in_place: bool, path: str
) -> ListingRow:
    git = services.git(target.project)
    manifest = services.manifests.load(target.slug) if in_place else None
    counts = (
        git.ahead_behind(target.path, f"origin/{target.project.main_branch}") if in_place else None
    )
    enabled = in_place and services.apache.is_enabled(target.vhost_name)
    dirty = bool(git.dirty_files(target.path)) if in_place else False
    return ListingRow(
        target.project.key,
        target.name,
        branch,
        counts[0] if counts else None,
        counts[1] if counts else None,
        dirty,
        target.url if enabled else "",
        enabled,
        manifest is not None,
        path,
    )


def format_rows(rows: list[ListingRow]) -> str:
    """Tabela simples para o terminal.

    Exemplo:
        print(format_rows(list_rows(services, None)))
    """
    if not rows:
        return "Nenhum worktree além do checkout principal."
    header = ("PROJETO", "NOME", "BRANCH", "+/-", "ALTERADO", "URL", "WTP")
    lines = [header, *(_cells(row) for row in rows)]
    widths = [max(len(line[i]) for line in lines) for i in range(len(header))]
    return "\n".join(
        "  ".join(c.ljust(w) for c, w in zip(line, widths, strict=True)).rstrip() for line in lines
    )


def _cells(row: ListingRow) -> tuple[str, ...]:
    counts = "?" if row.ahead is None else f"+{row.ahead}/-{row.behind}"
    url = row.url or "(sem vhost)"
    return (
        row.project,
        row.name,
        row.branch,
        counts,
        "sim" if row.dirty else "não",
        url,
        "sim" if row.managed else "não",
    )
