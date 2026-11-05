"""Базовый класс экрана игры."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pygame

if TYPE_CHECKING:
    from reddome.app import App
    from reddome.input.gestures import GestureFired


class Scene:
    """App каждый кадр вызывает у верхней сцены handle_event → update, а рисует все сцены стека.

    opaque = True — сцена закрывает экран целиком (свой фон), и сцены под ней не рисуются.
    """

    opaque = False

    def __init__(self, app: App) -> None:
        self.app = app

    def enter(self, **data: Any) -> None:
        """Вызывается при запуске сцены с данными из App.start / App.push."""

    def handle_event(self, event: pygame.event.Event) -> None:
        pass

    def update(self, dt_ms: float) -> None:
        pass

    def on_gesture(self, fired: GestureFired) -> None:
        """Сработавший жест (W3-12). App вызывает у верхней сцены; по умолчанию жесты не обрабатываются."""

    def draw(self, surface: pygame.Surface) -> None:
        pass
