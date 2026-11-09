"""Image storage, bounded history and transactional file operations."""
from pathlib import Path

from PyQt6.QtCore import QObject, QIODevice, QSaveFile, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QImageReader, QImageWriter, QPainter

MAX_PIXELS = 16_000_000
MAX_SIDE = 8192
HISTORY_BYTES = 128 * 1024 * 1024
HISTORY_STEPS = 30
FORMATS = {".png": b"png", ".jpg": b"jpeg", ".jpeg": b"jpeg", ".bmp": b"bmp"}


def validate_size(width: int, height: int) -> None:
    if not (1 <= width <= MAX_SIDE and 1 <= height <= MAX_SIDE):
        raise ValueError(f"Размер стороны должен быть от 1 до {MAX_SIDE} пикселей.")
    if width * height > MAX_PIXELS:
        raise ValueError("Размер холста не должен превышать 16 миллионов пикселей.")


def blank_image(width: int, height: int) -> QImage:
    validate_size(width, height)
    image = QImage(width, height, QImage.Format.Format_RGB32)
    if image.isNull():
        raise MemoryError("Не хватает памяти для холста.")
    image.fill(QColor("white"))
    return image


def load_image(filename: str) -> QImage:
    reader = QImageReader(filename)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid():
        validate_size(size.width(), size.height())
    image = reader.read()
    if image.isNull():
        raise ValueError("Не удалось открыть изображение: " + reader.errorString())
    validate_size(image.width(), image.height())
    # The editor has an opaque white paper, including when importing transparent PNGs.
    paper = blank_image(image.width(), image.height())
    painter = QPainter(paper)
    try:
        painter.drawImage(0, 0, image)
    finally:
        painter.end()
    return paper


def save_image(image: QImage, filename: str) -> None:
    image_format = FORMATS.get(Path(filename).suffix.lower())
    if image_format is None:
        raise ValueError("Выберите формат PNG, JPG или BMP и соответствующее расширение.")
    target = QSaveFile(filename)
    if not target.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError("Не удалось создать файл: " + target.errorString())
    writer = QImageWriter(target, image_format)
    writer.setQuality(95)
    if not writer.write(image):
        message = writer.errorString()
        target.cancelWriting()
        raise OSError("Не удалось записать изображение: " + message)
    if not target.commit():
        raise OSError("Не удалось сохранить файл: " + target.errorString())


class Document(QObject):
    changed = pyqtSignal()

    def __init__(self, width=1200, height=800, *, history_bytes=HISTORY_BYTES):
        super().__init__()
        self.image = blank_image(width, height)
        self.filename = ""
        self.undo_stack = []
        self.redo_stack = []
        self.history_bytes = history_bytes
        self.revision = 0
        self.saved_revision = 0
        self._next_revision = 1

    @property
    def dirty(self):
        return self.revision != self.saved_revision

    def _snapshot(self):
        # QImage uses copy-on-write. Editing a canvas detaches its working copy.
        return (QImage(self.image), self.revision)

    def _trim(self):
        while self.undo_stack and (
            len(self.undo_stack) > HISTORY_STEPS
            or sum(im.sizeInBytes() for im, _ in self.undo_stack + self.redo_stack) > self.history_bytes
        ):
            self.undo_stack.pop(0)
        while self.redo_stack and sum(
            im.sizeInBytes() for im, _ in self.undo_stack + self.redo_stack
        ) > self.history_bytes:
            self.redo_stack.pop(0)

    def apply(self, image):
        if image.isNull():
            raise ValueError("Пустое изображение не может заменить холст.")
        validate_size(image.width(), image.height())
        if image == self.image:
            return False
        self.undo_stack.append(self._snapshot())
        self.redo_stack.clear()
        self.image = QImage(image)
        self.revision = self._next_revision
        self._next_revision += 1
        self._trim()
        self.changed.emit()
        return True

    def reset(self, image, filename=""):
        if image.isNull():
            raise ValueError("Нельзя открыть пустое изображение.")
        validate_size(image.width(), image.height())
        self.image = QImage(image)
        self.filename = filename
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.revision = self._next_revision
        self.saved_revision = self.revision
        self._next_revision += 1
        self.changed.emit()

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self._snapshot())
            self.image, self.revision = self.undo_stack.pop()
            self._trim()
            self.changed.emit()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self._snapshot())
            self.image, self.revision = self.redo_stack.pop()
            self._trim()
            self.changed.emit()

    def save(self, filename):
        save_image(self.image, filename)
        self.filename = filename
        self.saved_revision = self.revision
        self.changed.emit()
