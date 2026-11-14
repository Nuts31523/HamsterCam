from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from hamstercam.assets import AssetPack, Collection
from hamstercam.camera import CameraFrame, Device
from hamstercam.expressions import Expression, ExpressionTracker, Face
from hamstercam.pipeline import Pipeline
from hamstercam.render import Renderer
from hamstercam.settings import Settings, load_settings, save_settings


class ExpressionsTest(unittest.TestCase):
    def test_expressions_with_hold_and_face_loss(self):
        settings = Settings(smoothing=0, hold_ms=100)
        samples = {
            "happy": {"mouthSmileLeft": .72, "mouthSmileRight": .78},
            "angry": {"browDownLeft": .65, "browDownRight": .72},
            "surprised": {"jawOpen": .69, "eyeWideLeft": .4, "eyeWideRight": .4},
            "sad": {"mouthFrownLeft": .43, "mouthFrownRight": .39, "browInnerUp": .36},
            "laughing": {"mouthSmileLeft": .8, "mouthSmileRight": .8, "jawOpen": .49},
            "crying": {
                "mouthFrownLeft": .4, "mouthFrownRight": .4, "browInnerUp": .56,
                "eyeSquintLeft": .59, "eyeSquintRight": .59,
            },
            "smirk": {"mouthSmileLeft": .66, "mouthSmileRight": .05},
            "suspicious": {"browOuterUpLeft": .52, "browOuterUpRight": .07},
        }
        for expected, features in samples.items():
            with self.subTest(expected=expected):
                tracker = ExpressionTracker()
                self.assertEqual(tracker.update(Face(features), 1, settings).name, "neutral")
                self.assertEqual(tracker.update(Face(features), 1.12, settings).name, expected)
                self.assertEqual(tracker.update(None, 1.16, settings), Expression())

    def test_only_sustained_eye_closure_selects_sleepy(self):
        settings = Settings(hold_ms=0, smoothing=0)
        eyes = Face({"eyeBlinkLeft": .9, "eyeBlinkRight": .92})
        tracker = ExpressionTracker()
        self.assertEqual(tracker.update(eyes, 1.0, settings).name, "neutral")
        self.assertEqual(tracker.update(Face(), 1.14, settings).name, "neutral")
        self.assertEqual(tracker.update(eyes, 1.3, settings).name, "neutral")
        self.assertEqual(tracker.update(eyes, 2.5, settings).name, "sleepy")


class AssetsTest(unittest.TestCase):
    def test_import_preserves_png_and_roundtrips_settings(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "original.png"
            image = Image.new("RGBA", (20, 40))
            image.paste("red", (5, 10, 15, 30))
            image.save(source)
            collection = Collection(root / "hamsters")
            collection.assign("neutral", source)
            self.assertEqual((collection.directory / "neutral.png").read_bytes(), source.read_bytes())
            images, invalid = collection.load()
            self.assertEqual(invalid, [])
            self.assertEqual(images["neutral"].size, (10, 20))
            settings = Settings(height=1080, baseline={"jawOpen": .026})
            save_settings(settings, root / "settings.json")
            self.assertEqual(load_settings(root / "settings.json"), settings)

    def test_transparency_fade_and_resolution(self):
        pack = AssetPack({
            "neutral": Image.new("RGBA", (45, 80), (255, 0, 0, 255)),
            "happy": Image.new("RGBA", (45, 80), (0, 0, 255, 255)),
        })
        settings = Settings(height=1080, background="transparent", mirror=False, fade=True)
        renderer = Renderer()
        frame = renderer.frame(pack, Expression("sad"), settings, 1)
        self.assertEqual(frame.displayed, "neutral")
        self.assertEqual(frame.rgb.shape, (1080, 1920, 3))
        self.assertEqual(frame.preview.getpixel((0, 0))[3], 0)
        self.assertEqual(tuple(frame.rgb[0, 0]), (255, 255, 255))
        renderer.frame(pack, Expression("happy"), settings, 2)
        mid = renderer.frame(pack, Expression("happy"), settings, 2.09)
        self.assertTrue(90 < mid.rgb[540, 960, 0] < 170)
        self.assertTrue(90 < mid.rgb[540, 960, 2] < 170)
        lost = renderer.frame(pack, Expression(), settings, 2.1, cut=True)
        self.assertEqual(tuple(lost.rgb[540, 960]), (255, 0, 0))


class PipelineTest(unittest.TestCase):
    def test_publishes_painted_pixels_and_releases_on_stop(self):
        pack = AssetPack({
            "neutral": Image.new("RGBA", (32, 32), (255, 0, 0, 255)),
            "happy": Image.new("RGBA", (32, 32), (0, 0, 255, 255)),
        })
        camera_released, sink_closed = [], []
        received = []
        capture_available = True
        raw = np.zeros((480, 640, 3), dtype=np.uint8)
        raw[:, :] = (0, 255, 0)

        class Capture:
            def release(self):
                camera_released.append(True)

        def read(_capture, generation):
            time.sleep(.02)
            if capture_available:
                return CameraFrame(generation, time.monotonic(), raw)
            return None

        class Detector:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def detect(self, bgr, _captured_at):
                if bgr is not raw:
                    raise AssertionError("The detector should receive the local frame.")
                return Face({"mouthSmileLeft": .8, "mouthSmileRight": .8})

        class Sink:
            name = "Test sink"

            def __init__(self, size):
                self.size = size

            def __enter__(self):
                return self

            def __exit__(self, *_):
                sink_closed.append(self.size)

            def send(self, frame):
                height, width, _ = frame.rgb.shape
                received.append((frame.rgb.shape, tuple(frame.rgb[height // 2, width // 2])))

        with (
            patch("hamstercam.pipeline.open_camera", return_value=Capture()),
            patch("hamstercam.pipeline.read_frame", side_effect=read),
            patch("hamstercam.pipeline.Landmarker", Detector),
            patch("hamstercam.pipeline.VirtualCamera", Sink),
        ):
            pipeline = Pipeline(Settings(hold_ms=0), pack)
            try:
                pipeline.select_device(Device(0, 700, "Test input", ""))
                pipeline.start_output()
                self.wait_for(lambda: ((720, 1280, 3), (0, 0, 255)) in received)
                pipeline.settings.write(replace(pipeline.settings.read(), height=1080))
                self.wait_for(lambda: ((1080, 1920, 3), (0, 0, 255)) in received)
                capture_available = False
                self.wait_for(lambda: ((1080, 1920, 3), (255, 0, 0)) in received)
                self.assertNotIn((0, 255, 0), {color for _, color in received})
                pipeline.stop_output()
                self.wait_for(lambda: (1920, 1080) in sink_closed)
            finally:
                pipeline.stop()
                self.wait_for(lambda: not pipeline.is_alive())
            self.assertIn((1280, 720), sink_closed)
            self.assertTrue(camera_released)

    def wait_for(self, condition):
        deadline = time.monotonic() + 5
        while not condition() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(condition())
