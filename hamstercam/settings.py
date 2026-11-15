from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import sys
import tempfile


EXPRESSIONS = {
    "neutral": "Нейтральное",
    "happy": "Улыбка",
    "laughing": "Смех",
    "angry": "Нахмуренные брови",
    "sad": "Грустное выражение",
    "crying": "Плачущее выражение",
    "surprised": "Удивление",
    "smirk": "Ухмылка",
    "suspicious": "Поднятая бровь",
    "sleepy": "Закрытые глаза",
    "thinking": "Задумчивость",
}
DEFAULT_PRIORITY = (
    "laughing", "crying", "sleepy", "surprised", "thinking", "angry",
    "suspicious", "smirk", "happy", "sad",
)
BACKGROUNDS = {
    "white": "Белый",
    "transparent": "Прозрачный (предпросмотр)",
    "green": "Зелёный",
    "custom": "Своё изображение",
}
FPS = 30
ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "models" / "face_landmarker.task"
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "HamsterCam"
COLLECTION_DIR = (DATA_DIR if getattr(sys, "frozen", False) else ROOT) / "assets" / "hamsters"
SETTINGS_PATH = DATA_DIR / "settings.json"


@dataclass(frozen=True)
class Settings:
    camera_id: str = ""
    height: int = 720
    sensitivity: int = 50
    hold_ms: int = 220
    smoothing: int = 50
    background: str = "white"
    custom_background: str = ""
    mirror: bool = True
    auto: bool = True
    manual_expression: str = "neutral"
    sway: bool = False
    tilt: bool = False
    zoom: bool = False
    fade: bool = False
    bounce: bool = False
    priority: tuple[str, ...] = DEFAULT_PRIORITY
    baseline: dict[str, float] = field(default_factory=dict)

    @property
    def dimensions(self) -> tuple[int, int]:
        return (1920, 1080) if self.height == 1080 else (1280, 720)


def load_settings(path: Path = SETTINGS_PATH) -> Settings:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(data, dict):
        return Settings()

    defaults = Settings()
    values = {}
    for name, default in asdict(defaults).items():
        value = data.get(name, default)
        if type(value) is type(default):
            values[name] = value
    for name, maximum in (("sensitivity", 100), ("smoothing", 100), ("hold_ms", 1500)):
        values[name] = min(maximum, max(0, values.get(name, getattr(defaults, name))))
    values["height"] = 1080 if data.get("height") == 1080 else 720
    for name, choices in (("background", BACKGROUNDS), ("manual_expression", EXPRESSIONS)):
        if values.get(name) not in choices:
            values.pop(name, None)
    priority = data.get("priority")
    if isinstance(priority, list) and all(isinstance(item, str) for item in priority):
        if (len(priority) == len(DEFAULT_PRIORITY) - 1
                and set(priority) == set(DEFAULT_PRIORITY) - {"thinking"}):
            first_overlap = min(priority.index("sad"), priority.index("angry"))
            priority.insert(first_overlap, "thinking")
        if len(priority) == len(DEFAULT_PRIORITY) and set(priority) == set(DEFAULT_PRIORITY):
            values["priority"] = tuple(priority)
    values["baseline"] = {
        key: float(value) for key, value in values.get("baseline", {}).items()
        if type(value) in (int, float) and 0 <= value <= 2
    }
    return Settings(**values)


def save_settings(settings: Settings, path: Path = SETTINGS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, mode="w", encoding="utf-8", delete=False,
        ) as file:
            temporary = Path(file.name)
            json.dump(asdict(settings), file, ensure_ascii=False, indent=2)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
