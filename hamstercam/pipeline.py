from contextlib import ExitStack
from dataclasses import dataclass
from statistics import median
from threading import Event, Lock, Thread
import time
from typing import Generic, TypeVar

from .assets import AssetPack
from .camera import CameraFrame, Device, open_camera, read_frame
from .expressions import Expression, ExpressionTracker, Face
from .landmarks import Landmarker
from .render import Rendered, Renderer
from .settings import FPS, Settings
from .virtual_camera import VirtualCamera


T = TypeVar("T")
MAX_FRAME_AGE = 0.65


class Latest(Generic[T]):
    """A single slot, so a slow consumer cannot build up a backlog of camera frames."""

    def __init__(self, initial: T) -> None:
        self._lock = Lock()
        self._value = initial

    def read(self) -> T:
        with self._lock:
            return self._value

    def write(self, value: T) -> None:
        with self._lock:
            self._value = value


@dataclass(frozen=True)
class Tracking:
    frame_at: float = 0.0
    generation: int = -1
    expression: Expression = Expression()


@dataclass(frozen=True)
class Output:
    rendered: Rendered | None = None
    expression: str = "neutral"
    face: Face | None = None
    fps: float = 0.0
    device: str = ""
    error: str = ""


@dataclass(frozen=True)
class Calibration:
    message: str = ""
    baseline: dict[str, float] | None = None


