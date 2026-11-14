from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil
import tempfile

from PIL import Image, ImageOps

from .settings import EXPRESSIONS


MAX_SOURCE_PIXELS = 25_000_000


def prepare_image(path: Path, png_only: bool = False) -> Image.Image:
    with Image.open(path) as source:
        if png_only and source.format != "PNG":
            raise ValueError("Выберите изображение в формате PNG.")
        if source.width * source.height > MAX_SOURCE_PIXELS:
            raise ValueError("Изображение превышает 25 мегапикселей.")
        image = ImageOps.exif_transpose(source).convert("RGBA")
    if png_only:
        box = image.getbbox(alpha_only=True)
        if box is None:
            raise ValueError("PNG полностью прозрачный.")
        image = image.crop(box)
    image.thumbnail((2560, 1440), Image.Resampling.LANCZOS)
    return image


@dataclass(frozen=True)
class AssetPack:
    hamsters: dict[str, Image.Image] = field(default_factory=dict)
    background: Image.Image | None = None

    def resolve(self, expression: str) -> str | None:
        if expression in self.hamsters:
            return expression
        return "neutral" if "neutral" in self.hamsters else None


class Collection:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def load(self) -> tuple[dict[str, Image.Image], list[str]]:
        images, invalid = {}, []
        for expression in EXPRESSIONS:
            path = self.directory / f"{expression}.png"
            if path.is_file():
                try:
                    images[expression] = prepare_image(path, png_only=True)
                except (OSError, ValueError, Image.DecompressionBombError):
                    invalid.append(path.name)
        return images, invalid

    def assign(self, expression: str, source: Path) -> None:
        if expression not in EXPRESSIONS:
            raise ValueError("Неизвестное выражение.")
        prepare_image(source, png_only=True)
        destination = self.directory / f"{expression}.png"
        # Preserve the uploaded original, including its transparent margins and metadata.
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.directory, delete=False) as temporary:
                temp_path = Path(temporary.name)
                with source.open("rb") as input_file:
                    shutil.copyfileobj(input_file, temporary)
            os.replace(temp_path, destination)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
