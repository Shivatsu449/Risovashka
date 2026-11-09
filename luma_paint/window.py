"""Main editor window and explicit user decisions around file replacement."""
from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QSignalBlocker, QTimer
from PyQt6.QtGui import QAction, QActionGroup, QColor, QIcon, QKeySequence, QTransform
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QFileDialog, QColorDialog, QToolBar, QToolButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame, QSpinBox, QSlider,
    QCheckBox, QScrollArea, QComboBox, QMessageBox, QDialog, QDialogButtonBox,
    QFormLayout, QStyle, QSplitter,
)

from .canvas import Canvas
from .document import Document, blank_image, load_image, validate_size, MAX_SIDE

ZOOMS = [10, 25, 50, 75, 100, 125, 150, 200, 300, 400]
TOOLS = [
    ("brush", "Кисть", "B"), ("eraser", "Ластик", "E"),
    ("line", "Линия", "L"), ("rectangle", "Прямоугольник", "R"),
    ("ellipse", "Эллипс", "O"), ("picker", "Пипетка", "I"),
]
PALETTE = ["#202630", "#ffffff", "#8893a8", "#d6dbe5", "#ef4444", "#f97316",
           "#facc15", "#84cc16", "#22c55e", "#14b8a6", "#06b6d4", "#3b82f6",
           "#6366f1", "#a855f7", "#ec4899", "#a16207", "#fde1c5", "#fbcfe8"]


