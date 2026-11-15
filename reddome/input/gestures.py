"""Распознавание жестов (ФТ-13): какой жест какой рукой даёт какую команду.

Логика «жест → команда» отделена от камеры, поэтому её проверяют тесты без mediapipe.
Камера (input/camera.py) и эмуляция клавишами (input/keyboard.py) только поставляют кадры;
команды исполняет сцена в игровом потоке через те же методы, что мышь и клавиатура.

Раскладка: левая рука — экономика и дроны, правая — армия и роверы, «любая» — общие приказы.
«Левая» и «правая» — рука игрока, а не половина кадра.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    import numpy

    from reddome.config.balance import GestureSpec

Hand = Literal["left", "right"]
HANDS: tuple[Hand, ...] = ("left", "right")
#: Время — сумма dt кадров во float; без допуска 500 мс могли бы «не дотянуть» на 1e-13.
TIME_EPSILON_MS = 1e-6

GestureCommand = Literal[
    "select_drone", "select_rovers", "attack_base", "gather", "retreat", "train_drone", "train_rover", "pause",
    "help_build", "train_rocket",
]

#: Категории готовой модели Gesture Recognizer (официальная страница mediapipe, раздел Models).
#: "None" — рука видна, но жест не распознан.
GESTURE_NAMES = ("None", "Closed_Fist", "Open_Palm", "Pointing_Up", "Thumb_Down", "Thumb_Up", "Victory", "ILoveYou")

#: (жест, рука) → команда. Сначала ищется привязка к конкретной руке, потом к "any".
#: Кулак (этап 3): левой — дроны на стройку, правой — ракетный ровер; держать дольше, как атаку,
#: потому что кулак — частая «нерабочая» поза руки.
GESTURE_BINDINGS: dict[tuple[str, str], GestureCommand] = {
    ("Open_Palm", "left"): "select_drone",
    ("Open_Palm", "right"): "select_rovers",
    ("Pointing_Up", "any"): "attack_base",
    ("Thumb_Up", "any"): "gather",
    ("Thumb_Down", "any"): "retreat",
    ("Victory", "left"): "train_drone",
    ("Victory", "right"): "train_rover",
    ("ILoveYou", "any"): "pause",
    ("Closed_Fist", "left"): "help_build",
    ("Closed_Fist", "right"): "train_rocket",
}
#: Команды, которые держат attack_hold_ms, а не hold_ms.
LONG_HOLD: tuple[GestureCommand, ...] = ("attack_base", "help_build", "train_rocket")

#: Подписи для индикатора, подсказок и памятки.
GESTURE_TITLES = {
    "Open_Palm": "ладонь",
    "Pointing_Up": "указательный вверх",
    "Thumb_Up": "большой вверх",
    "Thumb_Down": "большой вниз",
    "Victory": "V",
    "ILoveYou": "ILY",
    "Closed_Fist": "кулак",
    "None": "не распознан",
}
HAND_TITLES: dict[str, str] = {"left": "левая", "right": "правая"}
COMMAND_TITLES: dict[str, str] = {
    "select_drone": "выбрать дрона",
    "select_rovers": "выбрать роверов",
    "attack_base": "атака на базу ВЕКТОРа",
    "gather": "за работу",
    "retreat": "отступить",
    "train_drone": "собрать дрона",
    "train_rover": "собрать ровера",
    "pause": "пауза",
    "help_build": "дроны на стройку",
    "train_rocket": "собрать ракетный ровер",
}


def binding(gesture: str, hand: Hand) -> GestureCommand | None:
    return GESTURE_BINDINGS.get((gesture, hand)) or GESTURE_BINDINGS.get((gesture, "any"))


@dataclass(frozen=True)
class GestureFrame:
    """Одна рука в одном кадре. Кадр камеры даёт до двух GestureFrame с одним time_ms."""

    gesture: str
    score: float
    time_ms: float
    hand: Hand = "right"


@dataclass(frozen=True)
class GestureFired:
    """Сработавшая команда: кто, чем и с какой уверенностью."""

    command: GestureCommand
    hand: Hand
    gesture: str
    score: float
    time_ms: float


@dataclass(frozen=True)
class HoldState:
    """Что сейчас держит рука — для индикатора: жест, будущая команда и доля удержания 0…1."""

    hand: Hand
    gesture: str
    command: GestureCommand
    progress: float
    fired: bool


@dataclass
class _HandState:
    gesture: str | None = None
    since_ms: float = 0.0
    fired: bool = False
    score: float = 0.0
    last_ms: float = 0.0


class GestureMapper:
    """Превращает кадры распознавания в команды игры.

    Правила для каждой руки отдельно:
    - кадр считается при уверенности ≥ min_score, иначе удержание этой руки сбрасывается;
    - команда срабатывает, когда жест держат ≥ порога команды (атака и кулаки — attack_hold_ms,
      пауза — pause_hold_ms, остальное — hold_ms);
    - одно удержание — одна команда, повтор — после смены жеста или опускания руки;
    - рука пропала из кадра — её удержание сброшено.
    Общие правила:
    - после любой команды cooldown_ms ничего не срабатывает; удержание, дошедшее до порога
      в это время, сгорает — жест нужно показать заново;
    - если в одном кадре дошли до порога обе руки, побеждает большая уверенность.
    swap_hands меняет левую и правую руку на входе — если на конкретной камере они перепутаны.
    """

    def __init__(self, settings: GestureSpec, swap_hands: bool = False) -> None:
        self.settings = settings
        self.swap_hands = swap_hands
        self._hands: dict[Hand, _HandState] = {hand: _HandState() for hand in HANDS}
        self._cooldown_until = -1.0

    def hold_ms(self, command: GestureCommand) -> int:
        if command in LONG_HOLD:
            return self.settings.attack_hold_ms
        if command == "pause":
            return self.settings.pause_hold_ms
        return self.settings.hold_ms

    def _hand_of(self, frame: GestureFrame) -> Hand:
        if not self.swap_hands:
            return frame.hand
        return "right" if frame.hand == "left" else "left"

    def feed(self, frames: list[GestureFrame], time_ms: float) -> GestureFired | None:
        """Кадры одного момента (0–2 руки). Руки, которых нет в списке, считаются опущенными."""
        seen: dict[Hand, GestureFrame] = {}
        for frame in frames:
            hand = self._hand_of(frame)
            if hand not in seen or frame.score > seen[hand].score:
                seen[hand] = frame
        ready: list[tuple[float, Hand, GestureCommand, GestureFrame]] = []
        for hand in HANDS:
            state = self._hands[hand]
            frame = seen.get(hand)
            command = binding(frame.gesture, hand) if frame is not None else None
            if frame is None or command is None or frame.score < self.settings.min_score:
                self._hands[hand] = _HandState()
                continue
            if frame.gesture != state.gesture:
                state.gesture = frame.gesture
                state.since_ms = time_ms
                state.fired = False
            state.score = frame.score
            state.last_ms = time_ms
            if not state.fired and time_ms - state.since_ms + TIME_EPSILON_MS >= self.hold_ms(command):
                state.fired = True  # удержание израсходовано, даже если команда не пройдёт
                ready.append((frame.score, hand, command, frame))
        if not ready or time_ms < self._cooldown_until:
            return None
        score, hand, command, frame = max(ready, key=lambda r: r[0])
        self._cooldown_until = time_ms + self.settings.cooldown_ms
        return GestureFired(command, hand, frame.gesture, score, time_ms)

    def holds(self, time_ms: float) -> list[HoldState]:
        """Текущие удержания по рукам — для индикатора над портретом."""
        result = []
        for hand in HANDS:
            state = self._hands[hand]
            if state.gesture is None:
                continue
            command = binding(state.gesture, hand)
            if command is None:
                continue
            progress = min(1.0, (time_ms - state.since_ms) / max(1, self.hold_ms(command)))
            result.append(HoldState(hand, state.gesture, command, progress, state.fired))
        return result

    def reset(self) -> None:
        self._hands = {hand: _HandState() for hand in HANDS}
        self._cooldown_until = -1.0


# --- Источники кадров ------------------------------------------------------------

SourceStatus = Literal["off", "starting", "running", "no_camera", "no_mediapipe", "no_model", "error"]
#: Статусы, при которых жесты с камеры не работают.
FAILED_STATUSES: tuple[SourceStatus, ...] = ("no_camera", "no_mediapipe", "no_model", "error")
STATUS_TEXT: dict[str, str] = {
    "off": "жесты выключены флагом --no-gestures",
    "starting": "камера запускается…",
    "running": "камера работает",
    "no_camera": "камера не открылась",
    "no_mediapipe": "не установлен mediapipe или OpenCV (requirements-ai.txt)",
    "no_model": "нет модели жестов (models/gesture_recognizer.task), скачать не удалось",
    "error": "ошибка распознавания",
}


@dataclass(frozen=True)
class SourceResult:
    """Последний результат источника: руки в кадре и уменьшенное превью (numpy RGB 160×120) для оверлея."""

    frames: list[GestureFrame]
    preview: numpy.ndarray | None = None


class GestureSource(Protocol):
    """Источник жестов. Камера работает в своём потоке и кладёт результат в общий слот;
    игровой поток забирает его через poll(). poll() возвращает None, если нового результата нет.
    """

    name: str

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def poll(self) -> SourceResult | None: ...

    @property
    def status(self) -> SourceStatus: ...

    @property
    def status_text(self) -> str: ...

    @property
    def fps(self) -> float: ...
