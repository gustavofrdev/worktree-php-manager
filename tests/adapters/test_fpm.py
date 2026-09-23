from pathlib import Path

from tests.fakes import write_pool
from wtp.adapters.fpm import PoolIdentity, parse_pool, php_socket, pool_identity


def test_parse_pool_reads_user_and_group() -> None:
    assert parse_pool("[www]\nuser = nk\ngroup = web\n") == PoolIdentity("nk", "web")


def test_parse_pool_defaults_group_to_user_and_skips_comments() -> None:
    assert parse_pool(";user = x\nuser = nk\n") == PoolIdentity("nk", "nk")
    assert parse_pool("listen = /x\n") is None


def test_pool_identity_reads_pool_dir(tmp_path: Path) -> None:
    write_pool(tmp_path, "someone")
    assert pool_identity("8.1", tmp_path) == PoolIdentity("someone", "someone")
    assert pool_identity("8.4", tmp_path) is None


def test_php_socket_path() -> None:
    assert php_socket("8.2") == "/run/php/php8.2-fpm.sock"