class SizeDialog(QDialog):
    def __init__(self, title, width, height, parent=None, resize_mode=False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(350)
        self.width_input = QSpinBox()
        self.height_input = QSpinBox()
        for control, value in [(self.width_input, width), (self.height_input, height)]:
            control.setRange(1, MAX_SIDE)
            control.setValue(value)
            control.setSuffix(" px")
        form = QFormLayout(self)
        form.addRow("Ширина", self.width_input)
        form.addRow("Высота", self.height_input)
        if resize_mode:
            form.addRow(QLabel("Изображение будет растянуто до указанных размеров.\nДействие можно отменить."))
        form.addRow(QLabel("Не более 16 миллионов пикселей."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Изменить" if resize_mode else "Создать")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def accept(self):
        try:
            validate_size(self.width_input.value(), self.height_input.value())
        except ValueError as error:
            QMessageBox.warning(self, "Размер холста", str(error))
            return
        super().accept()

    def dimensions(self):
        return self.width_input.value(), self.height_input.value()


class PaintWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.document = Document()
        self.canvas = Canvas(self.document)
        self.resize(1250, 860)
        self.setMinimumSize(780, 560)
        self.setWindowTitle("Luma Paint")
        self._build_actions()
        self._build_layout()
        self._build_menus()
        self._build_toolbar()
        self.document.changed.connect(self._update_state)
        self.canvas.colorPicked.connect(self.set_color)
        self.canvas.positionChanged.connect(self.position_label.setText)
        self.canvas.zoomRequested.connect(self.zoom_step)
        self._update_state()
        QTimer.singleShot(0, self.fit_canvas)

    def _action(self, text, callback, shortcut=None, icon=None):
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(shortcut)
        if icon:
            action.setIcon(self.style().standardIcon(icon))
        action.triggered.connect(callback)
        return action

    def _build_actions(self):
        self.new_action = self._action("Новый", self.new_document, QKeySequence.StandardKey.New, QStyle.StandardPixmap.SP_FileIcon)
        self.open_action = self._action("Открыть…", self.open_document, QKeySequence.StandardKey.Open, QStyle.StandardPixmap.SP_DirOpenIcon)
        self.save_action = self._action("Сохранить", self.save_document, QKeySequence.StandardKey.Save, QStyle.StandardPixmap.SP_DialogSaveButton)
        self.save_as_action = self._action("Сохранить как…", self.save_as, QKeySequence.StandardKey.SaveAs)
        self.undo_action = self._action("Отменить", self.undo, QKeySequence.StandardKey.Undo, QStyle.StandardPixmap.SP_ArrowBack)
        self.redo_action = self._action("Повторить", self.redo, QKeySequence.StandardKey.Redo, QStyle.StandardPixmap.SP_ArrowForward)
        self.redo_action.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
        self.clear_action = self._action("Очистить холст…", self.clear_canvas, "Ctrl+Delete")
        self.fit_action = self._action("Вписать холст", self.fit_canvas, "Ctrl+0")
        self.actual_action = self._action("Масштаб 100%", lambda: self.set_zoom(100), "Ctrl+1")
        self.zoom_in_action = self._action("Увеличить", lambda: self.zoom_step(1), "Ctrl++")
        self.zoom_out_action = self._action("Уменьшить", lambda: self.zoom_step(-1), "Ctrl+-")
        self.tool_group = QActionGroup(self)
        self.tool_actions = {}
        for key, name, shortcut in TOOLS:
            action = QAction(name, self)
            action.setCheckable(True)
            action.setShortcut(shortcut)
            action.setToolTip(f"{name} ({shortcut})")
            action.triggered.connect(lambda checked, value=key: self.set_tool(value))
            self.tool_group.addAction(action)
            self.addAction(action)
            self.tool_actions[key] = action
        self.tool_actions["brush"].setChecked(True)

    def _build_layout(self):
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(228)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 23, 18, 18)
        side.setSpacing(16)
        title = QLabel("LUMA  <span style='color:#9198b2'>PAINT</span>")
        title.setObjectName("brand")
        side.addWidget(title)
        side.addWidget(self._caption("ИНСТРУМЕНТЫ"))
        tool_grid = QGridLayout()
        tool_grid.setSpacing(8)
        for index, (key, _, _) in enumerate(TOOLS):
            button = QToolButton()
            button.setDefaultAction(self.tool_actions[key])
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setMinimumHeight(42)
            button.setMinimumWidth(0)
            button.setSizePolicy(button.sizePolicy().Policy.Expanding, button.sizePolicy().Policy.Fixed)
            tool_grid.addWidget(button, index // 2, index % 2)
        side.addLayout(tool_grid)
        side.addWidget(self._caption("ТОЛЩИНА"))
        width_row = QHBoxLayout()
        self.width_slider = QSlider(Qt.Orientation.Horizontal)
        self.width_slider.setRange(1, 80)
        self.width_slider.setValue(6)
        self.width_slider.setAccessibleName("Толщина инструмента")
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 80)
        self.width_spin.setValue(6)
        self.width_spin.setSuffix(" px")
        self.width_spin.setAccessibleName("Толщина в пикселях")
        self.width_spin.setFixedWidth(77)
        self.width_slider.valueChanged.connect(self.width_spin.setValue)
        self.width_spin.valueChanged.connect(self.width_slider.setValue)
        self.width_spin.valueChanged.connect(self.set_width)
        width_row.addWidget(self.width_slider)
        width_row.addWidget(self.width_spin)
        side.addLayout(width_row)
        self.fill_check = QCheckBox("Заливка фигур")
        self.fill_check.setToolTip("Закрашивает прямоугольник или эллипс выбранным цветом")
        self.fill_check.setEnabled(False)
        self.fill_check.toggled.connect(lambda state: setattr(self.canvas, "fill_shapes", state))
        side.addWidget(self.fill_check)
        side.addWidget(self._caption("ЦВЕТ"))
        self.color_button = QToolButton()
        self.color_button.setMinimumHeight(42)
        self.color_button.clicked.connect(self.pick_color)
        side.addWidget(self.color_button)
        self._update_color_button()
        palette = QGridLayout()
        palette.setSpacing(6)
        for index, value in enumerate(PALETTE):
            button = QToolButton()
            button.setFixedSize(26, 26)
            button.setStyleSheet(f"QToolButton {{background:{value}; border:1px solid #6a7086; border-radius:6px;}} QToolButton:hover {{border:2px solid #c1b6ff;}}")
            button.setToolTip(value)
            button.setAccessibleName("Цвет " + value)
            button.clicked.connect(lambda checked=False, color=value: self.set_color(QColor(color)))
            palette.addWidget(button, index // 6, index % 6)
        side.addLayout(palette)
        side.addStretch()
        hint = QLabel("B — кисть  ·  E — ластик\nCtrl+Z — отменить\nCtrl+колесо — масштаб\nEsc — отменить фигуру")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        side.addWidget(hint)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("canvasArea")
        self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setWidget(self.canvas)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(sidebar)
        layout.addWidget(self.scroll, 1)
        self.setCentralWidget(central)
        self.tool_label = QLabel("Кисть")
        self.size_label = QLabel()
        self.position_label = QLabel()
        self.statusBar().addWidget(self.tool_label)
        self.statusBar().addPermanentWidget(self.position_label)
        self.statusBar().addPermanentWidget(self.size_label)

    @staticmethod
    def _caption(text):
        label = QLabel(text)
        label.setObjectName("caption")
        return label

    def _build_toolbar(self):
        toolbar = QToolBar("Основные действия")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(toolbar)
        for action in (self.new_action, self.open_action, self.save_action):
            toolbar.addAction(action)
        toolbar.addSeparator()
        toolbar.addAction(self.undo_action)
        toolbar.addAction(self.redo_action)
        toolbar.addSeparator()
        toolbar.addAction(self.fit_action)
        self.zoom_combo = QComboBox()
        self.zoom_combo.setAccessibleName("Масштаб холста")
        self.zoom_combo.setMinimumWidth(90)
        for zoom in ZOOMS:
            self.zoom_combo.addItem(f"{zoom}%", zoom)
        self.zoom_combo.setCurrentIndex(ZOOMS.index(100))
        self.zoom_combo.activated.connect(lambda index: self.set_zoom(self.zoom_combo.itemData(index)))
        toolbar.addWidget(self.zoom_combo)

    def _build_menus(self):
        file_menu = self.menuBar().addMenu("Файл")
        for action in (self.new_action, self.open_action, self.save_action, self.save_as_action):
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction(self._action("Выход", self.close, "Ctrl+Q"))
        edit = self.menuBar().addMenu("Правка")
        edit.addAction(self.undo_action)
        edit.addAction(self.redo_action)
        edit.addSeparator()
        edit.addAction(self.clear_action)
        image_menu = self.menuBar().addMenu("Изображение")
        image_menu.addAction(self._action("Изменить размер…", self.resize_image))
        image_menu.addAction(self._action("Повернуть вправо", lambda: self.rotate(90)))
        image_menu.addAction(self._action("Повернуть влево", lambda: self.rotate(-90)))
        image_menu.addAction(self._action("Отразить по горизонтали", lambda: self.mirror(True)))
        image_menu.addAction(self._action("Отразить по вертикали", lambda: self.mirror(False)))
        view = self.menuBar().addMenu("Вид")
        for action in (self.fit_action, self.actual_action, self.zoom_in_action, self.zoom_out_action):
            view.addAction(action)
        help_menu = self.menuBar().addMenu("Справка")
        help_menu.addAction(self._action("О программе и управлении", self.about))

    def _update_state(self):
        name = Path(self.document.filename).name if self.document.filename else "Без названия"
        self.setWindowTitle(f"{'● ' if self.document.dirty else ''}{name} — Luma Paint")
        self.undo_action.setEnabled(bool(self.document.undo_stack))
        self.redo_action.setEnabled(bool(self.document.redo_stack))
        self.size_label.setText(f"  {self.document.image.width()} × {self.document.image.height()} px  ")

    def set_tool(self, tool):
        self.canvas.finish_gesture()
        self.canvas.tool = tool
        self.tool_actions[tool].setChecked(True)
        self.tool_label.setText(dict((key, name) for key, name, _ in TOOLS)[tool])
        self.fill_check.setEnabled(tool in {"rectangle", "ellipse"})
        self.width_spin.setEnabled(tool != "picker")
        self.width_slider.setEnabled(tool != "picker")

    def set_width(self, width):
        self.canvas.pen_width = width

    def _update_color_button(self):
        color = self.canvas.color
        foreground = "#111827" if color.lightness() > 145 else "white"
        self.color_button.setText("Выбрать цвет  " + color.name().upper())
        self.color_button.setStyleSheet(f"QToolButton{{background:{color.name()};color:{foreground};border:1px solid #727991;border-radius:7px;padding:7px;font-size:11px;}}")

    def set_color(self, color):
        if color.isValid():
            self.canvas.finish_gesture()
            self.canvas.color = QColor(color)
            self._update_color_button()
            if self.canvas.tool in {"eraser", "picker"}:
                self.set_tool("brush")

    def pick_color(self):
        self.canvas.finish_gesture()
        color = QColorDialog.getColor(self.canvas.color, self, "Цвет инструмента")
        self.set_color(color)

    def set_zoom(self, percent):
        percent = max(10, min(400, round(percent)))
        self.canvas.set_zoom(percent / 100)
        blocker = QSignalBlocker(self.zoom_combo)
        for index in range(self.zoom_combo.count() - 1, -1, -1):
            if self.zoom_combo.itemData(index) not in ZOOMS:
                self.zoom_combo.removeItem(index)
        index = self.zoom_combo.findData(percent)
        if index < 0:
            self.zoom_combo.addItem(f"{percent}%", percent)
            index = self.zoom_combo.count() - 1
        self.zoom_combo.setCurrentIndex(index)
        del blocker

    def fit_canvas(self):
        viewport = self.scroll.viewport().size()
        image = self.document.image
        percent = min((viewport.width()-36)/image.width(), (viewport.height()-36)/image.height(), 1.0) * 100
        self.set_zoom(max(10, int(percent)))

    def zoom_step(self, direction):
        current = round(self.canvas.zoom * 100)
        options = [value for value in ZOOMS if value > current] if direction > 0 else [value for value in ZOOMS if value < current]
        if options:
            self.set_zoom(min(options) if direction > 0 else max(options))

    def undo(self):
        self.canvas.finish_gesture()
        self.document.undo()

    def redo(self):
        self.canvas.finish_gesture()
        self.document.redo()

    def maybe_save(self):
        self.canvas.finish_gesture()
        if not self.document.dirty:
            return True
        choice = QMessageBox.question(self, "Несохранённый рисунок", "Сохранить изменения перед продолжением?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if choice == QMessageBox.StandardButton.Save:
            return self.save_document()
        return choice == QMessageBox.StandardButton.Discard

    def new_document(self):
        dialog = SizeDialog("Новый рисунок", 1200, 800, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if self.maybe_save():
            self.document.reset(blank_image(*dialog.dimensions()))
            self.fit_canvas()

    def open_document(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Открыть изображение", "", "Изображения (*.png *.jpg *.jpeg *.bmp *.webp)")
        if filename:
            self.open_path(filename)

    def open_path(self, filename):
        try:
            image = load_image(filename)
        except (ValueError, OSError, MemoryError) as error:
            QMessageBox.warning(self, "Не удалось открыть", str(error))
            return False
        if not self.maybe_save():
            return False
        self.document.reset(image, filename)
        self.fit_canvas()
        return True

    def save_document(self):
        self.canvas.finish_gesture()
        if not self.document.filename or Path(self.document.filename).suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp"}:
            return self.save_as()
        return self._save_to(self.document.filename)

    def save_as(self):
        self.canvas.finish_gesture()
        start = self.document.filename or "Рисунок.png"
        if Path(start).suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp"}:
            start = str(Path(start).with_suffix(".png"))
        filename, selected = QFileDialog.getSaveFileName(self, "Сохранить рисунок", start,
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;BMP (*.bmp)")
        if not filename:
            return False
        extension = {"PNG (*.png)": ".png", "JPEG (*.jpg *.jpeg)": ".jpg", "BMP (*.bmp)": ".bmp"}.get(selected, ".png")
        if not Path(filename).suffix:
            filename += extension
            if Path(filename).exists():
                answer = QMessageBox.question(self, "Заменить файл?", f"Файл {Path(filename).name} уже существует. Заменить?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    return False
        return self._save_to(filename)

    def _save_to(self, filename):
        try:
            self.document.save(filename)
        except (ValueError, OSError, MemoryError) as error:
            QMessageBox.warning(self, "Ошибка сохранения", str(error))
            return False
        self.statusBar().showMessage("Сохранено: " + filename, 6000)
        return True

    def clear_canvas(self):
        self.canvas.finish_gesture()
        answer = QMessageBox.question(self, "Очистить холст", "Залить весь холст белым цветом? Действие можно отменить.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.document.apply(blank_image(self.document.image.width(), self.document.image.height()))

    def rotate(self, angle):
        self.canvas.finish_gesture()
        self.document.apply(self.document.image.transformed(QTransform().rotate(angle)))
        self.fit_canvas()

    def mirror(self, horizontal):
        self.canvas.finish_gesture()
        self.document.apply(self.document.image.mirrored(horizontal, not horizontal))

    def resize_image(self):
        self.canvas.finish_gesture()
        dialog = SizeDialog("Размер изображения", self.document.image.width(), self.document.image.height(), self, True)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            width, height = dialog.dimensions()
            self.document.apply(self.document.image.scaled(width, height, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.fit_canvas()

    def about(self):
        QMessageBox.information(self, "Luma Paint 1.0", "Luma Paint — простой растровый редактор.\n\n"
            "B — кисть; E — ластик; L — линия; R — прямоугольник; O — эллипс; I — пипетка.\n"
            "Ctrl+Z — отмена, Ctrl+Y / Ctrl+Shift+Z — повтор.\nCtrl+S — сохранить. Ctrl+0 — вписать холст.\n"
            "Ctrl+колесо — масштаб. Esc — отменить незавершённый штрих или фигуру.\n\n"
            "Белый непрозрачный холст. При открытии прозрачность заменяется белым.\n"
            "История ограничена 30 шагами и 128 МиБ; большие рисунки хранят меньше шагов.\n"
            "Программа работает локально и не отправляет изображения в интернет.")

    def closeEvent(self, event):
        if self.maybe_save():
            event.accept()
        else:
            event.ignore()


STYLE = """
QMainWindow,QDialog {background:#1c1f2b;color:#e8eaf3;}
QWidget {font-family:'Segoe UI';font-size:12px;color:#e8eaf3;}
QMenuBar,QToolBar {background:#252936;border:0;spacing:7px;padding:7px;}
QMenuBar::item {padding:5px 12px;}
QMenuBar::item:selected,QMenu::item:selected {background:#514574;}
QMenu {background:#292d3e;border:1px solid #4b5169;padding:5px;}
QMenu::item {padding:7px 32px 7px 15px;}
QMenu::item:disabled {color:#7f869c;}
QToolBar {border-top:1px solid #353a4d;border-bottom:1px solid #353a4d;}
QToolBar QToolButton {padding:8px 10px;}
QToolButton,QPushButton {background:#2e3345;border:1px solid #41485e;border-radius:7px;padding:7px;}
QToolButton:hover,QPushButton:hover {background:#3c4156;border-color:#9280d0;}
QToolButton:checked {background:#6950a1;border-color:#bca6f2;color:white;}
QToolButton:disabled,QPushButton:disabled {color:#737c92;background:#262a38;}
QToolButton:focus,QPushButton:focus,QSpinBox:focus,QComboBox:focus {border:2px solid #c4afff;}
QFrame#sidebar {background:#222634;border-right:1px solid #373d50;}
QLabel#brand {font-size:19px;font-weight:700;letter-spacing:2px;margin-bottom:12px;}
QLabel#caption {font-size:10px;font-weight:600;color:#a0abc5;letter-spacing:1.5px;}
QLabel#hint {color:#9ca7bf;font-size:11px;line-height:1.6;}
QScrollArea#canvasArea {background:#151822;}
QStatusBar {background:#252936;border-top:1px solid #363b4f;}
QStatusBar QLabel {color:#bcc5da;padding:4px 9px;}
QSpinBox,QComboBox {background:#181d2b;border:1px solid #4d556f;padding:6px;border-radius:5px;}
QComboBox QAbstractItemView {background:#252936;color:white;selection-background-color:#6950a1;}
QCheckBox {spacing:9px;}
QSlider::groove:horizontal {height:4px;background:#454e69;border-radius:2px;}
QSlider::handle:horizontal {background:#c6b0fa;width:14px;margin:-5px 0;border-radius:7px;}
QMessageBox {background:#252936;}
"""
