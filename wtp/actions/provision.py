"""wtp new e wtp adopt: deixam um worktree pronto e servido pelo Apache."""

import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from wtp.actions.services import Services
from wtp.adapters.apache import render_vhost
from wtp.adapters.composer import composer_install_command
from wtp.adapters.fpm import PoolIdentity, pool_identity
from wtp.adapters.locking import exclusive_lock
from wtp.adapters.permissions import grant_group_write, pool_can_write
from wtp.adapters.runner import require_ok
from wtp.core.envfile import build_worktree_env, is_wtp_env, read_env_value
from wtp.core.errors import WtpError
from wtp.core.manifest import Manifest
from wtp.core.naming import WorktreeTarget
from wtp.core.validation import ensure_db_name, validate_branch


@dataclass(frozen=True)
class NewOptions:
    base: str | None = None
    branch: str | None = None
    db: str | None = None
    adopt: bool = False
    run_composer: bool = True


@dataclass
class ProvisionReport:
    project: str
    name: str
    path: str
    url: str
    branch: str
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Resultado pronto para o --json.

        Exemplo:
            json.dumps(report.as_dict())
        """
        return asdict(self)


class Provisioner:
    """Cria ou completa um worktree. Rodar duas vezes termina no mesmo estado.

    Exemplo:
        Provisioner(services, services.target("outserv_agenda", "x"), NewOptions()).run()
    """

    def __init__(self, services: Services, target: WorktreeTarget, options: NewOptions) -> None:
        self.services = services
        self.target = target
        self.options = options
        self.project = target.project
        self.git = services.git(target.project)
        self.warnings: list[str] = []

    def run(self) -> ProvisionReport:
        """Executa todas as etapas e devolve o que o agente precisa (path, url, branch).

        Exemplo:
            report = Provisioner(services, target, NewOptions(branch="feat/x")).run()
        """
        self._validate_options()
        self._check_main_checkout()
        with exclusive_lock(self.services.lock_path(self.target.slug)):
            manifest = self._load_manifest()
            self._confirm_apache()
            self._ensure_worktree(manifest)
            self._save(manifest)
            self._ensure_env(manifest)
            self._ensure_local_files(manifest)
            # Pastas antes do composer: o package:discover do Laravel já precisa delas.
            self._ensure_dirs(manifest)
            self._save(manifest)
            self._ensure_vendor(manifest)
            self._ensure_writable()
            self._ensure_vhost(manifest)
            self._save(manifest)
            self._warn_new_migrations(manifest)
        return self._report(manifest)

    def _validate_options(self) -> None:
        # Antes de qualquer efeito: esses valores vão para o git e para o .env.
        if self.options.branch:
            validate_branch(self.options.branch)
        if self.options.base:
            validate_branch(self.options.base)
        if self.options.db:
            ensure_db_name(self.options.db)

    def _warn(self, message: str) -> None:
        self.warnings.append(message)
        self.services.console.warn(message)

    def _save(self, manifest: Manifest) -> None:
        self.services.manifests.save(manifest)

    def _check_main_checkout(self) -> None:
        if (self.project.main_checkout / ".git").exists():
            return
        raise WtpError(
            f"Checkout principal {self.project.main_checkout} não é um repositório git.",
            hint=f"Confira main_checkout de [projects.{self.project.key}] no config.",
        )

    def _load_manifest(self) -> Manifest:
        existing = self.services.manifests.load(self.target.slug)
        if existing is not None:
            return existing
        branch = validate_branch(self.options.branch or self.target.default_branch)
        return Manifest(self.project.key, self.target.name, str(self.target.path), branch)

    def _confirm_apache(self) -> None:
        if self._vhost_is_current():
            return
        question = (
            f"Vou criar e habilitar o vhost {self.target.vhost_name} ({self.target.host}) "
            "e recarregar o Apache com sudo. Continuar?"
        )
        if not self.services.console.confirm(question):
            raise WtpError(
                "Parei antes de mexer em qualquer coisa.", hint="Rode de novo com --yes."
            )

    def _vhost_is_current(self) -> bool:
        apache = self.services.apache
        name = self.target.vhost_name
        current = apache.installed_content(name) == render_vhost(self.target)
        return apache.is_ours(name) and current and apache.is_enabled(name)

    def _ensure_worktree(self, manifest: Manifest) -> None:
        path = self.target.path
        if self.git.is_worktree(path):
            self._accept_existing(manifest)
            return
        if path.exists():
            raise WtpError(
                f"{path} já existe mas não é worktree de {self.project.main_checkout}.",
                hint="Mova ou apague essa pasta, ou escolha outro nome.",
            )
        if self.options.adopt:
            raise WtpError(
                f"Não há worktree em {path} para adotar.", hint="Para criar um, use wtp new."
            )
        self._create_worktree(manifest)

    def _accept_existing(self, manifest: Manifest) -> None:
        if not (manifest.created_worktree or self.options.adopt):
            raise WtpError(
                f"Já existe um worktree em {self.target.path} que o wtp não criou.",
                hint=f"Para servir sem recriar: wtp adopt {self.project.key} {self.target.name}",
            )
        manifest.branch = self.git.current_branch(self.target.path)

    def _create_worktree(self, manifest: Manifest) -> None:
        # Vários agentes no mesmo repo: fetch e worktree add em paralelo brigam pelos locks de ref.
        with exclusive_lock(self.services.lock_path(f"git-{self.project.key}")):
            self._fetch_and_add(manifest)
        self.services.console.info(
            f"Worktree criado em {self.target.path} na branch {manifest.branch}."
        )

    def _fetch_and_add(self, manifest: Manifest) -> None:
        self.services.console.info("Buscando o origin (git fetch)...")
        self.git.fetch()
        path, branch = self.target.path, manifest.branch
        if self.git.has_local_branch(branch):
            self.git.add_worktree_existing_branch(path, branch)
        else:
            start = f"origin/{self.options.base or self.project.main_branch}"
            self.git.add_worktree_new_branch(path, branch, start)
            manifest.created_branch = True
            manifest.base_ref = start
        manifest.created_worktree = True

    def _ensure_env(self, manifest: Manifest) -> None:
        env_path = self.target.path / self.project.env_file
        if env_path.exists() and not is_wtp_env(env_path.read_text()):
            self._warn(f"{env_path} já existe e não foi gerado pelo wtp; deixei como está.")
            return
        source = self.project.main_checkout / self.project.env_file
        if not source.exists():
            raise WtpError(
                f"Não achei {source} para copiar.", hint="Crie o .env do checkout principal."
            )
        source_text = source.read_text()
        env_path.write_text(build_worktree_env(source_text, self._env_overrides(manifest)))
        self._warn_base_url(source_text)
        # O .env tem credenciais: a cópia fica com a mesma permissão do original.
        shutil.copymode(source, env_path)
        manifest.created_env = True

    def _ensure_local_files(self, manifest: Manifest) -> None:
        for relative in self.project.copy_files:
            destination = self.target.path / relative
            source = self.project.main_checkout / relative
            if destination.exists():
                continue
            if not source.exists():
                self._warn(f"{relative} não existe no checkout principal; não copiei.")
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            manifest.copied_files.append(relative)

    def _warn_base_url(self, source_text: str) -> None:
        key = self.project.base_url_key
        if not key:
            self._warn(
                f"O wtp não sabe onde o projeto '{self.project.key}' guarda a URL base, então não "
                f"mexeu nela. Agente: descubra pelo código qual chave do .env define a URL base, "
                f"ponha base_url_key em [projects.{self.project.key}] e rode wtp new de novo "
                f"(a URL do worktree é {self.target.url}). Só pergunte ao usuário se o código "
                "não mostrar."
            )
        elif read_env_value(source_text, key) is None:
            self._warn(
                f"A chave {key} não existia no .env do checkout principal; acrescentei no "
                "worktree. Agente: confira no código do projeto se é essa a chave da URL base."
            )

    def _env_overrides(self, manifest: Manifest) -> dict[str, str]:
        key = self.project.base_url_key
        overrides = {key: self.target.url} if key else {}
        manifest.db_override = self.options.db or manifest.db_override
        if not manifest.db_override:
            return overrides
        if not self.project.db_override_key:
            raise WtpError(
                f"Pediu --db, mas o projeto '{self.project.key}' não tem db_override_key.",
                hint='Exemplo no config: db_override_key = "database.default.database"',
            )
        overrides[self.project.db_override_key] = manifest.db_override
        return overrides

    def _ensure_vendor(self, manifest: Manifest) -> None:
        path = self.target.path
        # composer_running sobrou de uma execução que falhou: vendor/ pode estar pela metade.
        vendor_ready = (path / "vendor").exists() and not manifest.composer_running
        if not self.options.run_composer or vendor_ready or not (path / "composer.json").exists():
            return
        self.services.console.info("Rodando composer install...")
        manifest.composer_running = True
        self._save(manifest)
        command = composer_install_command(self.project.php_version)
        require_ok(self.services.runner.run(command, cwd=path), "rodar composer install")
        manifest.composer_running = False
        self._save(manifest)

    def _ensure_dirs(self, manifest: Manifest) -> None:
        for relative in self.project.ensure_dirs:
            directory = self.target.path / relative
            if directory.is_dir():
                continue
            # Guarda só a pasta mais alta que faltava: o rm não pode apagar o que já existia.
            manifest.created_dirs.append(_first_missing(self.target.path, relative))
            directory.mkdir(parents=True)

    def _ensure_writable(self) -> None:
        identity = pool_identity(self.project.php_version, self.services.php_root)
        if identity is None:
            self._warn(f"Não achei o pool do PHP {self.project.php_version} em /etc/php.")
            return
        for relative in self.project.writable_dirs:
            self._ensure_writable_dir(self.target.path / relative, identity)

    def _ensure_writable_dir(self, writable: Path, identity: PoolIdentity) -> None:
        if not writable.exists():
            self._warn(f"{writable} não existe; o PHP pode falhar ao gravar.")
            return
        if pool_can_write(writable, identity):
            return
        if not self.services.console.confirm(
            f"Dar escrita ao grupo {identity.group} em {writable}?"
        ):
            self._warn(f"{writable} sem escrita para {identity.user}; o PHP vai falhar ao gravar.")
            return
        grant_group_write(self.services.runner, writable, identity)

    def _ensure_vhost(self, manifest: Manifest) -> None:
        if not self._vhost_is_current():
            self.services.console.info(f"Instalando o vhost {self.target.vhost_name}...")
            self.services.apache.install(self.target)
        manifest.created_vhost = True

    def _warn_new_migrations(self, manifest: Manifest) -> None:
        base = f"origin/{self.project.main_branch}"
        added = self.git.files_added_since(self.target.path, base, self.project.migrations_dir)
        if not added or manifest.db_override:
            return
        self._warn(
            f"A branch tem {len(added)} migration(s) que {base} não tem: {', '.join(added[:5])}. "
            "O banco é compartilhado com os outros worktrees; rodar essas migrations muda o "
            "esquema para todos. Para isolar, use --db <outro_banco>."
        )

    def _report(self, manifest: Manifest) -> ProvisionReport:
        return ProvisionReport(
            self.project.key,
            self.target.name,
            str(self.target.path),
            self.target.url,
            manifest.branch,
            self.warnings,
        )


def _first_missing(root: Path, relative: str) -> str:
    parts = Path(relative).parts
    prefixes = [Path(*parts[: i + 1]) for i in range(len(parts))]
    return str(next(p for p in prefixes if not (root / p).exists()))


def provision(services: Services, target: WorktreeTarget, options: NewOptions) -> ProvisionReport:
    """Atalho para Provisioner(...).run().

    Exemplo:
        provision(services, target, NewOptions(branch="feat/x"))
    """
    return Provisioner(services, target, options).run()
