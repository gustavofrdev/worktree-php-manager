"""Argumentos da linha de comando: um subcomando por ação do wtp."""

import argparse
from pathlib import Path
from typing import Any

from wtp import __version__


def build_parser() -> argparse.ArgumentParser:
    """Monta o argparse com todos os subcomandos.

    Exemplo:
        build_parser().parse_args(["ls", "--json"])
    """
    parser = argparse.ArgumentParser(prog="wtp", description="Worktrees PHP com vhost próprio.")
    parser.add_argument("--version", action="version", version=f"wtp {__version__}")
    parser.add_argument("--config", type=Path, help="caminho do config.toml")
    parser.add_argument("--debug", action="store_true", help="mostra o traceback em erros")
    commands = parser.add_subparsers(dest="command", required=True)
    _add_new(commands)
    _add_adopt(commands)
    _add_simple(commands)
    return parser


def _common(sub: argparse.ArgumentParser, target: bool = True, confirm: bool = False) -> None:
    if target:
        sub.add_argument("project", help="projeto do config, por exemplo outserv_agenda")
        sub.add_argument("name", help="nome do worktree, vira <nome>.<domínio>")
    if confirm:
        sub.add_argument("-y", "--yes", action="store_true", help="não pergunta antes do sudo")
    sub.add_argument("--json", action="store_true", help="saída em JSON no stdout")


def _add_new(commands: Any) -> None:
    sub = commands.add_parser("new", help="cria worktree, .env e vhost")
    _common(sub, confirm=True)
    sub.add_argument("--from", dest="base", help="branch base no origin (padrão: main do config)")
    sub.add_argument("--branch", help="branch do worktree (padrão: wtp/<nome>)")
    sub.add_argument("--db", help="banco próprio para este worktree")
    sub.add_argument("--no-composer", action="store_true", help="não roda composer install")


def _add_adopt(commands: Any) -> None:
    sub = commands.add_parser("adopt", help="serve um worktree que já existe, sem recriar")
    _common(sub, confirm=True)
    sub.add_argument("--db", help="banco próprio para este worktree")
    sub.add_argument("--no-composer", action="store_true", help="não roda composer install")


def _add_simple(commands: Any) -> None:
    ls = commands.add_parser("ls", help="lista os worktrees")
    ls.add_argument("project", nargs="?")
    _common(ls, target=False)
    _common(commands.add_parser("open", help="abre a URL no navegador do Windows"))
    rm = commands.add_parser("rm", help="remove o que o wtp criou")
    _common(rm, confirm=True)
    rm.add_argument("--delete-branch", action="store_true", help="apaga a branch, se o wtp a criou")
    doctor = commands.add_parser("doctor", help="confere se o worktree está servindo")
    doctor.add_argument("project", nargs="?")
    doctor.add_argument("name", nargs="?")
    _common(doctor, target=False)
    _add_generate(commands)
    which = commands.add_parser("which", help="diz de qual projeto e worktree é um diretório")
    which.add_argument("path", nargs="?", type=Path, default=Path.cwd())
    _common(which, target=False)


def _add_generate(commands: Any) -> None:
    sub = commands.add_parser(
        "generate-config", help="cadastra o projeto de um diretório no config"
    )
    sub.add_argument("path", nargs="?", type=Path, default=Path.cwd(), help="checkout do projeto")
    sub.add_argument("--name", help="nome do projeto no config (padrão: pasta do checkout)")
    sub.add_argument("--base-url-key", help="chave do .env com a URL base, se o wtp não souber")
    sub.add_argument("--print", action="store_true", help="só mostra, não grava no config")
    _common(sub, target=False)
