"""Пауза поверх игры (ФТ-16): размытый кадр игры, карточка с кнопками и памятка по управлению.

Памятка на двух вкладках — «Клавиши» и «Жесты» (Tab или щелчок), чтобы карточка не переполнялась.
Жест ILY закрывает паузу так же, как открыл. Игровая сцена лежит в стеке ниже и не обновляется.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pygame

from reddome.input.gestures import COMMAND_TITLES, GESTURE_BINDINGS, GESTURE_TITLES, HAND_TITLES
from reddome.input.keyboard import KEYS
from reddome.scenes.base import Scene
from reddome.ui import theme
from reddome.ui.commands import difficulty_line
from reddome.ui.icons import GESTURE_ICONS, icon
from reddome.ui.widgets import Button, card

if TYPE_CHECKING:
    from reddome.input.gestures import GestureFired

CONTROLS = (
    ("ЛКМ, рамка", "выделить; Shift — добавить"),
    ("Двойной щелчок", "все такие же на экране"),
    ("ПКМ", "добывать, атаковать, строить, идти"),
    ("Ctrl+цифра / цифра", "назначить / выбрать группу"),
    (".", "свободный дрон"),
    ("WASD, стрелки", "камера"),
    ("G · R · E · B · X", "добывать · вернуть · чинить · строить · стоп"),
    ("F", "атака (роверы)"),
    ("Q · T", "собрать юнита · точка сбора"),
    ("B, затем P · I · O · E · H", "панель, бур, генератор, переработчик, ангар"),
)
TABS = ("Клавиши", "Жесты")
HAND_ANY = "любая"


def gesture_rows() -> list[tuple[str, str, str, str]]:
    """(жест, рука, команда, клавиша эмуляции) в порядке таблицы ФТ-13."""
    keys = {(gesture, hand): label for _, gesture, hand, label in KEYS}
    rows = []
    for (gesture, hand), command in GESTURE_BINDINGS.items():
        key = keys.get((gesture, hand)) or keys.get((gesture, "right")) or ""
        rows.append((gesture, HAND_TITLES.get(hand, HAND_ANY), COMMAND_TITLES[command], key))
    return rows


class PauseScene(Scene):
    opaque = True

    def enter(self, background: pygame.Surface | None = None, difficulty: str | None = None, **data: Any) -> None:
        self.background = background
        self.difficulty_text = difficulty_line(difficulty or self.app.difficulty)
        w, h = theme.SCREEN_SIZE
        self.card_rect = pygame.Rect(0, 0, 860, 470)
        self.card_rect.center = (w // 2, h // 2)
        bx = self.card_rect.x + 190
        self.buttons = [
            Button((bx, self.card_rect.y + 170), "Продолжить", self.app.pop, width=300),
            Button((bx, self.card_rect.y + 240), "Настройки (скоро)", lambda: None, width=300, enabled=False),
            Button((bx, self.card_rect.y + 310), "Выйти в меню", lambda: self.app.start("menu"), width=300),
        ]
        self.tab = 0
        x = self.card_rect.x + 380
        self.tab_rects = [pygame.Rect(x + i * 130, self.card_rect.y + 26, 122, 34) for i in range(len(TABS))]

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.pop()
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
            self.tab = (self.tab + 1) % len(TABS)
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, rect in enumerate(self.tab_rects):
                if rect.collidepoint(event.pos):
                    self.tab = i
                    return
        for button in self.buttons:
            button.handle_event(event)

    def on_gesture(self, fired: GestureFired) -> None:
        if fired.command == "pause":
            self.app.pop()

    def draw(self, surface: pygame.Surface) -> None:
        if self.background is not None:
            surface.blit(self.background, (0, 0))
        r = self.card_rect
        surface.blit(card(r.size), r)
        theme.draw_text(surface, "Пауза", (r.x + 190, r.y + 70), 48, theme.SAND, anchor="center", kind="title", shadow=True)
        theme.draw_text(surface, self.difficulty_text, (r.x + 190, r.y + 112), 16, theme.TEXT_QUIET, anchor="center")
        for button in self.buttons:
            button.draw(surface)
        x = r.x + 380
        pygame.draw.line(surface, theme.PANEL_EDGE, (x - 20, r.y + 30), (x - 20, r.bottom - 30))
        for i, (rect, title) in enumerate(zip(self.tab_rects, TABS)):
            active = i == self.tab
            pygame.draw.rect(surface, theme.PANEL_LIGHT if active else theme.PANEL, rect, border_radius=8)
            pygame.draw.rect(surface, theme.ACCENT if active else theme.PANEL_EDGE, rect, 1, border_radius=8)
            theme.draw_text(surface, title, rect.center, 17, theme.TEXT if active else theme.TEXT_QUIET, "center", kind="title")
        theme.draw_text(surface, "Tab — переключить", (r.right - 30, r.y + 43), 13, theme.TEXT_QUIET, anchor="midright")
        if self.tab == 0:
            self._draw_keys(surface, x, r.y + 78)
        else:
            self._draw_gestures(surface, x, r.y + 76)

    @staticmethod
    def _draw_keys(surface: pygame.Surface, x: int, top: int) -> None:
        for i, (keys, what) in enumerate(CONTROLS):
            y = top + i * 36
            theme.draw_text(surface, keys, (x, y), 16, theme.WARNING, kind="title")
            theme.draw_text(surface, what, (x + 4, y + 17), 14, theme.TEXT_QUIET)

    def _draw_gestures(self, surface: pygame.Surface, x: int, top: int) -> None:
        keys_on = self.app.gestures.keys is not None
        for i, (gesture, hand, command, key) in enumerate(gesture_rows()):
            y = top + i * 40
            surface.blit(icon(GESTURE_ICONS[gesture], 34), (x, y))
            theme.draw_text(surface, f"{GESTURE_TITLES[gesture][:1].upper()}{GESTURE_TITLES[gesture][1:]}, {hand}", (x + 44, y + 1), 15, theme.WARNING,
                            kind="title")
            theme.draw_text(surface, command, (x + 44, y + 19), 14, theme.TEXT_QUIET)
            if keys_on and key:
                theme.draw_text(surface, key, (self.card_rect.right - 30, y + 10), 14, theme.TEXT_QUIET, anchor="topright",
                                kind="title")
        y = top + 8 * 40
        surface.blit(icon(GESTURE_ICONS["Closed_Fist"], 26), (x + 4, y))
        hint = "Кулак не занят. Левая рука — экономика, правая — армия."
        theme.draw_text(surface, hint, (x + 44, y + 5), 14, theme.TEXT_QUIET)
        status = self.app.gestures.status_text if self.app.gestures.unavailable else ""
        if status:
            theme.draw_text(surface, f"Камера: {status}", (x, y + 32), 13, theme.WARNING)
