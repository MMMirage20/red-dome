"""Базовый класс экрана игры."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pygame

if TYPE_CHECKING:
    from reddome.app import App
    from reddome.input.gestures import GestureFired
    from reddome.ui.widgets import Button

#: Подсказка внизу меню, когда жесты включены.
MENU_GESTURE_HINT = "Жесты: ладонь левой / правой — выбор кнопки · большой палец вверх — нажать · вниз — назад"


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
        """Сработавший жест (W3-12). App вызывает у верхней сцены.

        По умолчанию — управление меню без мыши (этап 3): ладонь правой — следующая кнопка, левой — предыдущая,
        большой палец вверх (или указательный вверх) — нажать выбранную, большой палец вниз — назад.
        Сцена с кнопками отдаёт их в menu_buttons() и шаг «назад» в menu_back().
        """
        buttons = [b for b in self.menu_buttons() if b.enabled]
        if not buttons:
            return
        current = next((i for i, b in enumerate(buttons) if b.focused), None)
        if fired.gesture == "Open_Palm":
            step = 1 if fired.hand == "right" else -1
            self.focus_button(buttons, 0 if current is None else (current + step) % len(buttons))
        elif fired.gesture in ("Thumb_Up", "Pointing_Up"):
            if current is None:
                self.focus_button(buttons, 0)
            else:
                buttons[current].on_click()
        elif fired.gesture == "Thumb_Down":
            self.menu_back()

    def focus_button(self, buttons: list[Button], index: int) -> None:
        for b in self.menu_buttons():
            b.focused = False
        buttons[index].focused = True

    def menu_buttons(self) -> list[Button]:
        """Кнопки, по которым ходит жест; пусто — сцена жестами-меню не управляется."""
        return []

    def menu_back(self) -> None:
        """Что делает «назад» (большой палец вниз)."""

    def draw(self, surface: pygame.Surface) -> None:
        pass
