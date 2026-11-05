"""Магазин-заглушка (ФТ-15): предложения видны, покупка пока недоступна.

Демо-оплата и права доступа в SQLite — неделя 5 (ЛР13).
"""

from __future__ import annotations

from typing import Any

import pygame

from reddome.render.backdrop import starfield
from reddome.scenes.base import Scene
from reddome.ui import theme
from reddome.ui.icons import icon
from reddome.ui.widgets import Button, card

OFFERS = (
    ("Полная экспедиция", "Миссии 2–3 и режим «Схватка»", "1 490 ₸", "dome"),
    ("Скины купола и роверов", "Косметика без игрового преимущества", "290–590 ₸", "guard_rover"),
)


class ShopScene(Scene):
    def enter(self, **data: Any) -> None:
        self.sky = starfield(theme.SCREEN_SIZE, seed=11)
        self.back = Button((theme.SCREEN_SIZE[0] // 2, 600), "Назад в меню", lambda: self.app.start("menu"))

    def handle_event(self, event: pygame.event.Event) -> None:
        self.back.handle_event(event)

    def draw(self, surface: pygame.Surface) -> None:
        surface.blit(self.sky, (0, 0))
        cx = theme.SCREEN_SIZE[0] // 2
        theme.draw_text(surface, "Магазин", (cx, 100), 52, theme.SAND, anchor="center", kind="title", shadow=True)
        for i, (title, description, price, picture) in enumerate(OFFERS):
            rect = pygame.Rect(0, 0, 400, 340)
            rect.center = (cx - 220 + 440 * i, 350)
            surface.blit(card(rect.size), rect)
            surface.blit(icon(picture, 96), (rect.centerx - 48, rect.y + 28))
            theme.draw_text(surface, title, (rect.centerx, rect.y + 160), 26, theme.TEXT, anchor="center", kind="title")
            theme.draw_text(surface, description, (rect.centerx, rect.y + 198), 17, theme.TEXT_QUIET, anchor="center")
            theme.draw_text(surface, price, (rect.centerx, rect.y + 248), 32, theme.SAND, anchor="center", kind="title")
            badge = pygame.Rect(0, 0, 110, 30)
            badge.center = (rect.centerx, rect.bottom - 36)
            pygame.draw.rect(surface, theme.PANEL_LIGHT, badge, border_radius=15)
            pygame.draw.rect(surface, theme.ACCENT, badge, 1, border_radius=15)
            theme.draw_text(surface, "Скоро", badge.center, 16, theme.ACCENT, anchor="center", kind="title")
        self.back.draw(surface)
