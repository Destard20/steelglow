"""Tiny JSON-lines IPC between the running tray app and the ``ckl`` CLI.

Transport: Qt local socket (a named pipe on Windows). Each request is one JSON object per line;
the server answers each with one JSON object per line.
"""
from __future__ import annotations

import json
import logging
from typing import Callable

from PySide6.QtCore import QCoreApplication, QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)

SERVER_NAME = "SteelGlow-instance"
LEGACY_SERVER_NAMES = ("CustomKeyboardLights-instance",)  # pre-rename versions


class IpcServer(QObject):
    def __init__(self, handler: Callable[[dict], dict], parent=None) -> None:
        super().__init__(parent)
        self.handler = handler
        QLocalServer.removeServer(SERVER_NAME)
        self.server = QLocalServer(self)
        if not self.server.listen(SERVER_NAME):
            log.warning("IPC server failed to listen: %s", self.server.errorString())
        self.server.newConnection.connect(self._on_connection)
        self._buffers: dict[QLocalSocket, bytes] = {}

    def _on_connection(self) -> None:
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            self._buffers[sock] = b""
            sock.readyRead.connect(lambda s=sock: self._on_ready(s))
            sock.disconnected.connect(lambda s=sock: self._buffers.pop(s, None))
            sock.disconnected.connect(sock.deleteLater)

    def _on_ready(self, sock: QLocalSocket) -> None:
        buf = self._buffers.get(sock, b"") + bytes(sock.readAll())
        *lines, rest = buf.split(b"\n")
        self._buffers[sock] = rest
        for line in lines:
            if not line.strip():
                continue
            try:
                req = json.loads(line)
                resp = self.handler(req if isinstance(req, dict) else {"cmd": str(req)})
            except Exception as exc:  # noqa: BLE001 - always answer the client
                log.exception("IPC request failed")
                resp = {"ok": False, "error": str(exc)}
            sock.write((json.dumps(resp) + "\n").encode("utf-8"))
            sock.flush()


def send(cmd: dict, timeout_ms: int = 3000) -> dict | None:
    """Send one command to the running app. Returns its reply, or None if no app answered."""
    if QCoreApplication.instance() is None:
        QCoreApplication([])  # needed for Qt sockets; kept alive by Qt as the app instance
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(min(timeout_ms, 1000)):
        return None
    sock.write((json.dumps(cmd) + "\n").encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(timeout_ms)
    buf = b""
    while b"\n" not in buf:
        if not sock.waitForReadyRead(timeout_ms):
            sock.disconnectFromServer()
            return None
        buf += bytes(sock.readAll())
    sock.disconnectFromServer()
    try:
        return json.loads(buf.split(b"\n", 1)[0])
    except ValueError:
        return None


def is_running() -> bool:
    """True if an app instance is listening, including older versions that use a legacy socket
    name or don't answer commands (callers then treat it as outdated and restart it)."""
    if QCoreApplication.instance() is None:
        QCoreApplication([])
    for name in (SERVER_NAME, *LEGACY_SERVER_NAMES):
        sock = QLocalSocket()
        sock.connectToServer(name)
        if sock.waitForConnected(300):
            sock.disconnectFromServer()
            return True
    return False
