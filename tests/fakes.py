"""Versões falsas e nomeadas dos efeitos colaterais: git, sudo/Apache e HTTP."""

import io
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from wtp.apache import ApachePaths
from wtp.config import ProjectConfig, WtpConfig
from wtp.console import Console
from wtp.http_probe import HttpReply
from wtp.runner import CommandResult
from wtp.services import Services, build_services

Effect = Callable[[tuple[str, ...], Path | None], CommandResult]


def _contains(args: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    size = len(needle)
    return any(args[i : i + size] == needle for i in range(len(args) - size + 1))


class ScriptedRunner:
    """Responde comandos por trechos da linha de comando; o resto sai com código 0."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.rules: list[tuple[tuple[str, ...], Effect]] = []

    def on(self, *needle: str, effect: Effect) -> None:
        self.rules.insert(0, (needle, effect))

    def reply(self, *needle: str, stdout: str = "", returncode: int = 0) -> None:
        self.on(*needle, effect=lambda args, _cwd: CommandResult(args, returncode, stdout, ""))

    def run(self, args: Sequence[str], cwd: Path | None = None) -> CommandResult:
        command = tuple(args)
        self.calls.append(command)
        for needle, effect in self.rules:
            if _contains(command, needle):
                return effect(command, cwd)
        return CommandResult(command, 0)

    def count(self, *needle: str) -> int:
        return sum(1 for call in self.calls if _contains(call, needle))


@dataclass
class FakeGitWorld:
    """Simula os worktrees de um repo: `worktree add` cria a pasta de verdade no tmp_path."""

    runner: ScriptedRunner
    main: Path
    worktrees: dict[Path, str] = field(default_factory=dict)
    branches: set[str] = field(default_factory=lambda: {"main"})
    dirty: dict[Path, list[str]] = field(default_factory=dict)
    # Branches com commits que a base não tem (nem o HEAD do checkout principal).
    unmerged: set[str] = field(default_factory=set)

    def install(self) -> "FakeGitWorld":
        self.worktrees.setdefault(self.main, "main")
        self.runner.on("worktree", "list", effect=self._list)
        self.runner.on("worktree", "add", effect=self._add)
        self.runner.on("worktree", "remove", effect=self._remove)
        self.runner.on("show-ref", effect=self._show_ref)
        self.runner.on("status", "--porcelain", effect=self._status)
        self.runner.on("merge-base", "--is-ancestor", effect=self._is_ancestor)
        self.runner.on("branch", "-d", effect=self._is_ancestor)
        self.runner.reply("rev-parse", "--verify", stdout="0f99c7f\n")
        self.runner.on("rev-parse", "--abbrev-ref", effect=self._current_branch)
        self.runner.reply("rev-list", stdout="1\t2\n")
        return self

    def _list(self, args: tuple[str, ...], _cwd: Path | None) -> CommandResult:
        blocks = [
            f"worktree {p}\nHEAD abc\nbranch refs/heads/{b}\n" for p, b in self.worktrees.items()
        ]
        return CommandResult(args, 0, "\n".join(blocks))

    def _add(self, args: tuple[str, ...], _cwd: Path | None) -> CommandResult:
        new_branch = "-b" in args
        branch = args[args.index("-b") + 1] if new_branch else args[-1]
        path = Path(args[args.index("-b") + 2] if new_branch else args[-2])
        path.mkdir(parents=True)
        (path / "writable").mkdir()
        self.worktrees[path] = branch
        self.branches.add(branch)
        return CommandResult(args, 0)

    def _remove(self, args: tuple[str, ...], _cwd: Path | None) -> CommandResult:
        path = Path(args[-1])
        del self.worktrees[path]
        for child in sorted(path.rglob("*"), reverse=True):
            child.rmdir() if child.is_dir() else child.unlink()
        path.rmdir()
        return CommandResult(args, 0)

    def _show_ref(self, args: tuple[str, ...], _cwd: Path | None) -> CommandResult:
        branch = args[-1].removeprefix("refs/heads/")
        return CommandResult(args, 0 if branch in self.branches else 1)

    def _is_ancestor(self, args: tuple[str, ...], _cwd: Path | None) -> CommandResult:
        named = [a.removeprefix("refs/heads/") for a in args]
        return CommandResult(args, 1 if self.unmerged & set(named) else 0)

    def _status(self, args: tuple[str, ...], _cwd: Path | None) -> CommandResult:
        path = Path(args[args.index("-C") + 1])
        return CommandResult(args, 0, "\n".join(self.dirty.get(path, [])))

    def _current_branch(self, args: tuple[str, ...], _cwd: Path | None) -> CommandResult:
        path = Path(args[args.index("-C") + 1])
        return CommandResult(args, 0, self.worktrees.get(path, "?") + "\n")


@dataclass
class FakeApacheHost:
    """Faz o papel do sudo + a2ensite/a2dissite + reload, dentro do tmp_path."""

    runner: ScriptedRunner
    paths: ApachePaths
    configtest_ok: bool = True

    def install(self) -> "FakeApacheHost":
        self.paths.sites_available.mkdir(parents=True, exist_ok=True)
        self.paths.sites_enabled.mkdir(parents=True, exist_ok=True)
        self.runner.on("sudo", "-n", "bash", effect=self._sudo)
        return self

    def _sudo(self, args: tuple[str, ...], _cwd: Path | None) -> CommandResult:
        script_args = args[args.index("wtp") + 1 :]
        if "install -m 644" in args[4]:
            return self._install(args, script_args[0], script_args[1])
        if "a2dissite" in args[4]:
            return self._remove(args, script_args[0])
        return CommandResult(args, 0)

    def _install(self, args: tuple[str, ...], source: str, name: str) -> CommandResult:
        if not self.configtest_ok:
            return CommandResult(args, 3, "", "Syntax error on line 1")
        conf = self.paths.sites_available / f"{name}.conf"
        conf.write_text(Path(source).read_text())
        link = self.paths.sites_enabled / f"{name}.conf"
        if not link.exists():
            link.symlink_to(conf)
        return CommandResult(args, 0)

    def _remove(self, args: tuple[str, ...], name: str) -> CommandResult:
        (self.paths.sites_enabled / f"{name}.conf").unlink(missing_ok=True)
        (self.paths.sites_available / f"{name}.conf").unlink(missing_ok=True)
        return CommandResult(args, 0)


@dataclass
class CannedHttpProbe:
    """Devolve respostas fixas por (host, caminho)."""

    replies: dict[tuple[str, str], HttpReply] = field(default_factory=dict)
    requests: list[tuple[str, str]] = field(default_factory=list)

    def get(self, host: str, path: str) -> HttpReply:
        self.requests.append((host, path))
        return self.replies.get((host, path), HttpReply(404))


@dataclass
class Sandbox:
    services: Services
    runner: ScriptedRunner
    git: FakeGitWorld
    apache: FakeApacheHost
    project: ProjectConfig
    console_output: io.StringIO


def make_project(main: Path, copy_files: tuple[str, ...] = ()) -> ProjectConfig:
    return ProjectConfig(
        key="outserv_agenda",
        main_checkout=main,
        domain="agenda.localhost",
        php_version="8.1",
        db_override_key="database.dbportal.database",
        copy_files=copy_files,
    )


def write_pool(php_root: Path, user: str = "nk") -> None:
    pool = php_root / "8.1" / "fpm" / "pool.d"
    pool.mkdir(parents=True)
    (pool / "www.conf").write_text(f"[www]\nuser = {user}\ngroup = {user}\n")


def make_sandbox(
    tmp_path: Path, assume_yes: bool = True, pool_user: str = "", copy_files: tuple[str, ...] = ()
) -> Sandbox:
    import getpass

    main = tmp_path / "Projects" / "outserv_agenda"
    (main / ".git").mkdir(parents=True)
    (main / ".env").write_text(
        "CI_ENVIRONMENT = development\napp.baseURL = 'http://agenda.localhost/'\n"
    )
    write_pool(tmp_path / "php", pool_user or getpass.getuser())
    project = make_project(main, copy_files)
    config = WtpConfig({project.key: project}, tmp_path / "Projects", tmp_path / "config.toml")
    runner = ScriptedRunner()
    output = io.StringIO()
    console = Console(assume_yes=assume_yes, out=output, answer_source=io.StringIO())
    paths = ApachePaths(tmp_path / "sites-available", tmp_path / "sites-enabled")
    services = build_services(config, runner, console, tmp_path / "state", paths, tmp_path / "php")
    git = FakeGitWorld(runner, main).install()
    apache = FakeApacheHost(runner, paths).install()
    return Sandbox(services, runner, git, apache, project, output)
