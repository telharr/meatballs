"""Source-engine style RCON client (Project Zomboid dedicated server)."""

from __future__ import annotations

import os
import socket
import struct
from dataclasses import dataclass

SERVERDATA_AUTH = 3
SERVERDATA_AUTH_RESPONSE = 2
SERVERDATA_EXECCOMMAND = 2
SERVERDATA_RESPONSE_VALUE = 0


@dataclass
class RconConfig:
    host: str
    port: int
    password: str
    timeout: float = 10.0

    @classmethod
    def from_env(cls) -> RconConfig:
        return cls(
            host=os.environ.get("RCON_HOST", os.environ.get("FTP_HOST", "")).strip(),
            port=int(os.environ.get("RCON_PORT", "16284") or "16284"),
            password=os.environ.get("RCON_PASS", "").strip(),
            timeout=float(os.environ.get("RCON_TIMEOUT", "10") or "10"),
        )

    def validate(self) -> None:
        if not self.host:
            raise ValueError("RCON_HOST is not set")
        if not self.password:
            raise ValueError("RCON_PASS is not set")


def _encode_packet(req_id: int, cmd_type: int, body: str) -> bytes:
    payload = struct.pack("<ii", req_id, cmd_type) + body.encode("utf-8") + b"\x00\x00"
    return struct.pack("<i", len(payload)) + payload


def _recv_packet(sock: socket.socket) -> tuple[int, int, str]:
    size_data = _recv_exact(sock, 4)
    (size,) = struct.unpack("<i", size_data)
    data = _recv_exact(sock, size)
    req_id, cmd_type = struct.unpack("<ii", data[:8])
    body = data[8:-2].decode("utf-8", errors="replace")
    return req_id, cmd_type, body


def _recv_exact(sock: socket.socket, nbytes: int) -> bytes:
    chunks: list[bytes] = []
    received = 0
    while received < nbytes:
        chunk = sock.recv(nbytes - received)
        if not chunk:
            raise ConnectionError("RCON connection closed unexpectedly")
        chunks.append(chunk)
        received += len(chunk)
    return b"".join(chunks)


class RconClient:
    def __init__(self, config: RconConfig) -> None:
        self.config = config

    def execute(self, command: str) -> str:
        self.config.validate()
        command = command.strip()
        if not command:
            raise ValueError("Empty RCON command")

        sock = socket.create_connection(
            (self.config.host, self.config.port),
            timeout=self.config.timeout,
        )
        try:
            sock.settimeout(self.config.timeout)
            sock.sendall(_encode_packet(1, SERVERDATA_AUTH, self.config.password))
            _recv_packet(sock)  # auth response
            sock.sendall(_encode_packet(2, SERVERDATA_EXECCOMMAND, command))
            _recv_packet(sock)
            _, _, response = _recv_packet(sock)
            return response.strip() or "(no output)"
        finally:
            sock.close()


def rcon_execute(command: str) -> str:
    try:
        from panel.servers import rcon_config

        return RconClient(rcon_config()).execute(command)
    except Exception:
        return RconClient(RconConfig.from_env()).execute(command)
