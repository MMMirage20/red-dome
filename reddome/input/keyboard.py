"""Эмуляция жестов клавишами F1–F8 (W3-12): для тестов, отладки и на случай, если на защите
не заработает камера. Пока клавиша зажата, каждый кадр игры приходит «рука с этим жестом»
с уверенностью 1.0, поэтому удержание проверяется так же, как с камерой.
"""

from __future__ import annotations

import pygame

from reddome.input.gestures import GestureFrame, Hand, SourceResult, SourceStatus

#: Клавиша → (жест, рука, подпись). Для жестов «любой рукой» взята правая.
KEYS: tuple[tuple[int, str, Hand, str], ...] = (
    (pygame.K_F1, "Open_Palm", "left", "F1"),
    (pygame.K_F2, "Open_Palm", "right", "F2"),
    (pygame.K_F3, "Pointing_Up", "right", "F3"),
    (pygame.K_F4, "Thumb_Up", "right", "F4"),
    (pygame.K_F5, "Thumb_Down", "right", "F5"),
    (pygame.K_F6, "Victory", "left", "F6"),
    (pygame.K_F7, "Victory", "right", "F7"),
    (pygame.K_F8, "ILoveYou", "right", "F8"),
)
KEY_GESTURES: dict[int, tuple[str, Hand]] = {key: (gesture, hand) for key, gesture, hand, _ in KEYS}


class KeyboardGestureSource:
    """Зажатые клавиши отслеживаются по KEYDOWN/KEYUP, поэтому источник работает и без окна (в тестах)."""

    name = "keys"

    def __init__(self) -> None:
        self._held: list[int] = []
        self._released = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        """True, если событие — клавиша эмуляции (тогда сцене его не передают)."""
        if event.type not in (pygame.KEYDOWN, pygame.KEYUP) or event.key not in KEY_GESTURES:
            return False
        if event.type == pygame.KEYDOWN and event.key not in self._held:
            self._held.append(event.key)
        elif event.type == pygame.KEYUP and event.key in self._held:
            self._held.remove(event.key)
            self._released = True
        return True

    @property
    def active(self) -> bool:
        return bool(self._held)

    def start(self) -> None:
        pass

    def stop(self) -> None:
        self._held.clear()

    def poll(self) -> SourceResult | None:
        """Кадр с зажатыми жестами; после отпускания — один пустой кадр («рука опущена»)."""
        if self._held:
            self._released = False
            # Последняя нажатая клавиша для каждой руки — как одна рука в кадре.
            by_hand: dict[Hand, str] = {}
            for key in self._held:
                gesture, hand = KEY_GESTURES[key]
                by_hand[hand] = gesture
            return SourceResult([GestureFrame(gesture, 1.0, 0.0, hand) for hand, gesture in by_hand.items()])
        if self._released:
            self._released = False
            return SourceResult([])
        return None

    @property
    def status(self) -> SourceStatus:
        return "running"

    @property
    def status_text(self) -> str:
        return "эмуляция клавишами F1–F8"

    @property
    def fps(self) -> float:
        return 0.0
