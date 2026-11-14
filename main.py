import multiprocessing
import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from hamstercam.ui_style import STYLESHEET
    from hamstercam.window import Window

    app = QApplication(sys.argv)
    app.setApplicationName("HamsterCam")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    window = Window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
