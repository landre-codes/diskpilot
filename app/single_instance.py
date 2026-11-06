"""Garantia de instância única e ativação da janela já aberta."""

from __future__ import annotations

import getpass
import hashlib
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstanceGuard(QObject):
    """Named pipe local para impedir duas instâncias do DiskPilot.

    A segunda instância envia um pedido de ativação para a primeira e encerra.
    O nome inclui o usuário para não conflitar entre sessões do Windows.
    """

    activationRequested = Signal()

    def __init__(self, parent: QObject | None = None, server_name: str | None = None) -> None:
        super().__init__(parent)
        self.server_name = server_name or self._default_name()
        self._server: QLocalServer | None = None
        self._callback = None
        self._pending = False

    @staticmethod
    def _default_name() -> str:
        try:
            user = getpass.getuser()
        except Exception:
            user = "user"
        seed = f"{user}|{Path.home()}"
        digest = hashlib.sha1(seed.encode("utf-8", "ignore")).hexdigest()[:12]
        return f"DiskPilot-{digest}"

    # ------------------------------------------------------------------ API
    def acquire(self) -> bool:
        """Retorna True para a instância principal; False para a secundária."""
        if self._activate_existing():
            return False

        if self._listen():
            return True

        # Pode ser um pipe antigo de um processo que encerrou sem limpar,
        # ou uma corrida com outra inicialização simultânea.
        QLocalServer.removeServer(self.server_name)
        if self._listen():
            return True
        if self._activate_existing():
            return False
        return False

    def set_activation_callback(self, callback) -> None:
        self._callback = callback
        if self._pending:
            self._pending = False
            QTimer.singleShot(0, callback)

    def close(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
        QLocalServer.removeServer(self.server_name)

    # -------------------------------------------------------------- interno
    def _listen(self) -> bool:
        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.UserAccessOption)
        if not server.listen(self.server_name):
            server.deleteLater()
            return False
        server.newConnection.connect(self._on_connection)
        self._server = server
        return True

    def _activate_existing(self) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.server_name, QLocalSocket.WriteOnly)
        if not socket.waitForConnected(250):
            socket.abort()
            return False
        socket.write(b"activate\n")
        socket.waitForBytesWritten(250)
        socket.disconnectFromServer()
        socket.waitForDisconnected(100)
        return True

    def _on_connection(self) -> None:
        if self._server is None:
            return
        while self._server.hasPendingConnections():
            connection = self._server.nextPendingConnection()
            if connection is None:
                continue
            connection.readyRead.connect(
                lambda conn=connection: self._on_activation_data(conn)
            )
            connection.disconnected.connect(connection.deleteLater)
            if connection.bytesAvailable() > 0:
                self._on_activation_data(connection)

    def _on_activation_data(self, connection: QLocalSocket) -> None:
        if connection.property("handled"):
            return
        connection.setProperty("handled", True)
        try:
            if connection.bytesAvailable() > 0:
                connection.readAll()
            self._request_activation()
        finally:
            connection.disconnectFromServer()

    def _request_activation(self) -> None:
        self.activationRequested.emit()
        if self._callback is not None:
            self._callback()
        else:
            self._pending = True
