"""Run from source with `python main.py`, or build using build_exe.py."""
import logging
from pathlib import Path
import sys

from PyQt6.QtCore import QStandardPaths, QLocale, QLibraryInfo, QTranslator
from PyQt6.QtGui import QImageReader, QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from luma_paint.window import PaintWindow, STYLE


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Luma Paint")
    app.setOrganizationName("LumaPaint")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "assets" / "icon.ico")))
    QImageReader.setAllocationLimit(128)
    translator = QTranslator(app)
    translator.load("qtbase_ru", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
    app.installTranslator(translator)
    log_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=log_dir / "errors.log", level=logging.ERROR, encoding="utf-8")
    except OSError:
        logging.basicConfig(level=logging.ERROR)

    def show_error(kind, value, traceback):
        logging.error("Unhandled application error", exc_info=(kind, value, traceback))
        QMessageBox.critical(None, "Ошибка Luma Paint", "Не удалось завершить действие.\n"
            "Попробуйте сохранить рисунок через «Сохранить как».\n"
            "Подробности записаны в журнал приложения, если доступна запись.")
    sys.excepthook = show_error
    window = PaintWindow()
    window.show()
    if len(sys.argv) > 1:
        window.open_path(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
