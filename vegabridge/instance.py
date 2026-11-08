"""One visible Studio per Windows user; subsequent launches activate it."""
import hashlib
from PySide6.QtCore import QObject, QLockFile, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from .storage import user_dir


class SingleInstance(QObject):
    activated = Signal()

    def __init__(self):
        super().__init__()
        self.name = "VegaBridgeStudio-" + hashlib.sha256(str(user_dir()).lower().encode()).hexdigest()[:20]
        self.lock = QLockFile(str(user_dir() / "desktop-instance.lock"))
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._connection)

    def acquire(self):
        if not self.lock.tryLock(100):
            socket = QLocalSocket()
            socket.connectToServer(self.name)
            if socket.waitForConnected(1500):
                socket.write(b"activate")
                socket.waitForBytesWritten(1000)
                socket.disconnectFromServer()
            return False
        QLocalServer.removeServer(self.name)
        if not self.server.listen(self.name):
            self.lock.unlock()
            raise RuntimeError("Could not create the Studio single-instance endpoint")
        return True

    def _connection(self):
        socket = self.server.nextPendingConnection()
        def ready():
            if socket.bytesAvailable():
                socket.readAll()
                self.activated.emit()
                socket.disconnectFromServer()
        socket.readyRead.connect(ready)
        socket.disconnected.connect(socket.deleteLater)
        ready()

    def close(self):
        self.server.close()
        self.lock.unlock()
