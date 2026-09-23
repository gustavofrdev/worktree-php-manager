from pathlib import Path

import pytest

from tests.fakes import make_project
from wtp.core.errors import WtpError
from wtp.core.naming import make_target, validate_name


@pytest.mark.parametrize("name", ["hotfix", "a", "feat-1", "x9"])
def test_validate_name_accepts_dns_labels(name: str) -> None:
    assert validate_name(name) == name


@pytest.mark.parametrize("name", ["", "-a", "a-", "Feat", "a_b", "a.b", "x" * 41])
def test_validate_name_rejects_bad_labels(name: str) -> None:
    with pytest.raises(WtpError, match="inválido"):
        validate_name(name)


def test_target_derives_paths_and_host() -> None:
    project = make_project(Path("/p/outserv_agenda"))
    target = make_target(project, "hotfix", Path("/home/nk/Projects"))
    assert target.path == Path("/home/nk/Projects/outserv_agenda-hotfix")
    assert target.url == "http://hotfix.agenda.localhost/"
    assert target.vhost_name == "wtp-outserv_agenda-hotfix"
    assert target.document_root == target.path / "public"
    assert target.default_branch == "wtp/hotfix"
