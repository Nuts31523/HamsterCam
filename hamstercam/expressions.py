from dataclasses import dataclass, field
import math

from .settings import Settings


@dataclass(frozen=True)
class Face:
    features: dict[str, float] = field(default_factory=dict)
    roll: float = 0.0
    yaw: float = 0.0
    pitch: float = 0.0
    size: float = 0.0


@dataclass(frozen=True)
class Expression:
    name: str = "neutral"
    face: Face | None = None


class ExpressionTracker:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.face = None
        self.last_at = None
        self.closed_since = None
        self.active = "neutral"
        self.pending = "neutral"
        self.pending_since = 0.0

    def update(self, face: Face | None, now: float, settings: Settings) -> Expression:
        if face is None:
            self.reset()
            return Expression()
        if self.face is not None:
            elapsed = min(0.25, max(0.001, now - self.last_at))
            speed = 0.018 + 0.145 * settings.smoothing / 100
            weight = 1.0 - math.exp(-elapsed / speed)

            def smooth(old: float, new: float) -> float:
                return old + weight * (new - old)

            face = Face(
                {key: smooth(self.face.features.get(key, value), value)
                 for key, value in face.features.items()},
                smooth(self.face.roll, face.roll),
                smooth(self.face.yaw, face.yaw),
                smooth(self.face.pitch, face.pitch),
                smooth(self.face.size, face.size),
            )
        self.face = face
        self.last_at = now
        candidate = self.classify(face, now, settings)
        if candidate != self.pending:
            self.pending, self.pending_since = candidate, now
        if now - self.pending_since >= settings.hold_ms / 1000:
            self.active = self.pending
        return Expression(self.active, face)

    def classify(self, face: Face, now: float, settings: Settings) -> str:
        raw = face.features.get
        baseline = settings.baseline

        def score(key: str) -> float:
            value = raw(key, 0.0)
            rest = min(0.6, baseline.get(key, 0.0))
            return max(0.0, (value - rest) / (1.0 - rest))

        def pair(prefix: str) -> tuple[float, float]:
            return score(prefix + "Left"), score(prefix + "Right")

        def average(prefix: str) -> float:
            return sum(pair(prefix)) / 2

        left, right = pair("mouthSmile")
        smile = (left + right) / 2
        asymmetry = abs(left - right)
        downturn = average("mouthFrown")
        brow_down = average("browDown")
        inner_brow = score("browInnerUp")
        outer_brow = abs(pair("browOuterUp")[0] - pair("browOuterUp")[1])
        aperture = max(0.0, raw("aperture", 0.0) - baseline.get("aperture", 0.02))
        jaw_open = score("jawOpen")
        jaw = max(jaw_open, min(1.0, aperture * 2.2))
        eye_wide = average("eyeWide")
        squint = max(average("eyeSquint"), average("eyeBlink") * 0.8)
        width = raw("mouthWidth", 0.0) - baseline.get("mouthWidth", 0.37)
        smile = max(0.0, smile + 0.35 * max(0.0, width))

        threshold_scale = 1.24 - settings.sensitivity * 0.0048

        def at_least(name: str, value: float, threshold: float) -> bool:
            hysteresis = 0.83 if self.active == name else 1.0
            return value >= threshold * threshold_scale * hysteresis

        eyes_closed = min(pair("eyeBlink")) >= (0.48 if self.active == "sleepy" else 0.61)
        if eyes_closed:
            self.closed_since = now if self.closed_since is None else self.closed_since
        else:
            self.closed_since = None
        sleepy = self.closed_since is not None and now - self.closed_since >= 1.1

        matches = {
            "laughing": at_least("laughing", smile, 0.43)
            and (jaw_open >= 0.25 or aperture >= 0.22)
            and (squint >= 0.16 or jaw >= 0.43),
            "crying": at_least("crying", inner_brow, 0.33) and smile < 0.28
            and downturn >= 0.15 and (squint >= 0.38 or jaw >= 0.25),
            "sleepy": sleepy,
            "surprised": at_least("surprised", jaw, 0.39) and smile < 0.35
            and (eye_wide >= 0.10 or inner_brow >= 0.13 or jaw >= 0.53),
            "angry": at_least("angry", brow_down, 0.31) and smile < 0.29
            and (inner_brow < 0.28 or brow_down > inner_brow),
            "suspicious": at_least("suspicious", outer_brow, 0.27) and jaw < 0.31
            and abs(face.yaw) < 25,
            "smirk": at_least("smirk", asymmetry, 0.23) and jaw < 0.27
            and min(left, right) < 0.28 and abs(face.yaw) < 25,
            "happy": at_least("happy", smile, 0.31),
            "sad": at_least("sad", downturn, 0.19) and inner_brow > 0.17 and smile < 0.24,
        }
        return next((name for name in settings.priority if matches[name]), "neutral")
