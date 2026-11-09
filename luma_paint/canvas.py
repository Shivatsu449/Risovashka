"""Pixel-correct drawing canvas; a gesture is committed as one undo step."""
from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QBrush
from PyQt6.QtWidgets import QWidget


class Canvas(QWidget):
    colorPicked = pyqtSignal(QColor)
    positionChanged = pyqtSignal(str)
    zoomRequested = pyqtSignal(int)
    gestureChanged = pyqtSignal(bool)

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document
        self.tool = "brush"
        self.color = QColor("#202630")
        self.pen_width = 6
        self.fill_shapes = False
        self.zoom = 1.0
        self.working = None
        self.start = QPoint()
        self.last = QPoint()
        self.end = QPoint()
        self._stroke_tool = "brush"
        self._stroke_color = QColor(self.color)
        self._stroke_width = self.pen_width
        self._stroke_fill = False
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAccessibleName("Холст для рисования")
        document.changed.connect(self.sync_document)
        self.sync_document()

    def sync_document(self):
        self.setFixedSize(round(self.document.image.width() * self.zoom),
                          round(self.document.image.height() * self.zoom))
        self.update()

    def set_zoom(self, zoom):
        self.finish_gesture()
        self.zoom = max(.1, min(4.0, float(zoom)))
        self.sync_document()

    def _point(self, position, clamp=True):
        p = QPoint(int(position.x() / self.zoom), int(position.y() / self.zoom))
        if clamp:
            p.setX(max(0, min(self.document.image.width() - 1, p.x())))
            p.setY(max(0, min(self.document.image.height() - 1, p.y())))
        return p

    def _pen(self):
        color = QColor("white") if self._stroke_tool == "eraser" else self._stroke_color
        return QPen(color, self._stroke_width, Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)

    def _draw_segment(self, start, end):
        painter = QPainter(self.working)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(self._pen())
            if start == end:
                painter.drawPoint(start)
            else:
                painter.drawLine(start, end)
        finally:
            painter.end()

    def _draw_shape(self, painter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(self._pen())
        painter.setBrush(QBrush(self._stroke_color) if self._stroke_fill else QBrush(Qt.BrushStyle.NoBrush))
        rect = QRectF(QPointF(self.start), QPointF(self.end)).normalized()
        if self._stroke_tool == "line":
            painter.drawLine(self.start, self.end)
        elif self._stroke_tool == "rectangle":
            if self.start == self.end:
                painter.drawPoint(self.start)
            else:
                painter.drawRect(rect)
        elif self._stroke_tool == "ellipse":
            if self.start == self.end:
                painter.drawPoint(self.start)
            else:
                painter.drawEllipse(rect)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.scale(self.zoom, self.zoom)
            painter.drawImage(0, 0, self.working if self.working is not None else self.document.image)
            if self.working is not None and self._stroke_tool in {"line", "rectangle", "ellipse"}:
                self._draw_shape(painter)
        finally:
            painter.end()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus()
        self.finish_gesture()
        point = self._point(event.position())
        if self.tool == "picker":
            self.colorPicked.emit(self.document.image.pixelColor(point))
            return
        self.start = self.last = self.end = point
        self._stroke_tool = self.tool
        self._stroke_color = QColor(self.color)
        self._stroke_width = self.pen_width
        self._stroke_fill = self.fill_shapes
        self.working = QImage(self.document.image)
        if self._stroke_tool in {"brush", "eraser"}:
            self._draw_segment(point, point)
        self.gestureChanged.emit(True)
        self.update()

    def mouseMoveEvent(self, event):
        point = self._point(event.position(), clamp=False)
        if self.document.image.rect().contains(point):
            self.positionChanged.emit(f"X: {point.x()}   Y: {point.y()}")
        else:
            self.positionChanged.emit("")
        if self.working is not None:
            point = self._point(event.position())
            if self._stroke_tool in {"brush", "eraser"}:
                self._draw_segment(self.last, point)
            self.last = self.end = point
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.working is not None:
            self.end = self._point(event.position())
            if self._stroke_tool in {"brush", "eraser"}:
                self._draw_segment(self.last, self.end)
            self.finish_gesture()

    def finish_gesture(self):
        if self.working is None:
            return
        if self._stroke_tool in {"line", "rectangle", "ellipse"}:
            painter = QPainter(self.working)
            try:
                self._draw_shape(painter)
            finally:
                painter.end()
        image, self.working = self.working, None
        self.document.apply(image)
        self.gestureChanged.emit(False)
        self.update()

    def cancel_gesture(self):
        if self.working is not None:
            self.working = None
            self.gestureChanged.emit(False)
            self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_gesture()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoomRequested.emit(1 if event.angleDelta().y() > 0 else -1)
            event.accept()
        else:
            event.ignore()

    def leaveEvent(self, event):
        self.positionChanged.emit("")
        super().leaveEvent(event)

    def focusOutEvent(self, event):
        self.finish_gesture()
        super().focusOutEvent(event)
