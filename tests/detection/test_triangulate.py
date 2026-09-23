from pathlib import Path

from wtp.detection.triangulate import triangulate

from wtp.core.frameworks import Framework


def _project(tmp_path: Path, composer: str = "", entry: str = "", env: str = "") -> Path:
    if composer:
        (tmp_path / "composer.json").write_text(f'{{"require": {{"{composer}": "^10"}}}}')
    if entry:
        (tmp_path / entry).write_text("#!/usr/bin/env php\n")
    (tmp_path / ".env").write_text(env)
    return tmp_path


def test_three_laravel_signals_confirm(tmp_path: Path) -> None:
    found = triangulate(
        _project(tmp_path, "laravel/framework", "artisan", "APP_URL=http://x\n"), ".env"
    )
    assert (found.framework, found.confirmed) == (Framework.LARAVEL, True)
    assert len(found.signals) == 3


def test_two_codeigniter_signals_confirm(tmp_path: Path) -> None:
    # O agenda não tem codeigniter4/framework no composer (o system/ é versionado).
    found = triangulate(_project(tmp_path, "", "spark", "app.baseURL = 'http://x/'\n"), ".env")
    assert (found.framework, found.confirmed) == (Framework.CODEIGNITER4, True)


def test_single_signal_is_only_a_guess(tmp_path: Path) -> None:
    found = triangulate(_project(tmp_path, entry="artisan"), ".env")
    assert (found.framework, found.confirmed) == (Framework.LARAVEL, False)


def test_no_signal_is_unknown(tmp_path: Path) -> None:
    found = triangulate(_project(tmp_path), ".env")
    assert found.framework is Framework.UNKNOWN and found.signals == []


def test_conflicting_signals_are_unknown(tmp_path: Path) -> None:
    found = triangulate(_project(tmp_path, "laravel/framework", "spark"), ".env")
    assert found.framework is Framework.UNKNOWN
    assert found.conflict
