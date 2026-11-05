"""Сервис жестов (W3-12): источники кадров, маппер, CSV-лог и данные для индикатора и оверлея F9.

Живёт в App, а не в сцене: жесты работают и на экране паузы. Каждый кадр App вызывает poll(),
сервис забирает новый результат из слота источника (в игровом потоке), ставит ему время игры
и прогоняет через маппер. Сработавшую команду App передаёт верхней сцене — как щелчок мыши.
"""

from __future__ import annotations

import csv
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pygame

from reddome.config.camera import CameraSettings
from reddome.input.gestures import (
    FAILED_STATUSES,
    STATUS_TEXT,
    GestureFired,
    GestureFrame,
    GestureMapper,
    GestureSource,
    HoldState,
    SourceStatus,
)
from reddome.input.keyboard import KeyboardGestureSource

if TYPE_CHECKING:
    import numpy

    from reddome.config.balance import GestureSpec

LOG_DIR = Path(__file__).resolve().parents[2] / "ml" / "data"
LOG_COLUMNS = ("time_ms", "gesture", "hand", "score", "command", "source")
LOG_FLUSH_MS = 2000
OVERLAY_KEY = pygame.K_F9


class GestureLog:
    """CSV для тестов точности (неделя 4): смена жеста и сработавшие команды. Только названия и числа."""

    def __init__(self, directory: Path) -> None:
        self.path = directory / f"gesture_log_{datetime.now():%Y%m%d}.csv"
        self._rows: list[tuple[object, ...]] = []
        self._last_flush_ms = 0.0

    def add(self, time_ms: float, gesture: str, hand: str, score: float, command: str, source: str) -> None:
        self._rows.append((round(time_ms), gesture, hand, f"{score:.3f}", command, source))

    def maybe_flush(self, time_ms: float) -> None:
        if self._rows and time_ms - self._last_flush_ms >= LOG_FLUSH_MS:
            self.flush()
            self._last_flush_ms = time_ms

    def flush(self) -> None:
        if not self._rows:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self.path.exists()
        with self.path.open("a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            if new_file:
                writer.writerow(LOG_COLUMNS)
            writer.writerows(self._rows)
        self._rows.clear()


class GestureService:
    def __init__(self, spec: GestureSpec, settings: CameraSettings | None = None,
                 log_dir: Path | None = LOG_DIR) -> None:
        self.settings = settings or CameraSettings.off()
        self.mapper = GestureMapper(spec, swap_hands=self.settings.swap_hands)
        self.camera: GestureSource | None = None
        if self.settings.enabled:
            from reddome.input.camera import MediaPipeGestureSource

            self.camera = MediaPipeGestureSource(self.settings)
        self.keys = KeyboardGestureSource() if self.settings.keys else None
        self.log = GestureLog(log_dir) if log_dir is not None and (self.camera or self.keys) else None
        #: Отладочный оверлей ФТ-14 (F9).
        self.overlay = False
        self.now_ms = 0.0
        #: Руки последнего результата и откуда он пришёл — для оверлея.
        self.frames: list[GestureFrame] = []
        self.source = ""
        self.preview: numpy.ndarray | None = None
        self.last_fired: GestureFired | None = None
        self._last_gesture: dict[str, str] = {}

    def use_source(self, source: GestureSource) -> None:
        """Подменить камеру другим источником (тесты, скриншоты)."""
        if self.camera is not None:
            self.camera.stop()
        self.camera = source
        source.start()

    def start(self) -> None:
        if self.camera is not None:
            self.camera.start()

    def stop(self) -> None:
        if self.camera is not None:
            self.camera.stop()
        if self.log is not None:
            self.log.flush()

    # --- Состояние для экрана ------------------------------------------------------

    @property
    def status(self) -> SourceStatus:
        return self.camera.status if self.camera is not None else "off"

    @property
    def status_text(self) -> str:
        return self.camera.status_text if self.camera is not None else STATUS_TEXT["off"]

    @property
    def unavailable(self) -> bool:
        """Камера не работает (нет камеры, mediapipe, модели или ошибка) — нужно предупреждение НФТ-06."""
        return self.status in FAILED_STATUSES

    @property
    def fps(self) -> float:
        return self.camera.fps if self.camera is not None else 0.0

    @property
    def active(self) -> bool:
        """Есть ли хоть один источник жестов (для индикатора)."""
        return self.camera is not None or self.keys is not None

    def holds(self) -> list[HoldState]:
        return self.mapper.holds(self.now_ms)

    # --- Кадр ------------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> bool:
        """True — событие забрал сервис (F9 или клавиша эмуляции), сцене его не передают."""
        if event.type == pygame.KEYDOWN and event.key == OVERLAY_KEY:
            self.overlay = not self.overlay
            return True
        return self.keys is not None and self.keys.handle_event(event)

    def poll(self, now_ms: float) -> GestureFired | None:
        self.now_ms = now_ms
        result, source = None, ""
        camera_result = self.camera.poll() if self.camera is not None else None
        if camera_result is not None and camera_result.preview is not None:
            self.preview = camera_result.preview
        if self.keys is not None:
            keys_result = self.keys.poll()
            if keys_result is not None:
                result, source = keys_result, "keys"
        if result is None and camera_result is not None and not (self.keys and self.keys.active):
            result, source = camera_result, self.camera.name if self.camera is not None else ""
        fired = None
        if result is not None:
            frames = [replace(frame, time_ms=now_ms) for frame in result.frames]
            self.frames, self.source = frames, source
            self._log_changes(frames, source)
            fired = self.mapper.feed(frames, now_ms)
            if fired is not None:
                self.last_fired = fired
                if self.log is not None:
                    self.log.add(now_ms, fired.gesture, fired.hand, fired.score, fired.command, source)
        if self.log is not None:
            self.log.maybe_flush(now_ms)
        return fired

    def _log_changes(self, frames: list[GestureFrame], source: str) -> None:
        if self.log is None:
            return
        current = {frame.hand: frame for frame in frames}
        for hand in ("left", "right"):
            frame = current.get(hand)
            gesture = frame.gesture if frame is not None else "NoHand"
            if self._last_gesture.get(hand, "NoHand") != gesture:
                self._last_gesture[hand] = gesture
                self.log.add(self.now_ms, gesture, hand, frame.score if frame is not None else 0.0, "", source)
