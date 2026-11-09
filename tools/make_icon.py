"""Generate a local application icon without downloading artwork."""
from pathlib import Path
import struct
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPainterPath


def make_icon(destination):
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#252936"))
    painter.drawRoundedRect(QRectF(0, 0, 256, 256), 54, 54)
    painter.setPen(QPen(QColor("#bda5fa"), 25, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(QPointF(73, 65), QPointF(73, 186))
    painter.drawLine(QPointF(73, 186), QPointF(182, 186))
    painter.setPen(QPen(QColor("#ebddff"), 22, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(QPointF(114, 139), QPointF(180, 72))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#a58bec"))
    brush = QPainterPath(QPointF(107, 145))
    brush.cubicTo(126, 154, 107, 177, 94, 169)
    brush.cubicTo(107, 166, 92, 158, 107, 145)
    painter.drawPath(brush)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("Cannot generate icon")
    buffer.close()
    payload = bytes(data)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(payload), 22) + payload)


if __name__ == "__main__":
    make_icon(Path(__file__).resolve().parents[1] / "assets" / "icon.ico")
