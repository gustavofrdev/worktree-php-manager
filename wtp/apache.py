"""Vhosts do wtp no Apache: template, instalação e remoção com uma chamada de sudo."""

import tempfile
from dataclasses import dataclass
from pathlib import Path

from wtp.errors import WtpError
from wtp.fpm import php_socket
from wtp.locking import exclusive_lock
from wtp.naming import VHOST_PREFIX, WorktreeTarget
from wtp.runner import CommandRunner

VHOST_MARKER = "# wtp: arquivo gerado pelo wtp. Remova com 'wtp rm', não à mão."
CONFIGTEST_FAILED = 3

# Um único sudo por operação. Se o configtest falhar, volta o arquivo anterior
# (ou tira o novo) e não recarrega, para não derrubar os outros sites.
INSTALL_SCRIPT = r"""
set -u
src="$1"; name="$2"; sites="$3"; marker="$4"
dest="$sites/$name.conf"
case "$name" in wtp-*) ;; *) echo "recusado: $name" >&2; exit 4 ;; esac
if [ -e "$dest" ] && [ "$(head -n 1 "$dest")" != "$marker" ]; then
  echo "sem marca: $dest" >&2; exit 4
fi
backup=""
if [ -e "$dest" ]; then backup="$(mktemp)"; cp "$dest" "$backup"; fi
install -m 644 -o root -g root "$src" "$dest"
a2ensite -q "$name" >/dev/null
if ! apache2ctl configtest; then
  if [ -n "$backup" ]; then
    cp "$backup" "$dest"
  else
    a2dissite -q "$name" >/dev/null; rm -f "$dest"
  fi
  exit 3
fi
systemctl reload apache2
"""

REMOVE_SCRIPT = r"""
set -u
name="$1"; sites="$2"; marker="$3"
case "$name" in wtp-*) ;; *) echo "recusado: $name" >&2; exit 4 ;; esac
if [ -e "$sites/$name.conf" ] && [ "$(head -n 1 "$sites/$name.conf")" != "$marker" ]; then
  echo "sem marca: $sites/$name.conf" >&2; exit 4
fi
a2dissite -q "$name" >/dev/null 2>&1 || true
rm -f "$sites/$name.conf"
apache2ctl configtest && systemctl reload apache2
"""

VHOST_TEMPLATE = """{marker}
<VirtualHost *:80>
    ServerName {host}
    DocumentRoot {docroot}
    <Directory {docroot}>
        Options FollowSymLinks
        AllowOverride All
        Require all granted
    </Directory>
    <FilesMatch \\.php$>
        SetHandler "proxy:unix:{socket}|fcgi://localhost"
    </FilesMatch>
    ErrorLog ${{APACHE_LOG_DIR}}/{host}-error.log
    CustomLog ${{APACHE_LOG_DIR}}/{host}-access.log combined
</VirtualHost>
"""


def render_vhost(target: WorktreeTarget) -> str:
    """Vhost no molde do agenda.local.conf, apontando para o worktree.

    Exemplo:
        render_vhost(target).splitlines()[0] == VHOST_MARKER
    """
    return VHOST_TEMPLATE.format(
        marker=VHOST_MARKER,
        host=target.host,
        docroot=target.document_root,
        socket=php_socket(target.project.php_version),
    )


@dataclass(frozen=True)
class ApachePaths:
    sites_available: Path = Path("/etc/apache2/sites-available")
    sites_enabled: Path = Path("/etc/apache2/sites-enabled")


class ApacheSites:
    """Só mexe em arquivos wtp-*.conf que têm a marca do wtp no topo.

    Exemplo:
        ApacheSites(runner, ApachePaths(), state_dir / "apache.lock").install(target)
    """

    def __init__(self, runner: CommandRunner, paths: ApachePaths, lock_file: Path) -> None:
        self.runner = runner
        self.paths = paths
        self.lock_file = lock_file

    def conf_file(self, name: str) -> Path:
        """Caminho do .conf em sites-available.

        Exemplo:
            apache.conf_file("wtp-outserv_agenda-x")
        """
        return self.paths.sites_available / f"{name}.conf"

    def exists(self, name: str) -> bool:
        """Diz se o .conf existe, seja de quem for.

        Exemplo:
            apache.exists("wtp-outserv_agenda-x")
        """
        return self.conf_file(name).exists()

    def is_enabled(self, name: str) -> bool:
        """Diz se o site está em sites-enabled.

        Exemplo:
            apache.is_enabled("wtp-outserv_agenda-x")
        """
        return (self.paths.sites_enabled / f"{name}.conf").exists()

    def is_ours(self, name: str) -> bool:
        """Diz se o .conf tem o prefixo e a marca do wtp na primeira linha.

        Exemplo:
            apache.is_ours("agenda.local")  # False
        """
        if not name.startswith(VHOST_PREFIX) or not self.exists(name):
            return False
        with self.conf_file(name).open() as handle:
            return handle.readline().rstrip("\n") == VHOST_MARKER

    def installed_content(self, name: str) -> str:
        """Conteúdo atual do .conf, ou vazio se não existe.

        Exemplo:
            apache.installed_content("wtp-outserv_agenda-x")
        """
        return self.conf_file(name).read_text() if self.exists(name) else ""

    def install(self, target: WorktreeTarget) -> None:
        """Instala, habilita, valida e recarrega, numa única chamada de sudo.

        Exemplo:
            apache.install(target)
        """
        name = target.vhost_name
        self._guard(name)
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as staged:
            staged.write(render_vhost(target))
        try:
            sites = str(self.paths.sites_available)
            self._run_script(INSTALL_SCRIPT, staged.name, name, sites, VHOST_MARKER)
        finally:
            Path(staged.name).unlink(missing_ok=True)

    def remove(self, name: str) -> None:
        """Desabilita e apaga um vhost do wtp e recarrega o Apache.

        Exemplo:
            apache.remove("wtp-outserv_agenda-x")
        """
        self._guard(name)
        self._run_script(REMOVE_SCRIPT, name, str(self.paths.sites_available), VHOST_MARKER)

    def _guard(self, name: str) -> None:
        if not name.startswith(VHOST_PREFIX):
            raise WtpError(
                f"Recusei mexer no vhost '{name}': o wtp só mexe em {VHOST_PREFIX}*.conf."
            )
        if self.exists(name) and not self.is_ours(name):
            raise WtpError(
                f"{self.conf_file(name)} existe mas não tem a marca do wtp. Não vou tocar nele.",
                hint="Se ele é de outro projeto, escolha outro nome de worktree.",
            )

    def _run_script(self, script: str, *args: str) -> None:
        with exclusive_lock(self.lock_file):
            result = self.runner.run(["sudo", "-n", "bash", "-c", script, "wtp", *args])
        if result.returncode == CONFIGTEST_FAILED:
            raise WtpError(
                "O apache2ctl configtest falhou; desfiz o vhost e não recarreguei.\n"
                f"{result.output_text()}",
                hint="Rode 'sudo apache2ctl configtest' para ver o erro completo.",
            )
        if not result.ok:
            raise WtpError(
                f"Falhou a etapa do Apache (sudo): {result.output_text()}",
                hint="Confira se 'sudo -n true' funciona sem pedir senha.",
            )
