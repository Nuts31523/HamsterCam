from dataclasses import dataclass
import time

import cv2
from cv2_enumerate_cameras import enumerate_cameras
import numpy as np


@dataclass(frozen=True)
class Device:
    index: int
    backend: int
    name: str
    path: str

    @property
    def identifier(self) -> str:
        return self.path.casefold() if self.path else f"{self.backend}:{self.name}:{self.index}"


@dataclass(frozen=True)
class CameraFrame:
    generation: int
    captured_at: float
    bgr: np.ndarray


def list_devices() -> list[Device]:
    for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF):
        devices = [
            Device(item.index, item.backend, item.name, item.path or "")
            for item in enumerate_cameras(backend)
            if not any(marker in item.name.casefold() for marker in (
                "virtual", "unity capture", "manycam", "splitcam", "snap camera", "виртуаль",
            ))
        ]
        if devices:
            return devices
    return []


def open_camera(device: Device) -> cv2.VideoCapture:
    capture = cv2.VideoCapture()
    try:
        if not capture.open(device.index, device.backend):
            raise RuntimeError(f"Не удалось открыть «{device.name}»")
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        capture.set(cv2.CAP_PROP_FPS, 30)
        return capture
    except BaseException:
        capture.release()
        raise


def read_frame(capture: cv2.VideoCapture, generation: int) -> CameraFrame | None:
    success, frame = capture.read()
    if success and frame is not None and frame.size:
        if frame.shape[1] > 640:
            height = max(1, round(frame.shape[0] * 640 / frame.shape[1]))
            frame = cv2.resize(frame, (640, height), interpolation=cv2.INTER_AREA)
        return CameraFrame(generation, time.monotonic(), frame)
    return None
