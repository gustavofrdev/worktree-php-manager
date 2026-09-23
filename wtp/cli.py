"""Ponto de entrada do wtp. Aqui só se lê argumentos e se roteia."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from wtp import __version__
from wtp.browser import BrowserLauncher
from wtp.config import default_config_path, load_config
from wtp.console import Console
from wtp.doctor import Doctor, all_passed, format_checks
from wtp.errors import WtpError
from wtp.http_probe import LocalHttpProbe
from wtp.listing import format_rows, list_rows
from wtp.locate import locate
from wtp.manifest import default_state_dir
from wtp.naming import WorktreeTarget
from wtp.provision import NewOptions, provision
from wtp.runner import SubprocessRunner
from wtp.services import Services, build_services
from wtp.teardown import teardown


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
    which = commands.add_parser("which", help="diz de qual projeto e worktree é um diretório")
    which.add_argument("path", nargs="?", type=Path, default=Path.cwd())
    _common(which, target=False)


def _emit(args: argparse.Namespace, payload: Any, text: str) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else text)


def _new_options(args: argparse.Namespace, adopt: bool) -> NewOptions:
    return NewOptions(
        base=getattr(args, "base", None),
        branch=getattr(args, "branch", None),
        db=args.db,
        adopt=adopt,
        run_composer=not args.no_composer,
    )


def cmd_new(args: argparse.Namespace, services: Services, adopt: bool = False) -> int:
    """wtp new e wtp adopt: provisiona e imprime path, url e branch.

    Exemplo:
        cmd_new(args, services, adopt=True)
    """
    target = services.target(args.project, args.name)
    report = provision(services, target, _new_options(args, adopt))
    text = f"Pronto: {report.url}\nPasta:  {report.path}\nBranch: {report.branch}"
    _emit(args, report.as_dict(), text)
    return 0


def cmd_rm(args: argparse.Namespace, services: Services) -> int:
    """wtp rm: desfaz o que o wtp criou.

    Exemplo:
        cmd_rm(args, services)
    """
    report = teardown(services, services.target(args.project, args.name), args.delete_branch)
    _emit(args, report.as_dict(), f"Removido {args.project}-{args.name}.")
    return 0


def cmd_ls(args: argparse.Namespace, services: Services) -> int:
    """wtp ls: tabela ou JSON dos worktrees.

    Exemplo:
        cmd_ls(args, services)
    """
    rows = list_rows(services, args.project)
    _emit(args, [row.as_dict() for row in rows], format_rows(rows))
    return 0


def cmd_open(args: argparse.Namespace, services: Services) -> int:
    """wtp open: abre a URL do worktree no navegador do Windows.

    Exemplo:
        cmd_open(args, services)
    """
    target = services.target(args.project, args.name)
    launcher = BrowserLauncher(services.runner).open(target.url)
    _emit(args, {"url": target.url, "launcher": launcher}, f"Abrindo {target.url} com {launcher}.")
    return 0


def cmd_which(args: argparse.Namespace, services: Services) -> int:
    """wtp which: projeto e worktree de um diretório.

    Exemplo:
        cmd_which(args, services)
    """
    found = locate(services, args.path)
    worktree = found.worktree or "(checkout principal ou fora do wtp)"
    text = f"projeto: {found.project}\nworktree: {worktree}"
    _emit(args, found.as_dict(), text)
    return 0


def cmd_doctor(args: argparse.Namespace, services: Services) -> int:
    """wtp doctor: roda as checagens; sai com 1 se alguma falhou.

    Exemplo:
        cmd_doctor(args, services)
    """
    doctor = Doctor(services, LocalHttpProbe())
    targets = _doctor_targets(args, services)
    results = {target.slug: doctor.check(target) for target in targets}
    payload = {
        slug: [{"check": r.label, "status": r.status.value, "detail": r.detail} for r in checks]
        for slug, checks in results.items()
    }
    text = "\n\n".join(format_checks(t, results[t.slug]) for t in targets) or "Nada para conferir."
    _emit(args, payload, text)
    return 0 if all(all_passed(checks) for checks in results.values()) else 1


def _doctor_targets(args: argparse.Namespace, services: Services) -> list[WorktreeTarget]:
    if args.project and args.name:
        return [services.target(args.project, args.name)]
    manifests = services.manifests.all_for(args.project)
    return [services.target(m.project, m.name) for m in manifests]


def dispatch(args: argparse.Namespace, services: Services) -> int:
    """Roteia o subcomando para a função certa.

    Exemplo:
        dispatch(build_parser().parse_args(["ls"]), services)
    """
    match args.command:
        case "new":
            return cmd_new(args, services)
        case "adopt":
            return cmd_new(args, services, adopt=True)
        case "rm":
            return cmd_rm(args, services)
        case "ls":
            return cmd_ls(args, services)
        case "open":
            return cmd_open(args, services)
        case "doctor":
            return cmd_doctor(args, services)
        case "which":
            return cmd_which(args, services)
    raise WtpError(f"Comando desconhecido: {args.command}.")


def _services(args: argparse.Namespace) -> Services:
    config = load_config((args.config or default_config_path()).expanduser())
    console = Console(assume_yes=getattr(args, "yes", False))
    return build_services(config, SubprocessRunner(), console, default_state_dir())


def main(argv: list[str] | None = None) -> int:
    """Roda a CLI e devolve o código de saída.

    Exemplo:
        main(["ls", "outserv_agenda"])
    """
    args = build_parser().parse_args(argv)
    try:
        return dispatch(args, _services(args))
    except WtpError as error:
        return _report_error(error)
    except KeyboardInterrupt:
        print("\nInterrompido.", file=sys.stderr)
        return 130
    except Exception as error:
        if args.debug:
            raise
        print(f"erro inesperado: {error!r}\ndica: rode de novo com --debug.", file=sys.stderr)
        return 2


def _report_error(error: WtpError) -> int:
    print(f"erro: {error.message}", file=sys.stderr)
    if error.hint:
        print(f"dica: {error.hint}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
