"""Ponto de entrada do wtp: monta os Services, roda o comando e trata os erros."""

import argparse
import sys

from wtp.actions.services import Services, build_services
from wtp.adapters.console import Console
from wtp.adapters.runner import SubprocessRunner
from wtp.cli.commands import cmd_generate_config, dispatch
from wtp.cli.parser import build_parser
from wtp.core.config import default_config_path, load_config
from wtp.core.errors import WtpError
from wtp.core.manifest import default_state_dir


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
        # generate-config roda antes de existir config, então não monta os Services.
        if args.command == "generate-config":
            return cmd_generate_config(args)
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
