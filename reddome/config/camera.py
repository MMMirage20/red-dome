"""Настройки камеры для жестов (W3-12). Это настройки устройства, а не баланс: пороги жестов —
в balance.json → gestures. Меняются флагами запуска: --camera N, --no-gestures, --gesture-keys, --swap-hands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


@dataclass(frozen=True)
class CameraSettings:
    #: Распознавать жесты с камеры.
    enabled: bool = True
    #: Номер камеры для cv2.VideoCapture.
    index: int = 0
    #: Превью в оверлее показывать зеркально, как в селфи. На распознавание не влияет:
    #: mediapipe ждёт незеркальный кадр («Left/Right — руки самого человека»).
    mirror_preview: bool = True
    #: Поменять левую и правую руку, если на конкретной камере они перепутаны.
    swap_hands: bool = False
    #: Эмуляция жестов клавишами F1–F8 (тесты, отладка, запасной план на защите).
    keys: bool = False
    #: Файл модели Gesture Recognizer (скачивается отдельно, см. README).
    model_path: Path = field(default=MODELS_DIR / "gesture_recognizer.task")

    @staticmethod
    def off() -> CameraSettings:
        """Без камеры и без эмуляции — так App создаётся в тестах."""
        return CameraSettings(enabled=False)
