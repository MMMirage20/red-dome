"""Камера → mediapipe Gesture Recognizer (W3-12, ФТ-13) в отдельном потоке.

Поток ничего не знает об игре: он только кладёт последний результат в общий слот под Lock
(одно значение, очередь не растёт). Игровой поток забирает его через poll() между тиками.
mediapipe и cv2 импортируются лениво внутри потока: без них игра запускается и работает
с мыши и клавиатуры (НФТ-06). Кадры камеры никуда не сохраняются — наружу уходят только
названия жестов, числа и маленькое превью 160 × 120 для оверлея F9.

Руки: по документации mediapipe Left/Right — это руки самого человека для незеркального кадра,
а зеркальный кадр меняет их местами. Поэтому распознаём исходный кадр, а зеркалим только превью.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Any

from reddome.input.gestures import STATUS_TEXT, GestureFrame, Hand, SourceResult, SourceStatus

if TYPE_CHECKING:
    from reddome.config.camera import CameraSettings

FRAME_SIZE = (320, 240)
PREVIEW_SIZE = (160, 120)
#: Столько секунд без кадров (после открытия) — камера считается потерянной.
NO_FRAMES_TIMEOUT_S = 5.0
#: cv2.VideoCapture может повиснуть при открытии (камеру держит другая программа или нет доступа
#: в настройках Windows). Прервать его нельзя, поэтому через это время считаем камеру недоступной.
OPEN_TIMEOUT_S = 10.0
#: Камера не открылась или пропала — через столько секунд пробуем снова, пока игра запущена.
#: На этом ноутбуке камера открывается через раз (её на миг занимает другая программа или она
#: выключена клавишей/шторкой), поэтому жесты должны включаться сами, без перезапуска игры.
RETRY_S = 3.0


class MediaPipeGestureSource:
    name = "camera"

    def __init__(self, settings: CameraSettings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # Общий слот: пишет поток камеры, читает игровой поток.
        self._result: SourceResult | None = None
        self._seq = 0
        self._taken = 0
        self._status: SourceStatus = "starting"
        self._detail = ""
        self._fps = 0.0
        self._started_at = 0.0

    # --- Игровой поток -------------------------------------------------------------

    def start(self) -> None:
        if self._thread is None:
            self._started_at = time.monotonic()
            self._thread = threading.Thread(target=self._run, name="gesture-camera", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def poll(self) -> SourceResult | None:
        with self._lock:
            if self._seq == self._taken:
                return None
            self._taken = self._seq
            return self._result

    @property
    def status(self) -> SourceStatus:
        with self._lock:
            if self._status == "starting" and self._open_timed_out():
                return "no_camera"
            return self._status

    @property
    def status_text(self) -> str:
        with self._lock:
            text = STATUS_TEXT[self._status]
            if self._status == "starting" and self._open_timed_out():
                return f"камера {self.settings.index} не отвечает {OPEN_TIMEOUT_S:.0f} с (занята или нет доступа)"
            if self._status == "no_camera":
                text = f"камера {self.settings.index} не открылась"
            return f"{text}: {self._detail}" if self._detail else text

    @property
    def fps(self) -> float:
        with self._lock:
            return self._fps

    def _open_timed_out(self) -> bool:
        return self._started_at > 0 and time.monotonic() - self._started_at > OPEN_TIMEOUT_S

    # --- Поток камеры ------------------------------------------------------------------

    def _set_status(self, status: SourceStatus, detail: str = "") -> None:
        with self._lock:
            self._status = status
            self._detail = detail

    def _run(self) -> None:
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks.python import vision
            from mediapipe.tasks.python.core.base_options import BaseOptions
        except ImportError as error:
            self._set_status("no_mediapipe", str(error.name or ""))
            return
        if not self.settings.model_path.exists():
            self._set_status("no_model")
            return
        attempt = 0
        while not self._stop.is_set():
            attempt += 1
            capture = self._open_capture(cv2)
            if capture is None:
                self._set_status("no_camera", f"попытка {attempt}, повтор через {RETRY_S:.0f} с")
                self._stop.wait(RETRY_S)
                continue
            recognizer: Any = None
            try:
                options = vision.GestureRecognizerOptions(
                    base_options=BaseOptions(model_asset_path=str(self.settings.model_path)),
                    running_mode=vision.RunningMode.VIDEO,
                    num_hands=2,
                )
                # Новый распознаватель на каждое подключение: метки времени VIDEO начинаются заново.
                recognizer = vision.GestureRecognizer.create_from_options(options)
                self._loop(cv2, mp, capture, recognizer)
            except Exception as error:  # noqa: BLE001 — статус ошибки показывается в оверлее F9
                self._set_status("error", f"{type(error).__name__}: {error}"[:120])
                return
            finally:
                capture.release()
                if recognizer is not None:
                    recognizer.close()
            if not self._stop.is_set():
                self._stop.wait(RETRY_S)

    def _open_capture(self, cv2: Any) -> Any:
        """Камера по номеру: сначала Media Foundation, потом DirectShow, потом выбор OpenCV. None — не открылась."""
        backends = [getattr(cv2, name) for name in ("CAP_MSMF", "CAP_DSHOW") if hasattr(cv2, name)]
        for api in [*backends, cv2.CAP_ANY]:
            if self._stop.is_set():
                return None
            capture = cv2.VideoCapture(self.settings.index, api)
            if capture.isOpened():
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                return capture
            capture.release()
        return None

    def _loop(self, cv2: Any, mp: Any, capture: Any, recognizer: Any) -> None:
        started = time.monotonic()
        last_stamp = -1
        last_frame = started
        last_time = started
        while not self._stop.is_set():
            ok, frame = capture.read()
            if not ok or frame is None:
                if time.monotonic() - last_frame > NO_FRAMES_TIMEOUT_S:
                    self._set_status("no_camera", f"нет кадров {NO_FRAMES_TIMEOUT_S:.0f} с, переподключаюсь")
                    return
                time.sleep(0.02)
                continue
            last_frame = time.monotonic()
            small = cv2.resize(frame, FRAME_SIZE, interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            # Метки времени для режима VIDEO должны строго расти.
            stamp = max(last_stamp + 1, int((time.monotonic() - started) * 1000))
            last_stamp = stamp
            result = recognizer.recognize_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), stamp)
            frames = parse_result(result)
            preview = cv2.resize(rgb, PREVIEW_SIZE, interpolation=cv2.INTER_AREA)
            if self.settings.mirror_preview:
                preview = cv2.flip(preview, 1)
            now = time.monotonic()
            rate = 1 / max(1e-3, now - last_time)
            last_time = now
            with self._lock:
                self._result = SourceResult(frames, preview)
                self._seq += 1
                self._fps = rate if self._fps == 0 else self._fps * 0.9 + rate * 0.1
                self._status = "running"
                self._detail = ""


def parse_result(result: Any) -> list[GestureFrame]:
    """GestureRecognizerResult → по GestureFrame на руку (лучшая категория жеста и руки).

    Время ставит GestureService, когда игровой поток забирает результат.
    """
    frames = []
    for gestures, handedness in zip(result.gestures, result.handedness):
        if not gestures or not handedness:
            continue
        gesture = gestures[0]
        hand: Hand = "left" if (handedness[0].category_name or "").lower() == "left" else "right"
        frames.append(GestureFrame(gesture.category_name or "None", float(gesture.score or 0.0), 0.0, hand))
    return frames
