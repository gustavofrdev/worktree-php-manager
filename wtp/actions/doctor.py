"""wtp doctor: confere se um worktree está pronto para abrir no navegador."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import urlsplit

from wtp.actions.services import Services
from wtp.adapters.apache import render_vhost
from wtp.adapters.fpm import php_socket, pool_identity
from wtp.adapters.http_probe import HttpProbe, HttpReply
from wtp.adapters.permissions import pool_can_write
from wtp.core.envfile import read_env_value
from wtp.core.frameworks import profile_for
from wtp.core.naming import WorktreeTarget

OK_STATUSES = {200, 301, 302, 303, 307, 308}
ASSET_LINK = re.compile(r"""(?:src|href)=["']([^"']*/assets/[^"']+)["']""")


class CheckStatus(Enum):
    OK = "ok"
    WARN = "aviso"
    FAIL = "falha"


@dataclass(frozen=True)
class CheckResult:
    label: str
    status: CheckStatus
    detail: str = ""


def _check(label: str, passed: bool, detail: str = "", soft: bool = False) -> CheckResult:
    failed = CheckStatus.WARN if soft else CheckStatus.FAIL
    return CheckResult(label, CheckStatus.OK if passed else failed, "" if passed else detail)


class Doctor:
    """Roda as checagens de um worktree, da mais básica (pasta) à mais completa (assets).

    Exemplo:
        Doctor(services, LocalHttpProbe()).check(services.target("outserv_agenda", "hotfix"))
    """

    def __init__(self, services: Services, probe: HttpProbe) -> None:
        self.services = services
        self.probe = probe

    def check(self, target: WorktreeTarget) -> list[CheckResult]:
        """Roda as checagens em ordem; sem pasta, para na primeira.

        Exemplo:
            doctor.check(services.target("outserv_agenda", "hotfix"))
        """
        if not target.path.is_dir():
            return [_check("pasta do worktree", False, f"{target.path} não existe")]
        steps: list[Callable[[WorktreeTarget], CheckResult]] = [
            self._env_base_url,
            self._local_files,
            self._vhost_file,
            self._vhost_enabled,
            self._fpm_socket,
            self._writable,
            self._framework_cache,
            self._http_root,
            self._assets,
        ]
        return [step(target) for step in steps]

    def _env_base_url(self, target: WorktreeTarget) -> CheckResult:
        env_path = target.path / target.project.env_file
        if not env_path.exists():
            return _check(".env e baseURL", False, f"{env_path} não existe; rode wtp new de novo")
        if not target.project.base_url_key:
            detail = f"sem base_url_key no config; confira à mão se a URL base é {target.url}"
            return _check(".env e baseURL", False, detail, soft=True)
        found = read_env_value(env_path.read_text(), target.project.base_url_key)
        detail = f"{target.project.base_url_key} = {found!r}, esperado {target.url!r}"
        return _check(".env e baseURL", found == target.url, detail)

    def _local_files(self, target: WorktreeTarget) -> CheckResult:
        missing = [f for f in target.project.copy_files if not (target.path / f).exists()]
        detail = f"faltam {', '.join(missing)}; rode wtp new (ou adopt) de novo"
        return _check("arquivos locais (copy_files)", not missing, detail)

    def _vhost_file(self, target: WorktreeTarget) -> CheckResult:
        apache = self.services.apache
        name = target.vhost_name
        if not apache.is_ours(name):
            return _check("vhost", False, f"{apache.conf_file(name)} não existe ou não é do wtp")
        current = apache.installed_content(name) == render_vhost(target)
        return _check(
            "vhost", current, "conteúdo diferente do template; rode wtp new de novo", soft=True
        )

    def _vhost_enabled(self, target: WorktreeTarget) -> CheckResult:
        enabled = self.services.apache.is_enabled(target.vhost_name)
        return _check("vhost habilitado", enabled, f"rode: sudo a2ensite {target.vhost_name}")

    def _fpm_socket(self, target: WorktreeTarget) -> CheckResult:
        socket = php_socket(target.project.php_version)
        return _check("socket do PHP-FPM", Path(socket).exists(), f"{socket} não existe")

    def _writable(self, target: WorktreeTarget) -> CheckResult:
        identity = pool_identity(target.project.php_version, self.services.php_root)
        if identity is None:
            return _check(
                "pastas graváveis", False, f"sem pool do PHP {target.project.php_version}"
            )
        dirs = [target.path / d for d in target.project.writable_dirs]
        blocked = [str(d) for d in dirs if not d.exists() or not pool_can_write(d, identity)]
        return _check(
            "pastas graváveis", not blocked, f"{identity.user} não grava em {', '.join(blocked)}"
        )

    def _framework_cache(self, target: WorktreeTarget) -> CheckResult:
        profile = profile_for(target.project.framework)
        cache = (
            target.path / profile.config_cache_file
            if profile and profile.config_cache_file
            else None
        )
        stale = cache is not None and cache.exists()
        detail = (
            f"{cache} faz o framework ignorar o .env; rode php artisan config:clear no worktree"
        )
        return _check("cache de config do Laravel", not stale, detail, soft=True)

    def _http_root(self, target: WorktreeTarget) -> CheckResult:
        reply = self.probe.get(target.host, "/")
        detail = f"{target.url} respondeu {reply.status or reply.body}"
        return _check("HTTP", reply.status in OK_STATUSES, detail)

    def _assets(self, target: WorktreeTarget) -> CheckResult:
        page = self._landing_page(target)
        match = ASSET_LINK.search(page.body)
        if match is None:
            return _check("assets", False, "nenhum link para /assets/ na página inicial", soft=True)
        link = urlsplit(match.group(1))
        if link.netloc and link.netloc != target.host:
            return _check(
                "assets", False, f"asset aponta para {link.netloc}, esperado {target.host}"
            )
        status = self.probe.get(target.host, link.path).status
        return _check("assets", status == 200, f"{link.path} respondeu {status}")

    def _landing_page(self, target: WorktreeTarget) -> HttpReply:
        reply = self.probe.get(target.host, "/")
        location = urlsplit(reply.location)
        if reply.status in OK_STATUSES - {200} and location.netloc in {"", target.host}:
            return self.probe.get(target.host, location.path or "/")
        return reply


def format_checks(target: WorktreeTarget, results: list[CheckResult]) -> str:
    """Texto para o terminal com uma linha por checagem.

    Exemplo:
        print(format_checks(target, results))
    """
    lines = [f"{target.slug}  {target.url}"]
    for result in results:
        suffix = f": {result.detail}" if result.detail else ""
        lines.append(f"  [{result.status.value:>5}] {result.label}{suffix}")
    return "\n".join(lines)


def all_passed(results: list[CheckResult]) -> bool:
    """Verdadeiro se nenhuma checagem falhou (aviso não conta).

    Exemplo:
        all_passed(results)
    """
    return all(result.status is not CheckStatus.FAIL for result in results)
