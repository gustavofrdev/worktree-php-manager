"""Dependências compartilhadas pelos comandos, montadas uma vez na CLI."""

from dataclasses import dataclass
from pathlib import Path

from wtp.adapters.apache import ApachePaths, ApacheSites
from wtp.adapters.console import Console
from wtp.adapters.git_ops import GitRepo
from wtp.adapters.runner import CommandRunner
from wtp.core.config import ProjectConfig, WtpConfig
from wtp.core.manifest import ManifestStore
from wtp.core.naming import WorktreeTarget, make_target


@dataclass
class Services:
    """Tudo que tem efeito colateral, num lugar só, para os testes trocarem.

    Exemplo:
        services = build_services(config, SubprocessRunner(), Console(), state_dir)
    """

    config: WtpConfig
    runner: CommandRunner
    apache: ApacheSites
    manifests: ManifestStore
    console: Console
    state_dir: Path
    php_root: Path = Path("/etc/php")

    def git(self, project: ProjectConfig) -> GitRepo:
        """GitRepo do checkout principal do projeto.

        Exemplo:
            services.git(project).worktrees()
        """
        return GitRepo(self.runner, project.main_checkout)

    def target(self, project_key: str, name: str) -> WorktreeTarget:
        """WorktreeTarget validado a partir do config.

        Exemplo:
            services.target("outserv_agenda", "hotfix").url
        """
        return make_target(self.config.project(project_key), name, self.config.worktrees_dir)

    def lock_path(self, slug: str) -> Path:
        """Arquivo de lock para um slug.

        Exemplo:
            services.lock_path("outserv_agenda-x")
        """
        return self.state_dir / "locks" / f"{slug}.lock"


def build_services(
    config: WtpConfig,
    runner: CommandRunner,
    console: Console,
    state_dir: Path,
    apache_paths: ApachePaths | None = None,
    php_root: Path = Path("/etc/php"),
) -> Services:
    """Monta os Services de verdade (ou com caminhos de teste).

    Exemplo:
        build_services(config, SubprocessRunner(), Console(), default_state_dir())
    """
    apache = ApacheSites(runner, apache_paths or ApachePaths(), state_dir / "locks" / "apache.lock")
    return Services(config, runner, apache, ManifestStore(state_dir), console, state_dir, php_root)
