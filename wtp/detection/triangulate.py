"""Descobre o framework cruzando três sinais independentes, em vez de confiar em um só."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from wtp.core.envfile import read_env_value
from wtp.core.frameworks import PROFILES, Framework, FrameworkProfile

# Com dois sinais concordando, o wtp confia. Com um, é palpite e vai para as notas.
CONFIRMED_SIGNALS = 2


@dataclass(frozen=True)
class Triangulation:
    framework: Framework
    signals: list[str] = field(default_factory=list)
    confirmed: bool = False
    conflict: bool = False


def triangulate(checkout: Path, env_file: str) -> Triangulation:
    """Vota entre os frameworks conhecidos: composer.json, arquivo de entrada e chave do .env.

    Exemplo:
        triangulate(Path("~/Projects/produto-main"), ".env").framework  # Framework.LARAVEL
    """
    requires = _composer_requires(checkout)
    env_path = checkout / env_file
    env_text = env_path.read_text() if env_path.is_file() else ""
    votes = {fw: _signals(checkout, requires, env_text, p) for fw, p in PROFILES.items()}
    voting = {fw: signals for fw, signals in votes.items() if signals}
    if len(voting) != 1:
        every = [signal for signals in voting.values() for signal in signals]
        return Triangulation(Framework.UNKNOWN, every, conflict=len(voting) > 1)
    framework, signals = next(iter(voting.items()))
    return Triangulation(framework, signals, confirmed=len(signals) >= CONFIRMED_SIGNALS)


def _signals(
    checkout: Path, requires: set[str], env_text: str, profile: FrameworkProfile
) -> list[str]:
    found = []
    if profile.composer_package in requires:
        found.append(f"composer.json exige {profile.composer_package}")
    if (checkout / profile.entry_file).is_file():
        found.append(f"tem o arquivo {profile.entry_file}")
    if read_env_value(env_text, profile.base_url_key) is not None:
        found.append(f".env tem {profile.base_url_key}")
    return found


def _composer_requires(checkout: Path) -> set[str]:
    composer = checkout / "composer.json"
    try:
        manifest = json.loads(composer.read_text()) if composer.is_file() else {}
    except ValueError:
        return set()
    return {*manifest.get("require", {}), *manifest.get("require-dev", {})}
