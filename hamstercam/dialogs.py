from pathlib import Path

from PIL import Image
from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QGridLayout,
    QHBoxLayout, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from .assets import Collection
from .settings import EXPRESSIONS
from .ui_widgets import card, label, qimage


class CollectionDialog(QDialog):
    def __init__(self, collection: Collection, on_change, parent=None) -> None:
        super().__init__(parent)
        self.collection = collection
        self.on_change = on_change
        self.setWindowTitle("Коллекция · HamsterCam")
        self.resize(690, 630)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.addWidget(label("Коллекция хомяков", "heading"))
        introduction = label("Загрузите оригинальные PNG Almarts27. Для пустых ячеек используется neutral.png.", "muted")
        introduction.setWordWrap(True)
        layout.addWidget(introduction)
        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("scrollBody")
        grid = QGridLayout(body)
        grid.setContentsMargins(0, 0, 8, 0)
        grid.setSpacing(10)
        self.thumbnails = {}
        for index, (name, text) in enumerate(EXPRESSIONS.items()):
            tile = card()
            tile_layout = QVBoxLayout(tile)
            thumbnail = label("Пусто", "muted")
            thumbnail.setFixedHeight(66)
            thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.thumbnails[name] = thumbnail
            tile_layout.addWidget(thumbnail)
            tile_layout.addWidget(label(text, "accent"))
            tile_layout.addWidget(label(f"{name}.png", "muted"))
            assign = QPushButton("Выбрать PNG…")
            assign.clicked.connect(lambda checked=False, key=name: self.assign(key))
            tile_layout.addWidget(assign)
            grid.addWidget(tile, index // 3, index % 3)
        scroller.setWidget(body)
        layout.addWidget(scroller, 1)
        self.summary = label("", "muted")
        layout.addWidget(self.summary)
        actions = QHBoxLayout()
        bulk = QPushButton("Загрузить набор по именам…")
        bulk.clicked.connect(self.import_set)
        folder = QPushButton("Открыть папку")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(collection.directory))))
        close = QPushButton("Готово")
        close.setProperty("primary", True)
        close.clicked.connect(self.accept)
        actions.addWidget(bulk)
        actions.addWidget(folder)
        actions.addStretch()
        actions.addWidget(close)
        layout.addLayout(actions)
        self.refresh()

    def refresh(self) -> None:
        images, invalid = self.collection.load()
        for name, thumbnail in self.thumbnails.items():
            if name in images:
                image = images[name].copy()
                image.thumbnail((175, 62), Image.Resampling.LANCZOS)
                thumbnail.setPixmap(QPixmap.fromImage(qimage(image)))
            else:
                thumbnail.clear()
                thumbnail.setText("Ошибка PNG" if f"{name}.png" in invalid else "Пусто")
        self.summary.setText(f"Загружено {len(images)} из {len(EXPRESSIONS)}")
        self.on_change(images, invalid)

    def assign(self, name: str) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Выберите PNG", "", "Изображения PNG (*.png)")
        if filename:
            try:
                self.collection.assign(name, Path(filename))
            except (OSError, ValueError, Image.DecompressionBombError) as error:
                QMessageBox.warning(self, "Не удалось загрузить PNG", str(error))
            self.refresh()

    def import_set(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Папка с PNG")
        if not directory:
            return
        try:
            files = {path.stem.lower(): path for path in Path(directory).iterdir()
                     if path.is_file() and path.suffix.lower() == ".png" and path.stem.lower() in EXPRESSIONS}
        except OSError as error:
            QMessageBox.warning(self, "Не удалось открыть папку", str(error))
            return
        if not files:
            QMessageBox.information(self, "PNG не найдены", "Используйте имена из коллекции, например neutral.png.")
            return
        reply = QMessageBox.question(
            self, "Импорт коллекции",
            f"Импортировать {len(files)} PNG и заменить совпадающие ячейки?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        errors = []
        for name, path in files.items():
            try:
                self.collection.assign(name, path)
            except (OSError, ValueError, Image.DecompressionBombError) as error:
                errors.append(f"{path.name} — {error}")
        self.refresh()
        if errors:
            QMessageBox.warning(self, "Часть PNG не загрузилась", "\n".join(errors))


class PriorityDialog(QDialog):
    def __init__(self, priority: tuple[str, ...], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Приоритет выражений")
        self.resize(390, 445)
        layout = QVBoxLayout(self)
        note = label("Перетащите выражения. При совпадении выбирается верхнее из списка.", "muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        for name in priority:
            item = QListWidgetItem(EXPRESSIONS[name])
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.list.addItem(item)
        layout.addWidget(self.list)
        buttons = QDialogButtonBox()
        buttons.addButton("Сохранить", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("Отмена", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def priority(self) -> tuple[str, ...]:
        return tuple(self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count()))
