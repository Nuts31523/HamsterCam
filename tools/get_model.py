import hashlib
from pathlib import Path
import urllib.request


MODEL = Path(__file__).resolve().parents[1] / "models" / "face_landmarker.task"
URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
DIGEST = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"


def main() -> None:
    if MODEL.is_file() and hashlib.sha256(MODEL.read_bytes()).hexdigest() == DIGEST:
        print("Face Landmarker model verified.")
        return
    with urllib.request.urlopen(URL, timeout=45) as response:
        data = response.read(5 * 1024 * 1024)
    if hashlib.sha256(data).hexdigest() != DIGEST:
        raise RuntimeError("The Face Landmarker model checksum does not match.")
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    temporary = MODEL.with_suffix(".download")
    temporary.write_bytes(data)
    temporary.replace(MODEL)
    print("Face Landmarker model downloaded and verified.")


if __name__ == "__main__":
    main()