class Pipeline:
    def __init__(self, settings: Settings, assets: AssetPack) -> None:
        self.settings = Latest(settings)
        self.assets = Latest(assets)
        self.device = Latest[tuple[int, Device | None]]((0, None))
        self.camera_frame = Latest[CameraFrame | None](None)
        self.camera_health = Latest((-1, 0.0))
        self.camera_status = Latest("")
        self.tracking = Latest(Tracking())
        self.tracking_status = Latest("")
        self.output = Latest(Output())
        self.calibration = Latest(Calibration())
        self._calibrate = Event()
        self._running_output = Event()
        self._stopping = Event()
        self._threads = [
            Thread(target=worker, name=name, daemon=True)
            for name, worker in (
                ("Camera capture", self._capture_loop),
                ("Face Landmarker", self._tracking_loop),
                ("Virtual camera output", self._output_loop),
            )
        ]
        for thread in self._threads:
            thread.start()

    @property
    def output_requested(self) -> bool:
        return self._running_output.is_set()

    def select_device(self, device: Device | None) -> None:
        epoch, _ = self.device.read()
        self.device.write((epoch + 1, device))

    def start_output(self) -> None:
        self._running_output.set()

    def stop_output(self) -> None:
        self._running_output.clear()

    def calibrate(self) -> None:
        self._calibrate.set()

    def stop(self) -> None:
        self._stopping.set()

    def is_alive(self) -> bool:
        return any(thread.is_alive() for thread in self._threads)

    def _capture_loop(self) -> None:
        capture = None
        generation, retry_at, last_frame_at = -1, 0.0, 0.0
        try:
            while not self._stopping.is_set():
                epoch, device = self.device.read()
                if epoch != generation:
                    if capture is not None:
                        capture.release()
                        capture = None
                    self.camera_frame.write(None)
                    self.camera_health.write((epoch, 0.0))
                    generation, retry_at = epoch, 0.0
                    self.camera_status.write("Открываю камеру…" if device else "Выберите физическую камеру")
                now = time.monotonic()
                if device is None or now < retry_at:
                    self._stopping.wait(0.05)
                    continue
                try:
                    if capture is None:
                        capture = open_camera(device)
                        last_frame_at = time.monotonic()
                    frame = read_frame(capture, generation)
                    if frame is not None:
                        self.camera_frame.write(frame)
                        self.camera_health.write((frame.generation, frame.captured_at))
                        last_frame_at = frame.captured_at
                        self.camera_status.write("")
                    elif time.monotonic() - last_frame_at > MAX_FRAME_AGE:
                        raise RuntimeError("Камера перестала передавать кадры")
                    else:
                        self._stopping.wait(0.02)
                except Exception as error:
                    self.camera_frame.write(None)
                    self.camera_health.write((generation, 0.0))
                    self.camera_status.write(f"{error}. Повторное подключение…")
                    if capture is not None:
                        capture.release()
                        capture = None
                    retry_at = time.monotonic() + 1.5
        finally:
            if capture is not None:
                capture.release()
            self.camera_frame.write(None)
            self.camera_health.write((-1, 0.0))

    def _tracking_loop(self) -> None:
        tracker = ExpressionTracker()
        last_at, generation = 0.0, -1
        calibration_started = None
        calibration_epoch = -1
        samples: list[Face] = []
        detector = None
        retry_at = 0.0
        with ExitStack() as resources:
            while not self._stopping.is_set():
                now = time.monotonic()
                epoch, _ = self.device.read()
                if self._calibrate.is_set():
                    self._calibrate.clear()
                    calibration_started = now
                    calibration_epoch = epoch
                    samples.clear()
                    self.calibration.write(Calibration("Смотрите прямо, расслабьте лицо и держите глаза открытыми."))
                if calibration_started is not None and calibration_epoch != epoch:
                    calibration_started = None
                    self.calibration.write(Calibration("Камера изменена. Запустите калибровку заново."))
                if calibration_started is not None and now - calibration_started > 5.0:
                    calibration_started = None
                    self.calibration.write(Calibration("Калибровка не завершена. Расположите лицо в кадре и повторите."))
                frame = self.camera_frame.read()
                if frame is None or frame.generation != epoch or now - frame.captured_at > MAX_FRAME_AGE:
                    if last_at:
                        tracker.reset()
                        self.tracking.write(Tracking())
                        last_at = 0.0
                    self._stopping.wait(0.02)
                    continue
                if frame.captured_at == last_at or now < retry_at:
                    self._stopping.wait(0.006)
                    continue
                if generation != epoch:
                    tracker.reset()
                    if generation != -1:
                        resources.close()
                        detector = None
                    generation = epoch
                try:
                    if detector is None:
                        detector = resources.enter_context(Landmarker())
                    face = detector.detect(frame.bgr, frame.captured_at)
                    expression = tracker.update(face, frame.captured_at, self.settings.read())
                    self.tracking.write(Tracking(frame.captured_at, generation, expression))
                    self.tracking_status.write("")
                except Exception as error:
                    self.tracking_status.write(f"Ошибка распознавания: {error}")
                    self.tracking.write(Tracking())
                    tracker.reset()
                    resources.close()
                    detector = None
                    face = None
                    retry_at = time.monotonic() + 3.0
                last_at = frame.captured_at
                if calibration_started is not None:
                    if face is None or abs(face.yaw) > 18 or abs(face.pitch) > 20:
                        samples.clear()
                    elif max(face.features.get("eyeBlinkLeft", 0),
                             face.features.get("eyeBlinkRight", 0)) < 0.35:
                        samples.append(face)
                    if len(samples) >= 16 and now - calibration_started >= 1.3:
                        baseline = {
                            key: median(face.features[key] for face in samples)
                            for key in samples[0].features
                        }
                        baseline["faceSize"] = median(face.size for face in samples)
                        tracker.reset()
                        calibration_started = None
                        self.calibration.write(Calibration("Нейтральное лицо откалибровано.", baseline))

    def _output_loop(self) -> None:
        renderer = Renderer()
        sink = None
        error = ""
        next_at = time.monotonic()
        meter_at, sent, fps = next_at, 0, 0.0
        with ExitStack() as resources:
            while not self._stopping.is_set():
                now = time.monotonic()
                settings, pack = self.settings.read(), self.assets.read()
                epoch, _ = self.device.read()
                # Only derived features cross into the renderer. Raw frames stay in capture,
                # Face Landmarker and the local camera preview.
                tracked = self.tracking.read()
                camera_epoch, camera_at = self.camera_health.read()
                has_camera = camera_epoch == epoch and now - camera_at < MAX_FRAME_AGE
                valid = (
                    has_camera and tracked.generation == epoch
                    and now - tracked.frame_at < MAX_FRAME_AGE
                    and tracked.expression.face is not None
                )
                expression = tracked.expression if valid else Expression()
                manual = valid and not settings.auto
                requested = settings.manual_expression if manual else expression.name
                rendered = None
                try:
                    if sink is not None and (
                        not self.output_requested or sink.size != settings.dimensions
                    ):
                        resources.close()
                        sink = None
                        sent, fps = 0, 0.0
                    rendered = renderer.frame(pack, expression, settings, now,
                                              cut=not (valid or manual), manual=manual)
                    if self.output_requested and sink is None:
                        error = ""
                        if "neutral" not in pack.hamsters:
                            raise RuntimeError("Загрузите neutral.png в коллекцию.")
                        sink = resources.enter_context(VirtualCamera(settings.dimensions))
                        meter_at, sent = now, 0
                    if sink is not None and self.output_requested and not self._stopping.is_set():
                        sink.send(rendered)
                        sent += 1
                        if now - meter_at >= 1.0:
                            fps, meter_at, sent = sent / (now - meter_at), now, 0
                except Exception as failure:
                    self._running_output.clear()
                    resources.close()
                    sink = None
                    sent, fps = 0, 0.0
                    error = str(failure)
                    if rendered is None:
                        renderer = Renderer()
                self.output.write(Output(rendered, requested, expression.face, fps,
                                         sink.name if sink is not None else "", error))
                next_at = max(next_at + 1 / FPS, now)
                self._stopping.wait(max(0.0, next_at - time.monotonic()))
        self.output.write(Output())
