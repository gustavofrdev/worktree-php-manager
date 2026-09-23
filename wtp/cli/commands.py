"""Uma função por subcomando: chama a ação e imprime texto ou JSON."""

import argparse
import json
from typing import Any

from wtp.actions.doctor import Doctor, all_passed, format_checks
from wtp.actions.listing import format_rows, list_rows
from wtp.actions.locate import locate
from wtp.actions.provision import NewOptions, provision
from wtp.actions.services import Services
from wtp.actions.teardown import teardown
from wtp.adapters.apache import ApachePaths
from wtp.adapters.browser import BrowserLauncher
from wtp.adapters.http_probe import LocalHttpProbe
from wtp.adapters.runner import SubprocessRunner
from wtp.core.config import default_config_path
from wtp.core.errors import WtpError
from wtp.core.naming import WorktreeTarget
from wtp.detection.config_writer import add_project, render_project
from wtp.detection.detect import ProjectDetector


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


def cmd_generate_config(args: argparse.Namespace) -> int:
    """wtp generate-config: detecta o projeto, grava no config e lista o que falta perguntar.

    Exemplo:
        cmd_generate_config(build_parser().parse_args(["generate-config", "--print"]))
    """
    detector = ProjectDetector(SubprocessRunner(), ApachePaths().sites_available)
    found = detector.detect(args.path, args.name, args.base_url_key)
    config_path = (args.config or default_config_path()).expanduser()
    written = not args.print
    if written:
        add_project(config_path, found.project, found.project.main_checkout.parent)
    payload = {
        "config": str(config_path),
        "written": written,
        "project": found.project.key,
        "toml": render_project(found.project),
        "notes": found.notes,
        "agent_tasks": found.agent_tasks,
    }
    _emit(args, payload, _generate_text(payload))
    return 0


def _generate_text(payload: dict[str, Any]) -> str:
    action = "Gravado em" if payload["written"] else "Não gravado (--print). Seria gravado em"
    lines = [f"{action} {payload['config']}:", "", payload["toml"]]
    lines += [f"nota: {note}" for note in payload["notes"]]
    lines += [f"PARA O AGENTE: {task}" for task in payload["agent_tasks"]]
    return "\n".join(lines)


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
