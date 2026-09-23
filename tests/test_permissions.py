from wtp.permissions import GRANT_SCRIPT


def test_grant_script_never_follows_symlinks() -> None:
    # Regressão: um symlink versionado em writable/ apontando para /etc fazia o
    # chgrp -R (com sudo) mudar o grupo do alvo. -h -P mexe só no link.
    assert "chgrp -R -h -P" in GRANT_SCRIPT
