"""Источник камеры без камеры: разбор результата mediapipe и статусы. Нужен установленный mediapipe —
без него тесты пропускаются (pytest.importorskip), остальной набор проходит."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from reddome.config.camera import CameraSettings
from reddome.input.camera import MediaPipeGestureSource, parse_result


def test_parse_result_maps_handedness_and_best_gesture() -> None:
    pytest.importorskip("mediapipe")
    from mediapipe.tasks.python.components.containers.category import Category
    from mediapipe.tasks.python.vision import GestureRecognizerResult

    result = GestureRecognizerResult(
        gestures=[[Category(score=0.91, category_name="Open_Palm")], [Category(score=0.77, category_name="Victory")]],
        handedness=[[Category(score=0.98, category_name="Left")], [Category(score=0.95, category_name="Right")]],
        hand_landmarks=[[], []],
        hand_world_landmarks=[[], []],
    )
    frames = parse_result(result)
    assert [(f.gesture, f.hand, round(f.score, 2)) for f in frames] == [("Open_Palm", "left", 0.91), ("Victory", "right", 0.77)]


def test_missing_model_reports_no_model_without_opening_camera(tmp_path: Path) -> None:
    pytest.importorskip("mediapipe")
    pytest.importorskip("cv2")
    source = MediaPipeGestureSource(CameraSettings(model_path=tmp_path / "нет.task"))
    source.start()
    deadline = time.monotonic() + 10
    while source.status == "starting" and time.monotonic() < deadline:
        time.sleep(0.05)
    source.stop()
    assert source.status == "no_model"
    assert source.poll() is None


def test_recognizer_finds_no_hands_on_blank_frame() -> None:
    mp = pytest.importorskip("mediapipe")
    np = pytest.importorskip("numpy")
    settings = CameraSettings()
    if not settings.model_path.exists():
        pytest.skip("нет models/gesture_recognizer.task")
    from mediapipe.tasks.python import vision
    from mediapipe.tasks.python.core.base_options import BaseOptions

    options = vision.GestureRecognizerOptions(
        base_options=BaseOptions(model_asset_path=str(settings.model_path)),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=2,
    )
    with vision.GestureRecognizer.create_from_options(options) as recognizer:
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.zeros((240, 320, 3), np.uint8))
        assert parse_result(recognizer.recognize_for_video(image, 1)) == []


class _FakeCapture:
    def __init__(self, opened: bool) -> None:
        self.opened = opened
        self.released = False

    def isOpened(self) -> bool:  # noqa: N802 — имя как у cv2.VideoCapture
        return self.opened

    def set(self, *args: object) -> None:
        pass

    def release(self) -> None:
        self.released = True


class _FakeCv2:
    CAP_MSMF, CAP_DSHOW, CAP_ANY = 1400, 700, 0
    CAP_PROP_FRAME_WIDTH, CAP_PROP_FRAME_HEIGHT = 3, 4

    def __init__(self, working: set[int]) -> None:
        self.working = working
        self.tried: list[int] = []

    def VideoCapture(self, index: int, api: int) -> _FakeCapture:  # noqa: N802
        self.tried.append(api)
        return _FakeCapture(api in self.working)


def test_open_capture_tries_backends_in_order() -> None:
    """Этап 3: камера открывается через раз — пробуем MSMF, DirectShow, потом выбор OpenCV."""
    source = MediaPipeGestureSource(CameraSettings())
    fake = _FakeCv2({_FakeCv2.CAP_ANY})
    assert source._open_capture(fake) is not None
    assert fake.tried == [_FakeCv2.CAP_MSMF, _FakeCv2.CAP_DSHOW, _FakeCv2.CAP_ANY]
    fake = _FakeCv2(set())
    assert source._open_capture(fake) is None
