"""Requisições HTTP ao Apache local, sem depender de DNS para *.localhost."""

import http.client
from dataclasses import dataclass
from typing import Protocol

READ_LIMIT = 512_000


@dataclass(frozen=True)
class HttpReply:
    status: int
    location: str = ""
    body: str = ""


class HttpProbe(Protocol):
    def get(self, host: str, path: str) -> HttpReply:
        """Faz um GET no Apache local com o Host informado.

        Exemplo:
            probe.get("x.agenda.localhost", "/")
        """
        ...


class LocalHttpProbe:
    """Conecta em 127.0.0.1:80 mandando o Host do worktree.

    Exemplo:
        LocalHttpProbe().get("hotfix.agenda.localhost", "/").status
    """

    def __init__(self, address: str = "127.0.0.1", port: int = 80, timeout: float = 10.0) -> None:
        self.address = address
        self.port = port
        self.timeout = timeout

    def get(self, host: str, path: str) -> HttpReply:
        """GET em 127.0.0.1; erro de conexão vira status 0.

        Exemplo:
            LocalHttpProbe().get("x.agenda.localhost", "/").status
        """
        connection = http.client.HTTPConnection(self.address, self.port, timeout=self.timeout)
        try:
            connection.request("GET", path, headers={"Host": host, "User-Agent": "wtp-doctor"})
            response = connection.getresponse()
            body = response.read(READ_LIMIT).decode("utf-8", errors="replace")
            return HttpReply(response.status, response.getheader("Location", ""), body)
        except OSError as exc:
            return HttpReply(0, body=str(exc))
        finally:
            connection.close()
