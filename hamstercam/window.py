from dataclasses import replace
import os
from pathlib import Path
import time

import cv2
from PIL import Image
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QMainWindow,
    QMenu, QPushButton, QScrollArea, QSlider, QSpinBox, QSystemTrayIcon,
    QVBoxLayout, QWidget,
)

from .assets import AssetPack, Collection, prepare_image
from .camera import Device, list_devices
from .dialogs import CollectionDialog, PriorityDialog
from .pipeline import MAX_FRAME_AGE, Pipeline
from .settings import BACKGROUNDS, COLLECTION_DIR, DATA_DIR, EXPRESSIONS, load_settings, save_settings
from .ui_widgets import Preview, app_icon, card, combo, label, qimage, separator


class Window(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("HamsterCam")
        self.resize(1110, 770)
        self.setMinimumSize(820, 600)
        self.setWindowIcon(app_icon())
        self.settings = load_settings()
        self.collection = Collection(COLLECTION_DIR)
        self.images, self.invalid_images = self.collection.load()
        self.background_image = None
        self.background_error = ""
        self.load_background()
        self.pipeline = Pipeline(self.settings, self.assets())
        self.last_local = None
        self.last_render = None
        self.last_calibration = None
        self.closing_at = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(22, 16, 22, 15)
        layout.setSpacing(12)
        header = QHBoxLayout()
        brand = label("", "title")
        brand.setPixmap(self.windowIcon().pixmap(38, 38))
        header.addWidget(brand)
        header.addWidget(label("HamsterCam", "title"))
        header.addStretch()
        self.live = label("Виртуальная камера выключена", "status")
        header.addWidget(self.live)
        self.tray_button = QPushButton("В трей")
        self.tray_button.clicked.connect(self.hide)
        self.tray_button.setToolTip("Свернуть окно, оставив камеры в текущем состоянии")
        header.addWidget(self.tray_button)
        layout.addLayout(header)

        content = QHBoxLayout()
        content.setSpacing(12)
        previews = QVBoxLayout()
        previews.setSpacing(10)
        self.avatar = Preview("Добавьте neutral.png в коллекцию")
        virtual, avatar_status = self.preview_card(
            "Виртуальная камера", "1280 × 720  ·  30 FPS", self.avatar,
        )
        self.format_label = avatar_status
        self.expression = label("", "accent")
        self.expression.setWordWrap(True)
        virtual.layout().addWidget(self.expression)
        self.pose = label("", "muted")
        virtual.layout().addWidget(self.pose)
        self.local = Preview("Камера не подключена")
        physical, _ = self.preview_card("Физическая камера", "Только в этом окне", self.local)
        previews.addWidget(virtual, 3)
        previews.addWidget(physical, 2)
        content.addLayout(previews, 1)
        content.addWidget(self.build_controls())
        layout.addLayout(content, 1)
        self.message = label("", "error")
        self.message.setWordWrap(True)
        self.message.hide()
        layout.addWidget(self.message)
        self.notice = label("", "muted")
        self.notice.setWordWrap(True)
        self.notice.hide()
        layout.addWidget(self.notice)

        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            self.tray.setToolTip("HamsterCam")
            menu = QMenu(self)
            menu.addAction("Открыть HamsterCam", self.restore)
            menu.addAction("Запустить / остановить виртуальную камеру", self.toggle_output)
            menu.addSeparator()
            menu.addAction("Выход", self.close)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(self.tray_activated)
            self.tray.show()
        self.tray_button.setVisible(self.tray is not None)
        self.shortcuts = []
        for number, name in enumerate(EXPRESSIONS, 1):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{number % 10}"), self)
            shortcut.activated.connect(lambda key=name: self.pick_manual(key))
            self.shortcuts.append(shortcut)
        self.save_timer = QTimer(self, interval=300, singleShot=True)
        self.save_timer.timeout.connect(self.persist)
        self.refresh_devices()
        self.refresh_collection_label()
        self.timer = QTimer(self, interval=40)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    @staticmethod
    def preview_card(title: str, subtitle: str, preview: Preview) -> tuple[QWidget, QWidget]:
        panel = card()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(13, 11, 13, 10)
        heading = QHBoxLayout()
        heading.addWidget(label(title, "heading"))
        heading.addStretch()
        description = label(subtitle, "muted")
        heading.addWidget(description)
        layout.addLayout(heading)
        layout.addWidget(preview, 1)
        return panel, description

    def build_controls(self) -> QWidget:
        panel = card()
        panel.setFixedWidth(344)
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(14, 13, 10, 11)
        outer.addWidget(label("Управление", "heading"))
        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("scrollBody")
        controls = QVBoxLayout(body)
        controls.setContentsMargins(0, 2, 6, 2)
        controls.setSpacing(8)

        controls.addWidget(label("Физическая камера", "muted"))
        chooser = QHBoxLayout()
        self.device = QComboBox()
        self.device.setMinimumWidth(150)
        self.device.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.device.currentIndexChanged.connect(self.select_device)
        refresh = QPushButton("↻")
        refresh.setAccessibleName("Обновить список камер")
        refresh.setToolTip("Обновить список камер")
        refresh.setFixedWidth(39)
        refresh.clicked.connect(self.refresh_devices)
        chooser.addWidget(self.device, 1)
        chooser.addWidget(refresh)
        controls.addLayout(chooser)
        self.camera_note = label("", "muted")
        self.camera_note.setWordWrap(True)
        controls.addWidget(self.camera_note)

        options = QFormLayout()
        options.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        resolution = combo({720: "1280 × 720", 1080: "1920 × 1080"}, self.settings.height)
        resolution.currentIndexChanged.connect(lambda: self.change(height=resolution.currentData()))
        options.addRow(label("Разрешение", "muted"), resolution)
        self.background = combo(BACKGROUNDS, self.settings.background)
        self.background.setToolTip("Для прозрачного предпросмотра OBS получает белый фон")
        self.background.currentIndexChanged.connect(self.background_changed)
        options.addRow(label("Фон", "muted"), self.background)
        controls.addLayout(options)
        self.background_button = QPushButton("Выбрать изображение фона…")
        self.background_button.clicked.connect(self.pick_background)
        self.background_button.setVisible(self.settings.background == "custom")
        controls.addWidget(self.background_button)
        controls.addWidget(self.checkbox("Зеркальное отображение", "mirror"))

        self.collection_button = QPushButton()
        self.collection_button.clicked.connect(self.open_collection)
        controls.addWidget(self.collection_button)
        controls.addWidget(separator())
        self.auto = self.checkbox("Автоматическое переключение", "auto")
        self.auto.toggled.connect(self.mode_changed)
        controls.addWidget(self.auto)
        self.manual = combo(EXPRESSIONS, self.settings.manual_expression)
        self.manual.setEnabled(not self.settings.auto)
        self.manual.currentIndexChanged.connect(lambda: self.change(manual_expression=self.manual.currentData()))
        self.manual.setToolTip("Ручной выбор · Ctrl+1–9, Ctrl+0")
        controls.addWidget(self.manual)
        self.slider(controls, "Чувствительность", "sensitivity")
        self.slider(controls, "Сглаживание", "smoothing")
        hold = QSpinBox()
        hold.setRange(0, 1500)
        hold.setSingleStep(20)
        hold.setSuffix(" мс")
        hold.setValue(self.settings.hold_ms)
        hold.valueChanged.connect(lambda value: self.change(hold_ms=value))
        hold_layout = QFormLayout()
        hold_layout.addRow(label("Удержание мимики", "muted"), hold)
        controls.addLayout(hold_layout)
        priorities = QPushButton("Приоритет выражений…")
        priorities.clicked.connect(self.open_priority)
        controls.addWidget(priorities)
        calibration_row = QHBoxLayout()
        self.calibrate_button = QPushButton("Калибровать лицо")
        self.calibrate_button.clicked.connect(self.pipeline.calibrate)
        reset = QPushButton("Сбросить")
        reset.clicked.connect(self.reset_calibration)
        calibration_row.addWidget(self.calibrate_button, 1)
        calibration_row.addWidget(reset)
        controls.addLayout(calibration_row)
        self.calibration_note = label("", "muted")
        self.calibration_note.setWordWrap(True)
        self.calibration_note.hide()
        controls.addWidget(self.calibration_note)
        controls.addWidget(separator())
        controls.addWidget(label("Анимация", "heading"))
        for name, text in (
            ("sway", "Покачивание"), ("tilt", "Поворот при наклоне головы"),
            ("zoom", "Масштаб при приближении"), ("fade", "Плавные переходы PNG"),
            ("bounce", "Подпрыгивание при смехе"),
        ):
            controls.addWidget(self.checkbox(text, name))
        controls.addStretch()
        scroller.setWidget(body)
        outer.addWidget(scroller, 1)
        self.output_button = QPushButton("Запустить виртуальную камеру")
        self.output_button.setProperty("primary", True)
        self.output_button.clicked.connect(self.toggle_output)
        outer.addWidget(self.output_button)
        return panel

    def checkbox(self, text: str, field: str) -> QCheckBox:
        widget = QCheckBox(text)
        widget.setChecked(getattr(self.settings, field))
        widget.toggled.connect(lambda checked: self.change(**{field: checked}))
        return widget

    def slider(self, layout: QVBoxLayout, text: str, field: str) -> None:
        row = QHBoxLayout()
        title = label(text, "muted")
        value = label(str(getattr(self.settings, field)), "accent")
        row.addWidget(title)
        row.addStretch()
        row.addWidget(value)
        layout.addLayout(row)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setAccessibleName(text)
        slider.setRange(0, 100)
        slider.setValue(getattr(self.settings, field))
        slider.valueChanged.connect(lambda number: value.setText(str(number)))
        slider.valueChanged.connect(lambda number: self.change(**{field: number}))
        layout.addWidget(slider)

    def change(self, **values) -> None:
        self.settings = replace(self.settings, **values)
        self.pipeline.settings.write(self.settings)
        self.save_timer.start()

    def persist(self) -> None:
        try:
            save_settings(self.settings)
        except OSError as error:
            self.set_notice(f"Не удалось сохранить настройки: {error}")

    def set_notice(self, text: str) -> None:
        self.notice.setText(text)
        self.notice.setVisible(bool(text))

    def refresh_devices(self) -> None:
        try:
            devices = list_devices()
        except Exception as error:
            self.set_notice(f"Не удалось получить список камер: {error}")
            return
        selected = self.settings.camera_id
        self.device.blockSignals(True)
        self.device.clear()
        if not devices:
            self.device.addItem("Камеры не найдены", None)
        for device in devices:
            self.device.addItem(device.name, device)
        index = next((i for i, device in enumerate(devices) if device.identifier == selected), 0)
        self.device.setCurrentIndex(index)
        self.device.blockSignals(False)
        self.select_device()

    def select_device(self) -> None:
        device: Device | None = self.device.currentData()
        if device and device.identifier != self.settings.camera_id:
            self.change(camera_id=device.identifier)
        self.pipeline.select_device(device)

    def mode_changed(self, auto: bool) -> None:
        self.manual.setEnabled(not auto)

    def pick_manual(self, key: str) -> None:
        self.auto.setChecked(False)
        self.manual.setCurrentIndex(self.manual.findData(key))

    def assets(self) -> AssetPack:
        return AssetPack(self.images, self.background_image)

    def load_background(self) -> None:
        self.background_error = ""
        self.background_image = None
        if self.settings.custom_background:
            try:
                self.background_image = prepare_image(Path(self.settings.custom_background))
            except (OSError, ValueError, Image.DecompressionBombError):
                self.background_error = "Файл фона недоступен. Используется белый фон."

    def background_changed(self) -> None:
        value = self.background.currentData()
        self.change(background=value)
        self.background_button.setVisible(value == "custom")
        if value == "custom" and self.background_image is None:
            self.pick_background()

    def pick_background(self) -> None:
        file, _ = QFileDialog.getOpenFileName(
            self, "Изображение фона", "", "Изображения (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if file:
            try:
                self.background_image = prepare_image(Path(file))
            except (OSError, ValueError, Image.DecompressionBombError) as error:
                self.set_notice(f"Не удалось загрузить фон: {error}")
                return
            self.background_error = ""
            self.set_notice("")
            self.pipeline.assets.write(self.assets())
            self.change(custom_background=file)

    def open_collection(self) -> None:
        CollectionDialog(self.collection, self.collection_changed, self).exec()

    def collection_changed(self, images: dict, invalid: list[str]) -> None:
        self.images, self.invalid_images = images, invalid
        self.pipeline.assets.write(self.assets())
        self.refresh_collection_label()

    def refresh_collection_label(self) -> None:
        self.collection_button.setText(f"Коллекция PNG · {len(self.images)}/{len(EXPRESSIONS)}")

    def open_priority(self) -> None:
        dialog = PriorityDialog(self.settings.priority, self)
        if dialog.exec():
            self.change(priority=dialog.priority())

    def reset_calibration(self) -> None:
        self.change(baseline={})
        self.calibration_note.setText("Калибровка сброшена.")
        self.calibration_note.show()

    def toggle_output(self) -> None:
        if self.closing_at is not None:
            return
        if self.pipeline.output_requested:
            self.pipeline.stop_output()
        elif "neutral" not in self.images:
            self.restore()
            self.open_collection()
        else:
            self.pipeline.start_output()

    def refresh(self) -> None:
        if self.closing_at is not None:
            if not self.pipeline.is_alive():
                self.close()
            elif time.monotonic() - self.closing_at > 8:
                # A broken native webcam driver can block VideoCapture.read indefinitely.
                # Windows releases the camera handle when the process exits.
                os._exit(0)
            return
        now = time.monotonic()
        output = self.pipeline.output.read()
        calibration = self.pipeline.calibration.read()
        if calibration is not self.last_calibration:
            self.last_calibration = calibration
            self.calibration_note.setText(calibration.message)
            self.calibration_note.setVisible(bool(calibration.message))
            if calibration.baseline:
                self.change(baseline=calibration.baseline)

        pending = self.pipeline.output_requested
        if output.device:
            state = output.device if pending else "Камера останавливается…"
            if output.fps and pending:
                state += f"  ·  {output.fps:.1f} FPS"
        else:
            state = "Камера запускается…" if pending else "Виртуальная камера выключена"
        self.live.setText(state)
        self.output_button.setText(
            "Остановить виртуальную камеру" if pending else "Запустить виртуальную камеру",
        )
        self.output_button.setEnabled(pending or not output.device)

        camera = self.pipeline.camera_frame.read()
        generation, _ = self.pipeline.device.read()
        if camera is not None and (camera.generation != generation or now - camera.captured_at > MAX_FRAME_AGE):
            camera = None
        camera_note = self.pipeline.camera_status.read()
        self.camera_note.setText(camera_note)
        self.camera_note.setVisible(bool(camera_note))
        self.calibrate_button.setEnabled(camera is not None)
        issues = [
            output.error, self.pipeline.tracking_status.read(),
            self.background_error if self.settings.background == "custom" else "",
            f"Повреждённые PNG · {', '.join(self.invalid_images)}" if self.invalid_images else "",
        ]
        message = "\n".join(issue for issue in issues if issue)
        self.message.setText(message)
        self.message.setVisible(bool(message))
        if not self.isVisible() or self.isMinimized():
            return

        local_key = (camera.captured_at if camera else None, self.settings.mirror, camera_note)
        if local_key != self.last_local:
            self.last_local = local_key
            if camera is None:
                self.local.set_frame(None, camera_note or "Ожидание кадров")
            else:
                rgb = cv2.cvtColor(camera.bgr, cv2.COLOR_BGR2RGB)
                if self.settings.mirror:
                    rgb = cv2.flip(rgb, 1)
                height, width = rgb.shape[:2]
                image = QImage(rgb.data, width, height, rgb.strides[0], QImage.Format.Format_RGB888)
                self.local.set_frame(image.copy())

        rendered = output.rendered
        if rendered is not self.last_render:
            self.last_render = rendered
            if rendered and rendered.displayed:
                self.avatar.set_frame(qimage(rendered.preview),
                                      checkered=self.settings.background == "transparent")
            else:
                self.avatar.set_frame(None, "Добавьте neutral.png в коллекцию")
        width, height = self.settings.dimensions
        self.format_label.setText(f"{width} × {height}  ·  30 FPS")
        expression = EXPRESSIONS[output.expression]
        if rendered and rendered.displayed and rendered.displayed != output.expression:
            expression += "  →  neutral.png"
        self.expression.setText(expression)
        face = output.face
        self.pose.setText(
            f"Наклон {face.roll:+.0f}°  ·  Поворот {face.yaw:+.0f}°"
            if face else "Лицо вне кадра" if camera else "Камера недоступна",
        )

    def restore(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.restore()

    def closeEvent(self, event) -> None:
        if self.closing_at is None:
            self.closing_at = time.monotonic()
            self.save_timer.stop()
            self.persist()
            self.pipeline.stop()
            self.live.setText("Камеры отключаются…")
            self.centralWidget().setEnabled(False)
        if self.pipeline.is_alive():
            event.ignore()
        else:
            if self.tray:
                self.tray.hide()
            event.accept()
