"""Perfis dos frameworks que o wtp conhece. Fora deles, o wtp pergunta em vez de chutar."""

from dataclasses import dataclass
from enum import Enum


class Framework(Enum):
    CODEIGNITER4 = "codeigniter4"
    LARAVEL = "laravel"
    UNKNOWN = ""


@dataclass(frozen=True)
class FrameworkProfile:
    """O que muda de um framework para outro dentro do worktree."""

    framework: Framework
    composer_package: str
    entry_file: str
    base_url_key: str
    migrations_dir: str
    writable_dirs: tuple[str, ...]
    # Pastas ignoradas pelo git que o app precisa encontrar criadas.
    ensure_dirs: tuple[str, ...] = ()
    config_dirs: tuple[str, ...] = ()
    # Cache de config que faz o framework ignorar o .env novo.
    config_cache_file: str = ""


PROFILES = {
    Framework.CODEIGNITER4: FrameworkProfile(
        framework=Framework.CODEIGNITER4,
        composer_package="codeigniter4/framework",
        entry_file="spark",
        base_url_key="app.baseURL",
        migrations_dir="app/Database/Migrations",
        writable_dirs=("writable",),
        config_dirs=("app/Config/",),
    ),
    Framework.LARAVEL: FrameworkProfile(
        framework=Framework.LARAVEL,
        composer_package="laravel/framework",
        entry_file="artisan",
        base_url_key="APP_URL",
        migrations_dir="database/migrations",
        writable_dirs=("storage", "bootstrap/cache"),
        ensure_dirs=(
            "storage/framework/cache/data",
            "storage/framework/sessions",
            "storage/framework/views",
            "storage/logs",
            "bootstrap/cache",
        ),
        config_dirs=("config/",),
        config_cache_file="bootstrap/cache/config.php",
    ),
}


def profile_for(name: str) -> FrameworkProfile | None:
    """Perfil pelo nome gravado no config, ou None para projeto sem framework conhecido.

    Exemplo:
        profile_for("laravel").base_url_key  # 'APP_URL'
    """
    framework = Framework(name) if name in {f.value for f in Framework} else Framework.UNKNOWN
    return PROFILES.get(framework)
