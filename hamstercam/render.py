from dataclasses import dataclass
import math

import cv2
import numpy as np
from PIL import Image, ImageOps

from .assets import AssetPack
from .expressions import Expression
from .settings import Settings


@dataclass(frozen=True)
class Rendered:
    rgb: np.ndarray
    preview: Image.Image
    displayed: str | None


class Renderer:
    FADE_SECONDS = 0.18

    def __init__(self) -> None:
        self.pack = None
        self.style = None
        self.base = None
        self.sprites = {}
        self.premultiplied = {}
        self.current = None
        self.previous = None
        self.changed_at = 0.0
        self.fade_from = None
        self.last_layer = None
        self.last_key = None
        self.last_render = None
        self.rest_size = 0.0

    def frame(self, pack: AssetPack, tracked: Expression, settings: Settings,
              now: float, *, cut: bool = False, manual: bool = False) -> Rendered:
        size = settings.dimensions
        style = (size, settings.background)
        if self.pack is not pack or self.style != style:
            self.pack, self.style = pack, style
            self.base = self.make_background(pack, settings, size)
            self.sprites = {
                name: ImageOps.contain(image, (round(size[0] * 0.79), round(size[1] * 0.79)),
                                       Image.Resampling.LANCZOS)
                for name, image in pack.hamsters.items()
            }
            self.premultiplied = {}
            self.current = self.previous = self.last_key = self.last_layer = self.fade_from = None

        requested = settings.manual_expression if manual else tracked.name
        displayed = pack.resolve(requested)
        if displayed != self.current:
            self.previous, self.current = self.current, displayed
            self.changed_at = now
            self.fade_from = self.last_layer
        if cut or not settings.fade:
            self.previous = self.fade_from = None
        mix = min(1.0, (now - self.changed_at) / self.FADE_SECONDS)
        if self.previous is None or mix >= 1.0:
            self.previous = self.fade_from = None
            mix = 1.0

        face = tracked.face
        if face and self.rest_size <= 0:
            self.rest_size = face.size
        reference = settings.baseline.get("faceSize", self.rest_size)
        scale = 1.0
        if settings.zoom and face and reference > 0:
            scale = max(0.87, min(1.15, 1 + 0.36 * (face.size / reference - 1)))
        angle = max(-12.0, min(12.0, face.roll * 0.55)) if settings.tilt and face else 0.0
        if settings.sway:
            angle += 1.8 * math.sin(now * 2.3)
        offset = 0
        if settings.bounce and displayed == "laughing":
            offset = -round(size[1] * 0.025 * abs(math.sin(now * 9)))
        key = (displayed, self.previous, round(mix * 255), round(angle, 2),
               round(scale, 3), offset, settings.mirror)
        if key == self.last_key:
            return self.last_render
        self.last_key = key

        if self.current is None:
            composed = self.base
            self.last_layer = None
        elif self.fade_from is None:
            # On steady frames only composite the sprite rectangle.
            sprite = self.transform(self.current, angle, scale, settings.mirror)
            origin = ((size[0] - sprite.width) // 2, (size[1] - sprite.height) // 2 + offset)
            composed = self.base.copy()
            composed.alpha_composite(sprite, origin)
            self.last_layer = (sprite, origin)
        else:
            sprite = self.transform(self.current, angle, scale, settings.mirror)
            origin = ((size[0] - sprite.width) // 2, (size[1] - sprite.height) // 2 + offset)
            old, old_origin = self.fade_from
            x, y = min(origin[0], old_origin[0]), min(origin[1], old_origin[1])
            right = max(origin[0] + sprite.width, old_origin[0] + old.width)
            bottom = max(origin[1] + sprite.height, old_origin[1] + old.height)
            previous = Image.new("RGBA", (right - x, bottom - y))
            current = previous.copy()
            previous.paste(old, (old_origin[0] - x, old_origin[1] - y))
            current.paste(sprite, (origin[0] - x, origin[1] - y))
            # Blend premultiplied alpha so fading outlines do not pick up a dark halo.
            sprite = Image.blend(previous.convert("RGBa"), current.convert("RGBa"), mix).convert("RGBA")
            composed = self.base.copy()
            composed.alpha_composite(sprite, (x, y))
            self.last_layer = (sprite, (x, y))

        if settings.background == "transparent":
            opaque = Image.new("RGB", size, "white")
            opaque.paste(composed, mask=composed.getchannel("A"))
        else:
            opaque = composed.convert("RGB")
        preview = Image.fromarray(cv2.resize(np.asarray(composed), (640, 360), interpolation=cv2.INTER_NEAREST))
        self.last_render = Rendered(np.asarray(opaque), preview, displayed)
        return self.last_render

    @staticmethod
    def make_background(pack: AssetPack, settings: Settings, size: tuple[int, int]) -> Image.Image:
        if settings.background == "transparent":
            return Image.new("RGBA", size)
        if settings.background == "green":
            return Image.new("RGBA", size, (0, 255, 0, 255))
        background = Image.new("RGBA", size, "white")
        if settings.background == "custom" and pack.background is not None:
            background.alpha_composite(ImageOps.fit(pack.background, size, Image.Resampling.LANCZOS))
        return background

    def transform(self, name: str, angle: float, scale: float, mirror: bool) -> Image.Image:
        image = self.sprites[name]
        if scale == 1 and angle == 0:
            return ImageOps.mirror(image) if mirror else image
        if name not in self.premultiplied:
            self.premultiplied[name] = np.asarray(image.convert("RGBa"))
        source = self.premultiplied[name]
        center = ((image.width - 1) / 2, (image.height - 1) / 2)
        transform = cv2.getRotationMatrix2D(center, angle, scale)
        cosine, sine = abs(transform[0, 0]), abs(transform[0, 1])
        width = math.ceil(image.width * cosine + image.height * sine)
        height = math.ceil(image.width * sine + image.height * cosine)
        transform[:, 2] += ((width - image.width) / 2, (height - image.height) / 2)
        if mirror:
            transform[0, :2] *= -1
            transform[0, 2] = width - 1 - transform[0, 2]
        result = cv2.warpAffine(source, transform, (width, height))
        return Image.frombytes("RGBa", (width, height), result.tobytes()).convert("RGBA")
