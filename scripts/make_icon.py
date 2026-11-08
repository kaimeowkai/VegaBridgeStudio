"""Draw the project's original vector-style icon and wrap a PNG in ICO."""
import os
import struct
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt, QPointF
from PySide6.QtGui import QImage, QPainter, QColor, QPen, QPolygonF
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
image = QImage(256, 256, QImage.Format.Format_ARGB32)
image.fill(Qt.GlobalColor.transparent)
painter = QPainter(image)
painter.setRenderHint(QPainter.RenderHint.Antialiasing)
painter.setPen(Qt.PenStyle.NoPen)
painter.setBrush(QColor("#142536"))
painter.drawRoundedRect(1, 1, 254, 254, 48, 48)
painter.setBrush(QColor("#50d6b7"))
painter.drawPolygon(QPolygonF([QPointF(46, 62), QPointF(90, 62), QPointF(128, 164), QPointF(167, 62), QPointF(211, 62), QPointF(150, 205), QPointF(106, 205)]))
painter.setPen(QPen(QColor("#8dc7ec"), 9))
painter.drawLine(180, 197, 212, 197)
painter.end()
data = QByteArray()
buffer = QBuffer(data)
buffer.open(QIODevice.OpenModeFlag.WriteOnly)
image.save(buffer, "PNG")
png = bytes(data)
root = Path(__file__).resolve().parents[1]
dest = root / "vegabridge/resources/vegabridge.ico"
dest.write_bytes(struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22) + png)
