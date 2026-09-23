"""Operações de git sobre o checkout principal e seus worktrees. Nunca usa stash."""

from dataclasses import dataclass
from pathlib import Path

from wtp.adapters.runner import CommandResult, CommandRunner, require_ok
from wtp.core.errors import WtpError


@dataclass(frozen=True)
class WorktreeEntry:
    path: Path
    branch: str
    head: str


def parse_worktree_porcelain(text: str) -> list[WorktreeEntry]:
    """Lê a saída de `git worktree list --porcelain`.

    Exemplo:
        parse_worktree_porcelain("worktree /a\\nHEAD abc\\nbranch refs/heads/main\\n")
    """
    entries: list[WorktreeEntry] = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.partition(" ")[::2] for line in block.splitlines() if line)
        if "worktree" in fields:
            branch = fields.get("branch", "").removeprefix("refs/heads/")
            entries.append(WorktreeEntry(Path(fields["worktree"]), branch, fields.get("HEAD", "")))
    return entries


class GitRepo:
    """Um repositório git, identificado pelo checkout principal.

    Exemplo:
        GitRepo(SubprocessRunner(), Path("/home/nk/Projects/outserv_agenda")).worktrees()
    """

    def __init__(self, runner: CommandRunner, root: Path) -> None:
        self.runner = runner
        self.root = root

    def _git(self, *args: str, cwd: Path | None = None) -> CommandResult:
        return self.runner.run(["git", "-C", str(cwd or self.root), *args])

    def fetch(self) -> None:
        """Atualiza as refs do origin.

        Exemplo:
            repo.fetch()
        """
        require_ok(self._git("fetch", "--quiet", "origin"), "rodar git fetch origin")

    def has_local_branch(self, branch: str) -> bool:
        """Diz se a branch existe localmente.

        Exemplo:
            repo.has_local_branch("main")  # True
        """
        return self._git("show-ref", "--verify", "--quiet", f"refs/heads/{branch}").ok

    def add_worktree_new_branch(self, path: Path, branch: str, start: str) -> None:
        """Cria o worktree numa branch nova, sem upstream.

        Exemplo:
            repo.add_worktree_new_branch(path, "wtp/x", "origin/main")
        """
        result = self._git("worktree", "add", "--no-track", "-b", branch, str(path), start)
        require_ok(result, f"criar o worktree {path} na branch nova {branch}")

    def add_worktree_existing_branch(self, path: Path, branch: str) -> None:
        """Cria o worktree numa branch que já existe.

        Exemplo:
            repo.add_worktree_existing_branch(path, "feat/x")
        """
        result = self._git("worktree", "add", str(path), branch)
        require_ok(result, f"criar o worktree {path} na branch existente {branch}")

    def remove_worktree(self, path: Path) -> None:
        """Remove um worktree limpo; o git recusa se houver alteração.

        Exemplo:
            repo.remove_worktree(path)
        """
        require_ok(self._git("worktree", "remove", str(path)), f"remover o worktree {path}")

    def prune_worktrees(self) -> None:
        """Esquece worktrees cuja pasta já sumiu.

        Exemplo:
            repo.prune_worktrees()
        """
        self._git("worktree", "prune")

    def delete_branch_contained_in(self, branch: str, base: str) -> None:
        """Apaga a branch só se todos os commits dela já estão em base.

        Exemplo:
            repo.delete_branch_contained_in("wtp/x", "origin/main")
        """
        ref = f"refs/heads/{branch}"
        if not self._git("merge-base", "--is-ancestor", ref, base).ok:
            raise WtpError(
                f"A branch {branch} tem commits que {base} não tem; não apaguei a branch.",
                hint="Faça merge ou push dela, ou rode o rm sem --delete-branch para mantê-la.",
            )
        head = require_ok(self._git("rev-parse", "--verify", ref), f"ler a branch {branch}")
        # update-ref com o sha esperado: se alguém commitou nela agora, o git recusa.
        result = self._git("update-ref", "-d", ref, head.stdout.strip())
        require_ok(result, f"apagar a branch {branch}")

    def worktrees(self) -> list[WorktreeEntry]:
        """Lista todos os worktrees, incluindo o checkout principal.

        Exemplo:
            repo.worktrees()[0].branch
        """
        result = require_ok(self._git("worktree", "list", "--porcelain"), "listar os worktrees")
        return parse_worktree_porcelain(result.stdout)

    def is_worktree(self, path: Path) -> bool:
        """Diz se path é um worktree registrado deste repo.

        Exemplo:
            repo.is_worktree(path)
        """
        return any(entry.path == path for entry in self.worktrees())

    def dirty_files(self, path: Path) -> list[str]:
        """Linhas do git status --porcelain (vazio quando limpo).

        Exemplo:
            repo.dirty_files(path)  # [' M app/x.php']
        """
        result = require_ok(self._git("status", "--porcelain", cwd=path), f"ler o status de {path}")
        return [line for line in result.stdout.splitlines() if line.strip()]

    def current_branch(self, path: Path) -> str:
        """Branch atual do worktree, ou '?' se não der para ler.

        Exemplo:
            repo.current_branch(path)  # 'feat/x'
        """
        result = self._git("rev-parse", "--abbrev-ref", "HEAD", cwd=path)
        return result.stdout.strip() if result.ok else "?"

    def ahead_behind(self, path: Path, base: str) -> tuple[int, int] | None:
        """Commits à frente e atrás de base, ou None se base não existir.

        Exemplo:
            repo.ahead_behind(path, "origin/main")  # (2, 0)
        """
        result = self._git("rev-list", "--left-right", "--count", f"{base}...HEAD", cwd=path)
        if not result.ok:
            return None
        behind, ahead = result.stdout.split()
        return int(ahead), int(behind)

    def files_added_since(self, path: Path, base: str, subdir: str) -> list[str]:
        """Arquivos em subdir que a branch tem e base não tem (commitados ou não).

        Exemplo:
            repo.files_added_since(path, "origin/main", "app/Database/Migrations")
        """
        committed = self._git(
            "diff", "--name-only", "--diff-filter=A", f"{base}...HEAD", "--", subdir, cwd=path
        )
        untracked = self._git("ls-files", "--others", "--exclude-standard", "--", subdir, cwd=path)
        names = committed.stdout.splitlines() + untracked.stdout.splitlines()
        return sorted({name for name in names if name.strip()})


def common_checkout(runner: CommandRunner, path: Path) -> Path | None:
    """Checkout principal do repo que contém path, vale para qualquer worktree.

    Exemplo:
        common_checkout(runner, Path("~/Projects/outserv_agenda-hotfix/app"))
    """
    result = runner.run(
        ["git", "-C", str(path), "rev-parse", "--path-format=absolute", "--git-common-dir"]
    )
    if not result.ok:
        return None
    return Path(result.stdout.strip()).parent


def toplevel(runner: CommandRunner, path: Path) -> Path | None:
    """Raiz do worktree que contém path.

    Exemplo:
        toplevel(runner, Path("app"))
    """
    result = runner.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"])
    return Path(result.stdout.strip()) if result.ok else None
