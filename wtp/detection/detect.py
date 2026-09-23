"""wtp generate-config: descobre o que der pelo código e passa o resto para o agente."""

import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from wtp.adapters.git_ops import common_checkout
from wtp.adapters.runner import CommandRunner
from wtp.core.config import ProjectConfig
from wtp.core.envfile import read_env_value
from wtp.core.errors import WtpError
from wtp.core.frameworks import PROFILES, FrameworkProfile
from wtp.core.naming import VHOST_PREFIX
from wtp.detection.triangulate import Triangulation, triangulate

NAME_LINE = re.compile(r"^\s*Server(?:Name|Alias)\s+(.+)$", re.MULTILINE | re.IGNORECASE)
ROOT_LINE = re.compile(r"^\s*DocumentRoot\s+\"?([^\"\s]+)\"?", re.MULTILINE | re.IGNORECASE)
PHP_SOCKET = re.compile(r"php(\d+\.\d+)-fpm\.sock")
CI4_GROUP = re.compile(r"\$defaultGroup\s*=\s*['\"](\w+)['\"]")
KNOWN_BASE_URL_KEYS = tuple(profile.base_url_key for profile in PROFILES.values())
GENERIC_CONFIG_DIRS = ("app/Config/", "config/")
# Onde o agente deve olhar quando o wtp não acha a URL base sozinho.
BASE_URL_HINTS = (
    ".env.example, env.example, config/app.php, app/Config/App.php, e um grep por "
    "baseURL, base_url, APP_URL, SITE_URL"
)


@dataclass(frozen=True)
class VhostInfo:
    server_names: list[str]
    document_root: Path
    php_version: str | None


@dataclass
class Detection:
    """Projeto detectado, os palpites (notes) e o que o agente precisa resolver (agent_tasks)."""

    project: ProjectConfig
    notes: list[str] = field(default_factory=list)
    agent_tasks: list[str] = field(default_factory=list)


def parse_vhost(text: str) -> VhostInfo | None:
    """Lê nomes, DocumentRoot e versão do PHP de um .conf do Apache.

    Exemplo:
        parse_vhost(Path("/etc/apache2/sites-available/agenda.local.conf").read_text())
    """
    root = ROOT_LINE.search(text)
    if root is None:
        return None
    names = [name for line in NAME_LINE.findall(text) for name in line.split()]
    php = PHP_SOCKET.search(text)
    return VhostInfo(names, Path(root.group(1)), php.group(1) if php else None)


def pick_domain(names: list[str], key: str) -> str:
    """Escolhe o domínio base: o nome .localhost do vhost, ou um derivado dele.

    Exemplo:
        pick_domain(["agenda.local", "agenda.localhost"], "outserv_agenda")  # 'agenda.localhost'
    """
    localhost = [name for name in names if name.endswith(".localhost")]
    if localhost:
        return localhost[0]
    if names:
        return f"{names[0].rsplit('.', 1)[0]}.localhost"
    return f"{key.replace('_', '-').lower()}.localhost"


def base_url_key(env_text: str) -> str | None:
    """Chave de URL base de um framework conhecido presente no .env, ou None.

    Exemplo:
        base_url_key("app.baseURL = 'http://agenda.localhost/'")  # 'app.baseURL'
    """
    found = [key for key in KNOWN_BASE_URL_KEYS if read_env_value(env_text, key) is not None]
    return found[0] if found else None


def db_override_key(checkout: Path, env_text: str) -> str:
    """Chave do .env que troca o banco: grupo padrão do CI4 ou DB_DATABASE do Laravel.

    Exemplo:
        db_override_key(Path("~/Projects/outserv_agenda"), "")  # 'database.dbportal.database'
    """
    database_php = checkout / "app" / "Config" / "Database.php"
    group = CI4_GROUP.search(database_php.read_text()) if database_php.exists() else None
    if group:
        return f"database.{group.group(1)}.database"
    return "DB_DATABASE" if read_env_value(env_text, "DB_DATABASE") is not None else ""


