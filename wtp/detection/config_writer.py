"""Escrita de projetos no config.toml, sem nunca sobrescrever o que já existe."""

import json
import tomllib
from dataclasses import fields
from pathlib import Path

from wtp.core.config import ProjectConfig
from wtp.core.errors import WtpError


def _toml_value(value: object) -> str:
    # Strings básicas de TOML aceitam o mesmo escape que JSON para os casos que usamos.
    if isinstance(value, tuple):
        return "[" + ", ".join(json.dumps(str(item)) for item in value) + "]"
    return json.dumps(str(value))


def render_project(project: ProjectConfig) -> str:
    """Seção [projects.<key>] em TOML, com todas as chaves explícitas.

    Exemplo:
        print(render_project(detection.project))
    """
    lines = [f"[projects.{project.key}]"]
    for item in fields(ProjectConfig):
        if item.name != "key":
            lines.append(f"{item.name} = {_toml_value(getattr(project, item.name))}")
    return "\n".join(lines) + "\n"


def add_project(config_path: Path, project: ProjectConfig, worktrees_dir: Path) -> None:
    """Acrescenta o projeto ao config (criando o arquivo se preciso); recusa chave repetida.

    Exemplo:
        add_project(Path("~/.config/wtp/config.toml").expanduser(), project, Path("~/Projects"))
    """
    existing = config_path.read_text() if config_path.exists() else ""
    if project.key in tomllib.loads(existing).get("projects", {}):
        raise WtpError(
            f"O projeto '{project.key}' já está em {config_path}; não sobrescrevi.",
            hint="Edite a seção à mão, ou use --name para cadastrar com outro nome.",
        )
    header = "" if existing else f"[defaults]\nworktrees_dir = {_toml_value(worktrees_dir)}\n"
    separator = "\n" if existing and not existing.endswith("\n\n") else ""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f"{existing}{separator}{header}\n{render_project(project)}")
