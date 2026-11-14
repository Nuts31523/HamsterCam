from contextlib import AbstractContextManager
import math

import cv2
import mediapipe as mp
import numpy as np

from .expressions import Face
from .settings import MODEL_PATH


class Landmarker(AbstractContextManager):
    def __init__(self) -> None:
        if not MODEL_PATH.is_file():
            raise FileNotFoundError("Модель не установлена. Выполните setup.ps1.")
        vision = mp.tasks.vision
        self.detector = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_buffer=MODEL_PATH.read_bytes()),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        ))
        self.timestamp = -1

    def __exit__(self, *args) -> None:
        self.detector.close()

    def detect(self, bgr: np.ndarray, captured_at: float) -> Face | None:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        self.timestamp = max(self.timestamp + 1, int(captured_at * 1000))
        result = self.detector.detect_for_video(image, self.timestamp)
        if not result.face_landmarks or not result.face_blendshapes:
            return None
        features = {item.category_name: item.score for item in result.face_blendshapes[0]}
        points = result.face_landmarks[0]
        height, width = bgr.shape[:2]

        def distance(a: int, b: int) -> float:
            return math.hypot((points[a].x - points[b].x) * width,
                              (points[a].y - points[b].y) * height)

        face_width = max(distance(234, 454), 1)
        features["aperture"] = distance(13, 14) / max(distance(61, 291), 1)
        features["mouthWidth"] = distance(61, 291) / face_width

        roll = yaw = pitch = 0.0
        if result.facial_transformation_matrixes:
            rotation = result.facial_transformation_matrixes[0][:3, :3]
            rotation = rotation / np.maximum(np.linalg.norm(rotation, axis=0), 1e-6)
            roll = math.degrees(math.atan2(rotation[1, 0], rotation[0, 0]))
            yaw = math.degrees(math.asin(float(np.clip(-rotation[2, 0], -1, 1))))
            pitch = math.degrees(math.atan2(rotation[2, 1], rotation[2, 2]))
        return Face(features, roll, yaw, pitch, face_width / width)