class ProjectDetector:
    """Monta um ProjectConfig a partir do checkout, do vhost existente e do .env.

    Exemplo:
        ProjectDetector(SubprocessRunner(), Path("/etc/apache2/sites-available")).detect(Path.cwd())
    """

    def __init__(
        self, runner: CommandRunner, sites_dir: Path, fpm_dir: Path = Path("/run/php")
    ) -> None:
        self.runner = runner
        self.sites_dir = sites_dir
        self.fpm_dir = fpm_dir

    def detect(
        self, path: Path, key: str | None = None, base_url_key: str | None = None
    ) -> Detection:
        """Detecta o projeto de path; o que o código não mostrar vira tarefa do agente.

        Exemplo:
            detector.detect(Path("~/Projects/produto-main"), base_url_key="APP_URL")
        """
        checkout = self._checkout(path)
        detection = Detection(ProjectConfig(key or checkout.name, checkout, "", ""))
        found = triangulate(checkout, detection.project.env_file)
        profile = self._record_framework(detection, found)
        self._fill_web(detection, self._vhost_for(checkout))
        self._fill_env(detection, base_url_key, profile)
        self._fill_repo(detection, profile)
        return detection

    def _checkout(self, path: Path) -> Path:
        checkout = common_checkout(self.runner, path)
        if checkout is None:
            raise WtpError(
                f"{path} não é um repositório git.", hint="Rode dentro do checkout do projeto."
            )
        return checkout

    def _record_framework(
        self, detection: Detection, found: Triangulation
    ) -> FrameworkProfile | None:
        evidence = "; ".join(found.signals)
        if found.conflict:
            detection.agent_tasks.append(
                f"Os sinais apontam para mais de um framework ({evidence}). Veja o composer.json "
                "e o arquivo de entrada, e ajuste framework no config."
            )
            return None
        if found.framework.value == "":
            detection.notes.append("Framework não reconhecido; usei padrões genéricos.")
            return None
        kind = "confirmado" if found.confirmed else "palpite, confira"
        detection.notes.append(f"Framework {found.framework.value} ({kind}): {evidence}.")
        detection.project = replace(detection.project, framework=found.framework.value)
        return PROFILES[found.framework]

    def _vhost_for(self, checkout: Path) -> VhostInfo | None:
        for conf in sorted(self.sites_dir.glob("*.conf")):
            info = None if conf.name.startswith(VHOST_PREFIX) else parse_vhost(conf.read_text())
            if info and info.document_root.is_relative_to(checkout):
                return info
        return None

    def _fill_web(self, detection: Detection, vhost: VhostInfo | None) -> None:
        project = detection.project
        names = vhost.server_names if vhost else []
        root = vhost.document_root.relative_to(project.main_checkout) if vhost else Path("public")
        php = (vhost.php_version if vhost else None) or self._newest_fpm()
        if vhost is None:
            detection.notes.append(
                "Nenhum vhost aponta para o checkout; derivei o domínio do nome."
            )
        if php is None:
            detection.agent_tasks.append(
                "Não achei a versão do PHP. Leia o require.php do composer.json e os sockets em "
                "/run/php, e ajuste php_version no config."
            )
        detection.project = replace(
            project,
            domain=pick_domain(names, project.key),
            php_version=php or "",
            document_root=str(root) if str(root) != "." else "public",
        )

    def _newest_fpm(self) -> str | None:
        versions = [PHP_SOCKET.search(sock.name) for sock in self.fpm_dir.glob("php*-fpm.sock")]
        found = sorted(
            (m.group(1) for m in versions if m), key=lambda v: tuple(map(int, v.split(".")))
        )
        return found[-1] if found else None

    def _fill_env(
        self, detection: Detection, chosen: str | None, profile: FrameworkProfile | None
    ) -> None:
        project = detection.project
        env_path = project.main_checkout / project.env_file
        env_text = env_path.read_text() if env_path.exists() else ""
        key = chosen or base_url_key(env_text) or (profile.base_url_key if profile else "")
        if not key:
            detection.agent_tasks.append(
                f"Não achei a chave da URL base no {env_path}. Descubra pelo código qual chave "
                f"do .env define a URL base (olhe {BASE_URL_HINTS}) e rode de novo com "
                "--base-url-key <chave>. Só pergunte ao usuário se o código não mostrar."
            )
        detection.project = replace(
            project,
            base_url_key=key,
            db_override_key=db_override_key(project.main_checkout, env_text),
        )

    def _fill_repo(self, detection: Detection, profile: FrameworkProfile | None) -> None:
        project = detection.project
        root = project.main_checkout
        detection.project = replace(
            project,
            main_branch=self._main_branch(root),
            migrations_dir=profile.migrations_dir if profile else project.migrations_dir,
            writable_dirs=profile.writable_dirs if profile else _generic_writable(root),
            ensure_dirs=profile.ensure_dirs if profile else (),
            copy_files=self._ignored_config_files(root, profile),
        )
        if detection.project.copy_files:
            files = ", ".join(detection.project.copy_files)
            detection.notes.append(f"copy_files adivinhado: {files}. Confira.")

    def _main_branch(self, root: Path) -> str:
        args = ["git", "-C", str(root), "symbolic-ref", "--short", "refs/remotes/origin/HEAD"]
        head = self.runner.run(args)
        return (head.stdout.strip().removeprefix("origin/") if head.ok else "") or "main"

    def _ignored_config_files(
        self, root: Path, profile: FrameworkProfile | None
    ) -> tuple[str, ...]:
        # Só arquivos de config ignorados pelo git: vendor, logs e .env ficam de fora.
        dirs = profile.config_dirs if profile else GENERIC_CONFIG_DIRS
        args = ["git", "-C", str(root), "ls-files", "--others", "--ignored", "--exclude-standard"]
        listed = self.runner.run(args).stdout.splitlines()
        return tuple(sorted(f for f in listed if f.startswith(dirs) and f.endswith(".php")))


def _generic_writable(root: Path) -> tuple[str, ...]:
    found = tuple(d for d in ("writable", "storage") if (root / d).is_dir())
    return found or ("writable",)
