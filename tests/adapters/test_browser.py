import pytest

from tests.fakes import ScriptedRunner
from wtp.adapters.browser import BrowserLauncher
from wtp.core.errors import WtpError


def test_open_uses_first_available_launcher(monkeypatch: pytest.MonkeyPatch) -> None:
    available = {"explorer.exe", "xdg-open"}
    monkeypatch.setattr(
        "wtp.adapters.browser.shutil.which", lambda name: name if name in available else None
    )
    runner = ScriptedRunner()
    assert BrowserLauncher(runner).open("http://x.agenda.localhost/") == "explorer.exe"
    assert runner.calls == [("explorer.exe", "http://x.agenda.localhost/")]


def test_open_without_launcher_explains(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("wtp.adapters.browser.shutil.which", lambda _name: None)
    with pytest.raises(WtpError, match="Não achei como abrir"):
        BrowserLauncher(ScriptedRunner()).open("http://x/")
