"""Linha de comando do composer com o PHP do projeto, não o php padrão da máquina."""

import shutil


def composer_install_command(php_version: str) -> list[str]:
    """composer install rodando com php<versão>, se esse binário existir.

    Os scripts do composer (por exemplo o package:discover do Laravel) usam o mesmo
    PHP que roda o composer, então a versão errada quebra a instalação.

    Exemplo:
        composer_install_command("8.4")  # ['/usr/bin/php8.4', '/usr/local/bin/composer', ...]
    """
    flags = ["install", "--no-interaction", "--no-progress"]
    php = shutil.which(f"php{php_version}")
    composer = shutil.which("composer")
    if php and composer:
        return [php, composer, *flags]
    return ["composer", *flags]
