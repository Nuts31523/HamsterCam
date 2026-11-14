from contextlib import AbstractContextManager

import numpy as np
import pyvirtualcam

from .render import Rendered
from .settings import FPS


class VirtualCamera(AbstractContextManager):
    def __init__(self, size: tuple[int, int]) -> None:
        try:
            self.camera = pyvirtualcam.Camera(
                width=size[0], height=size[1], fps=FPS,
                fmt=pyvirtualcam.PixelFormat.RGB, backend="obs",
            )
        except RuntimeError as error:
            raise RuntimeError(
                "Не удалось открыть OBS Virtual Camera. Установите OBS Studio "
                "и остановите его виртуальную камеру, если она запущена.\n"
                f"{error}"
            ) from error
        self.size = size

    @property
    def name(self) -> str:
        return self.camera.device

    def send(self, frame: Rendered) -> None:
        rgb = frame.rgb
        if rgb.shape != (self.size[1], self.size[0], 3) or rgb.dtype != np.uint8:
            raise ValueError("Недопустимый формат кадров виртуальной камеры")
        self.camera.send(rgb)

    def __exit__(self, *args) -> None:
        self.camera.close()
