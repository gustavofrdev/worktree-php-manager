"""Leitura do config.toml com os projetos conhecidos."""

import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from wtp.errors import WtpError
from wtp.validation import (
    ensure_domain,
    ensure_php_version,
    ensure_relative_path,
    ensure_safe_absolute,
    validate_branch,
)

DEFAULT_CONFIG_PATH = Path("~/.config/wtp/config.toml")
REQUIRED_PROJECT_KEYS = ("main_checkout", "domain", "php_version")


@dataclass(frozen=True)
class ProjectConfig:
    key: str
    main_checkout: Path
    domain: str
    php_version: str
    env_file: str = ".env"
    base_url_key: str = "app.baseURL"
    main_branch: str = "main"
    document_root: str = "public"
    db_override_key: str = ""
    migrations_dir: str = "app/Database/Migrations"
    writable_dir: str = "writable"
    # Arquivos ignorados pelo git que o app precisa (credenciais, config local).
    copy_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class WtpConfig:
    projects: dict[str, ProjectConfig]
    worktrees_dir: Path
    source: Path

    def project(self, key: str) -> ProjectConfig:
        """Devolve o projeto pelo nome do config.

        Exemplo:
            config.project("outserv_agenda").domain  # 'agenda.localhost'
        """
        if key in self.projects:
            return self.projects[key]
        known = ", ".join(sorted(self.projects)) or "nenhum"
        raise WtpError(
            f"Projeto '{key}' não está no config. Projetos conhecidos: {known}.",
            hint=f"Adicione uma seção [projects.{key}] em {self.source}.",
        )

    def project_for_checkout(self, main_checkout: Path) -> ProjectConfig | None:
        """Acha o projeto cujo checkout principal é esse diretório.

        Exemplo:
            config.project_for_checkout(Path("/home/nk/Projects/outserv_agenda"))
        """
        resolved = main_checkout.resolve()
        matches = [p for p in self.projects.values() if p.main_checkout == resolved]
        return matches[0] if matches else None


def default_config_path() -> Path:
    """Caminho do config, respeitando a variável WTP_CONFIG.

    Exemplo:
        default_config_path()  # ~/.config/wtp/config.toml
    """
    return Path(os.environ.get("WTP_CONFIG", str(DEFAULT_CONFIG_PATH))).expanduser()


def load_config(path: Path) -> WtpConfig:
    """Lê o config.toml e valida cada projeto.

    Exemplo:
        load_config(Path("~/.config/wtp/config.toml").expanduser())
    """
    if not path.exists():
        raise WtpError(
            f"Config não encontrado em {path}.",
            hint="Copie o config.example.toml do repositório do wtp para esse caminho.",
        )
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    defaults = raw.get("defaults", {})
    raw_dir = str(defaults.get("worktrees_dir", "~/Projects"))
    worktrees_dir = Path(ensure_safe_absolute(_expand_text(raw_dir), "worktrees_dir"))
    tables = raw.get("projects", {})
    projects = {key: _project_from_table(key, table, path) for key, table in tables.items()}
    return WtpConfig(projects=projects, worktrees_dir=worktrees_dir, source=path)


def _project_from_table(key: str, table: dict[str, Any], source: Path) -> ProjectConfig:
    _reject_bad_keys(key, table, source)
    read = _ProjectTable(key, table, source)
    defaults = ProjectConfig(key, Path(), "", "")
    return ProjectConfig(
        key=key,
        main_checkout=Path(
            ensure_safe_absolute(_expand_text(read.text("main_checkout")), "main_checkout")
        ),
        domain=ensure_domain(read.text("domain")),
        php_version=ensure_php_version(read.text("php_version")),
        env_file=read.relative("env_file", defaults.env_file),
        base_url_key=read.text("base_url_key", defaults.base_url_key),
        main_branch=validate_branch(read.text("main_branch", defaults.main_branch)),
        document_root=read.relative("document_root", defaults.document_root),
        db_override_key=read.text("db_override_key", defaults.db_override_key),
        migrations_dir=read.relative("migrations_dir", defaults.migrations_dir),
        writable_dir=read.relative("writable_dir", defaults.writable_dir),
        copy_files=read.relative_list("copy_files"),
    )


class _ProjectTable:
    """Lê uma seção [projects.x] exigindo o tipo certo em cada chave."""

    def __init__(self, key: str, table: dict[str, Any], source: Path) -> None:
        self.key = key
        self.table = table
        self.source = source

    def text(self, name: str, default: str | None = None) -> str:
        value = self.table.get(name, default)
        if isinstance(value, str):
            return value
        raise WtpError(
            f"Projeto '{self.key}' em {self.source}: {name} = {value!r} não é texto.",
            hint=f'Escreva entre aspas, por exemplo {name} = "..."',
        )

    def relative(self, name: str, default: str) -> str:
        return ensure_relative_path(self.text(name, default), name)

    def relative_list(self, name: str) -> tuple[str, ...]:
        value = self.table.get(name, [])
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return tuple(ensure_relative_path(item, name) for item in value)
        raise WtpError(
            f"Projeto '{self.key}' em {self.source}: {name} = {value!r} não é uma lista de textos.",
            hint=f'Exemplo: {name} = ["app/Config/Constants.php"]',
        )


def _reject_bad_keys(key: str, table: dict[str, Any], source: Path) -> None:
    missing = [name for name in REQUIRED_PROJECT_KEYS if name not in table]
    if missing:
        raise WtpError(
            f"Projeto '{key}' em {source} sem as chaves obrigatórias: {', '.join(missing)}.",
            hint=f"Chaves obrigatórias: {', '.join(REQUIRED_PROJECT_KEYS)}.",
        )
    allowed = {f.name for f in fields(ProjectConfig)} - {"key"}
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise WtpError(
            f"Projeto '{key}' em {source} tem chaves desconhecidas: {', '.join(unknown)}.",
            hint=f"Chaves aceitas: {', '.join(sorted(allowed))}.",
        )


def _expand_text(value: str) -> str:
    return str(Path(value).expanduser().resolve())
