import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from wtp.http_probe import LocalHttpProbe


class _EchoHost(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (nome exigido pelo http.server)
        body = f"host={self.headers['Host']} path={self.path}".encode()
        self.send_response(307)
        self.send_header("Location", "/acesso/login")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return None


@pytest.fixture
def local_server() -> Iterator[int]:
    server = HTTPServer(("127.0.0.1", 0), _EchoHost)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()


def test_probe_sends_worktree_host_header(local_server: int) -> None:
    reply = LocalHttpProbe(port=local_server).get("x.agenda.localhost", "/a")
    assert (reply.status, reply.location) == (307, "/acesso/login")
    assert reply.body == "host=x.agenda.localhost path=/a"


def test_probe_reports_connection_error_as_status_zero() -> None:
    reply = LocalHttpProbe(port=1, timeout=1).get("x.localhost", "/")
    assert reply.status == 0 and reply.body
