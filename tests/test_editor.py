"""Regression checks for drawing, history, file safety and unsaved work."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QImage, QImageWriter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox

from luma_paint.document import Document, blank_image, load_image, save_image, validate_size
from luma_paint.canvas import Canvas
from luma_paint.window import PaintWindow

app = QApplication.instance() or QApplication([])


def marked(width=64, height=48, color="red"):
    image = blank_image(width, height)
    image.setPixelColor(10, 10, QColor(color))
    return image


class DocumentTests(unittest.TestCase):
    def test_limits(self):
        for size in [(0, 1), (-1, 10), (9000, 1), (8192, 8192)]:
            with self.assertRaises(ValueError):
                validate_size(*size)

    def test_blank_noop_does_not_dirty_or_clear_redo(self):
        doc = Document(64, 48)
        self.assertFalse(doc.apply(blank_image(64, 48)))
        self.assertFalse(doc.dirty)
        doc.apply(marked())
        doc.undo()
        self.assertFalse(doc.apply(blank_image(64, 48)))
        self.assertEqual(len(doc.redo_stack), 1)

    def test_undo_redo_and_savepoint(self):
        doc = Document(64, 48)
        original = QImage(doc.image)
        doc.apply(marked())
        with tempfile.TemporaryDirectory() as folder:
            filename = str(Path(folder) / "кириллица.png")
            doc.save(filename)
            self.assertFalse(doc.dirty)
            doc.apply(marked(color="blue"))
            self.assertTrue(doc.dirty)
            doc.undo()
            self.assertFalse(doc.dirty)
            doc.undo()
            self.assertEqual(doc.image, original)
            self.assertTrue(doc.dirty)
            doc.redo()
            self.assertFalse(doc.dirty)
            doc.redo()
            self.assertEqual(doc.image.pixelColor(10, 10), QColor("blue"))

    def test_new_edit_drops_redo(self):
        doc = Document(64, 48)
        doc.apply(marked())
        doc.undo()
        doc.apply(marked(color="blue"))
        self.assertFalse(doc.redo_stack)

    def test_history_memory_and_step_bounds(self):
        doc = Document(64, 48, history_bytes=64*48*4*2)
        for index in range(50):
            image = QImage(doc.image)
            image.setPixelColor(index % 64, 2, QColor(index, 70, 80))
            doc.apply(image)
        self.assertLessEqual(len(doc.undo_stack), 2)
        self.assertLessEqual(sum(im.sizeInBytes() for im, _ in doc.undo_stack), doc.history_bytes)

    def test_failed_save_keeps_dirty_and_destination(self):
        doc = Document(64, 48)
        doc.apply(marked())
        with tempfile.TemporaryDirectory() as folder:
            filename = str(Path(folder) / "original.png")
            Path(filename).write_bytes(b"KEEP ORIGINAL")
            with patch.object(QImageWriter, "write", return_value=False):
                with self.assertRaises(OSError):
                    doc.save(filename)
            self.assertEqual(Path(filename).read_bytes(), b"KEEP ORIGINAL")
            self.assertTrue(doc.dirty)
            self.assertEqual(doc.filename, "")

    def test_file_formats_and_unicode_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            image = marked()
            for extension in ["png", "jpg", "bmp"]:
                filename = str(Path(folder) / f"рисунок.{extension}")
                save_image(image, filename)
                loaded = load_image(filename)
                self.assertEqual(loaded.size(), image.size())
                if extension != "jpg":
                    self.assertEqual(image, loaded)

    def test_bad_files_and_unsupported_save(self):
        with tempfile.TemporaryDirectory() as folder:
            filename = str(Path(folder) / "broken.png")
            Path(filename).write_text("not an image")
            with self.assertRaises(ValueError):
                load_image(filename)
            with self.assertRaises(ValueError):
                save_image(marked(), str(Path(folder) / "picture.xyz"))

    def test_transparent_import_flattens_to_white(self):
        with tempfile.TemporaryDirectory() as folder:
            image = QImage(10, 10, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            filename = str(Path(folder) / "transparent.png")
            self.assertTrue(image.save(filename))
            self.assertEqual(load_image(filename).pixelColor(0, 0), QColor("white"))

    def test_reset_drops_previous_document_history(self):
        doc = Document(64, 48)
        doc.apply(marked())
        doc.reset(blank_image(20, 30), "new.png")
        self.assertFalse(doc.undo_stack or doc.redo_stack or doc.dirty)
        self.assertEqual(doc.image.width(), 20)


class CanvasTests(unittest.TestCase):
    def setUp(self):
        self.doc = Document(64, 48)
        self.canvas = Canvas(self.doc)
        self.canvas.color = QColor("red")
        self.canvas.show()
        app.processEvents()

    def tearDown(self):
        self.canvas.cancel_gesture()
        self.canvas.close()

    def drag(self, start, end):
        QTest.mousePress(self.canvas, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(self.canvas, end)
        QTest.mouseRelease(self.canvas, Qt.MouseButton.LeftButton, pos=end)

    def test_single_click_draws_dot(self):
        QTest.mouseClick(self.canvas, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
        self.assertEqual(self.doc.image.pixelColor(10, 10), QColor("red"))
        self.assertEqual(len(self.doc.undo_stack), 1)

    def test_zoom_uses_image_coordinates(self):
        self.canvas.set_zoom(2)
        QTest.mouseClick(self.canvas, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
        self.assertEqual(self.doc.image.pixelColor(10, 10), QColor("red"))
        self.assertEqual(self.doc.image.pixelColor(20, 20), QColor("white"))

    def test_brush_one_gesture_one_step(self):
        self.drag(QPoint(5, 10), QPoint(40, 10))
        self.assertEqual(len(self.doc.undo_stack), 1)
        self.assertEqual(self.doc.image.pixelColor(20, 10), QColor("red"))
        self.doc.undo()
        self.assertEqual(self.doc.image, blank_image(64, 48))
        self.doc.redo()
        self.assertEqual(self.doc.image.pixelColor(20, 10), QColor("red"))

    def test_shape_preview_and_cancel(self):
        self.canvas.tool = "rectangle"
        QTest.mousePress(self.canvas, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
        QTest.mouseMove(self.canvas, QPoint(30, 30))
        self.assertEqual(self.doc.image, blank_image(64, 48))
        QTest.keyClick(self.canvas, Qt.Key.Key_Escape)
        QTest.mouseRelease(self.canvas, Qt.MouseButton.LeftButton, pos=QPoint(30, 30))
        self.assertFalse(self.doc.dirty)

    def test_line_rectangle_ellipse_and_fill(self):
        for tool in ["line", "rectangle", "ellipse"]:
            self.doc.reset(blank_image(64, 48))
            self.canvas.tool = tool
            self.canvas.fill_shapes = True
            self.drag(QPoint(10, 10), QPoint(40, 35))
            self.assertTrue(self.doc.dirty)
            self.assertEqual(len(self.doc.undo_stack), 1)
            if tool != "line":
                self.assertEqual(self.doc.image.pixelColor(25, 23), QColor("red"))

    def test_eraser_and_picker(self):
        self.doc.reset(marked())
        picked = []
        self.canvas.colorPicked.connect(picked.append)
        self.canvas.tool = "picker"
        QTest.mouseClick(self.canvas, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
        self.assertEqual(picked, [QColor("red")])
        self.assertFalse(self.doc.dirty)
        self.canvas.tool = "eraser"
        QTest.mouseClick(self.canvas, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
        self.assertEqual(self.doc.image.pixelColor(10, 10), QColor("white"))
        self.doc.undo()
        self.assertEqual(self.doc.image.pixelColor(10, 10), QColor("red"))


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.window = PaintWindow()
        self.window.document.reset(blank_image(64, 48))

    def tearDown(self):
        self.window.document.saved_revision = self.window.document.revision
        self.window.close()

    def test_cancel_close_preserves_document(self):
        self.window.document.apply(marked())
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.window.maybe_save())
            self.assertTrue(self.window.document.dirty)

    def test_cancel_save_prevents_discard(self):
        self.window.document.apply(marked())
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Save), patch.object(self.window, "save_document", return_value=False):
            self.assertFalse(self.window.maybe_save())
            self.assertTrue(self.window.document.dirty)

    def test_cancel_open_does_not_replace_image(self):
        self.window.document.apply(marked())
        with tempfile.TemporaryDirectory() as folder:
            filename = str(Path(folder) / "new.png")
            save_image(blank_image(20, 30), filename)
            with patch.object(self.window, "maybe_save", return_value=False):
                self.assertFalse(self.window.open_path(filename))
            self.assertEqual(self.window.document.image, marked())

    def test_rotate_mirror_undo(self):
        self.window.document.apply(marked())
        before = QImage(self.window.document.image)
        self.window.rotate(90)
        self.assertEqual(self.window.document.image.width(), 48)
        self.window.undo()
        self.assertEqual(self.window.document.image, before)
        self.window.mirror(True)
        self.assertEqual(self.window.document.image.pixelColor(53, 10), QColor("red"))
        self.window.undo()
        self.assertEqual(self.window.document.image, before)

    def test_palette_leaves_eraser_and_syncs_action(self):
        self.window.set_tool("eraser")
        self.window.set_color(QColor("blue"))
        self.assertEqual(self.window.canvas.tool, "brush")
        self.assertTrue(self.window.tool_actions["brush"].isChecked())


if __name__ == "__main__":
    unittest.main()
