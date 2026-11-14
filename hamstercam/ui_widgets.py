from collections.abc import Mapping

from PIL import Image
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QComboBox, QFrame, QLabel, QSizePolicy, QWidget


def label(text: str, role: str = "") -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if role:
        widget.setProperty("role", role)
    return widget


def card() -> QFrame:
    widget = QFrame()
    widget.setProperty("card", True)
    return widget


def separator() -> QFrame:
    widget = QFrame()
    widget.setProperty("separator", True)
    return widget


def combo(options: Mapping, selected) -> QComboBox:
    widget = QComboBox()
    for value, text in options.items():
        widget.addItem(text, value)
    widget.setCurrentIndex(max(0, widget.findData(selected)))
    return widget


def qimage(image: Image.Image) -> QImage:
    rgba = image.convert("RGBA")
    return QImage(rgba.tobytes(), rgba.width, rgba.height,
                  rgba.width * 4, QImage.Format.Format_RGBA8888).copy()


def app_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#bda0ff"))
    painter.drawRoundedRect(1, 1, 62, 62, 17, 17)
    pen = QPen(QColor("#281a43"), 4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    for x, y, sx, sy in ((15, 15, 1, 1), (49, 15, -1, 1), (15, 49, 1, -1), (49, 49, -1, -1)):
        painter.drawLine(x, y, x + sx * 8, y)
        painter.drawLine(x, y, x, y + sy * 8)
    painter.drawEllipse(25, 25, 14, 14)
    painter.end()
    return QIcon(pixmap)


class Preview(QWidget):
    def __init__(self, empty: str) -> None:
        super().__init__()
        self.image = QImage()
        self.message = empty
        self.checkered = False
        self.setMinimumSize(300, 124)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_frame(self, image: QImage | None, message: str = "", checkered: bool = False) -> None:
        self.image = image if image is not None else QImage()
        self.message = message
        self.checkered = checkered
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#100e17"))
        if self.image.isNull():
            painter.setPen(QColor("#b8afcd"))
            painter.drawText(self.rect().adjusted(22, 15, -22, -15),
                             Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.message)
            return
        fit = self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QRect((self.width() - fit.width()) // 2, (self.height() - fit.height()) // 2,
                       fit.width(), fit.height())
        if self.checkered:
            painter.setClipRect(target)
            size = 16
            painter.fillRect(target, QColor("#342b43"))
            for row, top in enumerate(range(target.top(), target.bottom() + 1, size)):
                for left in range(target.left() + (row % 2) * size, target.right() + 1, size * 2):
                    painter.fillRect(QRect(left, top, size, size), QColor("#423750"))
        painter.drawImage(target, self.image)

    def sizeHint(self) -> QSize:
        return QSize(640, 360)
