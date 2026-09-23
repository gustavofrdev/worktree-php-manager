import json
from pathlib import Path

import pytest

from tests.fakes import make_sandbox
from wtp.actions.listing import format_rows, list_rows
from wtp.actions.locate import _worktree_name
from wtp.actions.provision import NewOptions, provision
from wtp.actions.services import Services
from wtp.cli.commands import _generate_text, dispatch
from wtp.cli.main import main
from wtp.cli.parser import build_parser


def test_parser_accepts_agent_friendly_new() -> None:
    args = build_parser().parse_args(
        ["new", "outserv_agenda", "x", "--branch", "feat/x", "-y", "--json"]
    )
    assert (args.project, args.name, args.branch, args.yes, args.json) == (
        "outserv_agenda",
        "x",
        "feat/x",
        True,
        True,
    )


def test_missing_config_prints_message_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["--config", str(tmp_path / "none.toml"), "ls"])
    err = capsys.readouterr().err
    assert code == 1
    assert err.startswith("erro: Config não encontrado") and "Traceback" not in err


def test_listing_shows_managed_worktree(tmp_path: Path) -> None:
    box = make_sandbox(tmp_path)
    provision(box.services, box.services.target("outserv_agenda", "hotfix"), NewOptions())
    rows = list_rows(box.services, None)
    assert [(r.name, r.managed, r.vhost_enabled, r.ahead) for r in rows] == [
        ("hotfix", True, True, 2)
    ]
    assert "http://hotfix.agenda.localhost/" in format_rows(rows)


def test_worktree_name_from_toplevel() -> None:
    root = Path("/home/nk/Projects")
    assert _worktree_name(root / "outserv_agenda-hotfix", "outserv_agenda", root) == "hotfix"
    assert _worktree_name(root / "outserv_agenda", "outserv_agenda", root) is None
    assert _worktree_name(root / "outserv_agenda" / ".claude" / "w", "outserv_agenda", root) is None


def _run_cli(services: Services, argv: list[str]) -> int:
    return dispatch(build_parser().parse_args(argv), services)


def test_cli_new_ls_doctor_rm_json_flow(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    box = make_sandbox(tmp_path)
    assert (
        _run_cli(box.services, ["new", "outserv_agenda", "x", "--branch", "feat/x", "-y", "--json"])
        == 0
    )
    created = json.loads(capsys.readouterr().out)
    assert (created["url"], created["branch"]) == ("http://x.agenda.localhost/", "feat/x")
    assert _run_cli(box.services, ["ls", "outserv_agenda", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["name"] == "x"
    assert _run_cli(box.services, ["rm", "outserv_agenda", "x", "-y", "--json"]) == 0
    assert "worktree" in json.loads(capsys.readouterr().out)["removed"][1]


def test_cli_doctor_without_worktrees(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    box = make_sandbox(tmp_path)
    assert _run_cli(box.services, ["doctor"]) == 0
    assert "Nada para conferir" in capsys.readouterr().out


def test_generate_text_marks_tasks_for_the_agent() -> None:
    payload = {
        "written": False,
        "config": "/c.toml",
        "toml": "[projects.x]\n",
        "notes": ["n"],
        "agent_tasks": ["Descubra a chave."],
    }
    text = _generate_text(payload)
    assert "Não gravado (--print)" in text
    assert "PARA O AGENTE: Descubra a chave." in text


def test_generate_config_flags_parse() -> None:
    args = build_parser().parse_args(
        ["generate-config", "/p", "--base-url-key", "SITE_URL", "--print"]
    )
    assert (args.path, args.base_url_key, args.print) == (Path("/p"), "SITE_URL", True)
