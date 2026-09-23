"""wtp rm: desfaz exatamente o que o wtp criou, e nada além disso."""

from dataclasses import asdict, dataclass, field
from typing import Any

from wtp.envfile import is_wtp_env
from wtp.errors import WtpError
from wtp.locking import exclusive_lock
from wtp.manifest import Manifest
from wtp.naming import WorktreeTarget
from wtp.services import Services

MAX_DIRTY_LINES = 10


@dataclass
class TeardownReport:
    project: str
    name: str
    removed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Resultado pronto para o --json.

        Exemplo:
            json.dumps(report.as_dict())
        """
        return asdict(self)


class Teardown:
    """Remove vhost, worktree (ou só o .env, se foi adotado) e, se pedido, a branch.

    Exemplo:
        Teardown(services, services.target("outserv_agenda", "x"), delete_branch=True).run()
    """

    def __init__(self, services: Services, target: WorktreeTarget, delete_branch: bool) -> None:
        self.services = services
        self.target = target
        self.delete_branch = delete_branch
        self.git = services.git(target.project)
        self.report = TeardownReport(target.project.key, target.name)

    def run(self) -> TeardownReport:
        """Remove na ordem: vhost, worktree (ou .env e cópias), branch, manifesto.

        Exemplo:
            Teardown(services, target, delete_branch=True).run()
        """
        with exclusive_lock(self.services.lock_path(self.target.slug)):
            manifest = self._require_manifest()
            self._refuse_if_dirty(manifest)
            self._confirm()
            self._remove_vhost()
            self._remove_files(manifest)
            self._remove_branch(manifest)
            self.services.manifests.delete(self.target.slug)
        return self.report

    def _done(self, item: str) -> None:
        self.report.removed.append(item)
        self.services.console.info(f"Removido: {item}")

    def _warn(self, message: str) -> None:
        self.report.warnings.append(message)
        self.services.console.warn(message)

    def _require_manifest(self) -> Manifest:
        manifest = self.services.manifests.load(self.target.slug)
        if manifest is not None:
            return manifest
        if self.services.apache.is_ours(self.target.vhost_name):
            # Sobrou só o vhost de uma execução interrompida: limpa ele.
            t = self.target
            return Manifest(t.project.key, t.name, str(t.path), "", created_vhost=True)
        raise WtpError(
            f"O wtp não tem registro do worktree '{self.target.slug}'.",
            hint=f"Veja os worktrees com: wtp ls {self.target.project.key}",
        )

    def _refuse_if_dirty(self, manifest: Manifest) -> None:
        path = self.target.path
        if not manifest.created_worktree or not self.git.is_worktree(path):
            return
        dirty = self.git.dirty_files(path)
        if not dirty:
            return
        listing = "\n".join(f"  {line}" for line in dirty[:MAX_DIRTY_LINES])
        raise WtpError(
            f"{path} tem alterações não commitadas; não removi nada.\n{listing}",
            hint="Commite ou descarte essas alterações (sem git stash) e rode o rm de novo.",
        )

    def _confirm(self) -> None:
        question = f"Vou remover o worktree {self.target.slug} e o vhost dele (sudo). Continuar?"
        if not self.services.console.confirm(question):
            raise WtpError("Parei antes de remover qualquer coisa.", hint="Rode de novo com --yes.")

    def _remove_vhost(self) -> None:
        name = self.target.vhost_name
        if not self.services.apache.exists(name):
            return
        self.services.apache.remove(name)
        self._done(f"vhost {name} (Apache recarregado)")

    def _remove_files(self, manifest: Manifest) -> None:
        path = self.target.path
        if manifest.created_worktree and self.git.is_worktree(path):
            self.git.remove_worktree(path)
            self._done(f"worktree {path}")
            return
        if manifest.created_worktree:
            self.git.prune_worktrees()
            return
        self._remove_env(manifest)
        self._remove_copied_files(manifest)

    def _remove_copied_files(self, manifest: Manifest) -> None:
        root = self.target.path.resolve()
        for relative in manifest.copied_files:
            copied = (self.target.path / relative).resolve()
            if not copied.is_relative_to(root):
                self._warn(f"Ignorei {relative!r} do manifesto: fica fora do worktree {root}.")
                continue
            if copied.is_file():
                copied.unlink()
                self._done(f"{copied} (copiado pelo wtp)")

    def _remove_env(self, manifest: Manifest) -> None:
        env_path = self.target.path / self.target.project.env_file
        if manifest.created_env and env_path.exists() and is_wtp_env(env_path.read_text()):
            env_path.unlink()
            self._done(f"{env_path} (worktree adotado continua no lugar)")

    def _remove_branch(self, manifest: Manifest) -> None:
        if not self.delete_branch or not manifest.branch:
            return
        if not manifest.created_branch:
            self._warn(f"Não apaguei a branch {manifest.branch}: ela não foi criada pelo wtp.")
            return
        base = manifest.base_ref or f"origin/{self.target.project.main_branch}"
        self.git.delete_branch_contained_in(manifest.branch, base)
        self._done(f"branch {manifest.branch}")


def teardown(services: Services, target: WorktreeTarget, delete_branch: bool) -> TeardownReport:
    """Atalho para Teardown(...).run().

    Exemplo:
        teardown(services, target, delete_branch=False)
    """
    return Teardown(services, target, delete_branch).run()
