"""Главное меню (ФТ-02, B5): панорама кратера с куполом на закате, летающие дроны и пыль.

«Играть» открывает выбор миссии (W3-01): там миссия 1, замки на 2–3 и переключатель сложности.
"""

from __future__ import annotations

import math
from typing import Any

import pygame

from reddome.render.backdrop import drone_frame, panorama, showcase_drone_path
from reddome.render.lighting import Lighting
from reddome.scenes.base import Scene
from reddome.ui import theme
from reddome.ui.widgets import Button, card

#: Панорама рисуется один раз на seed и живёт до выхода из игры.
_panoramas: dict[int, pygame.Surface] = {}
DRONE_TRIP_MS = 7000


class MenuScene(Scene):
    def enter(self, **data: Any) -> None:
        seed = self.app.seed
        if seed not in _panoramas:
            _panoramas[seed] = panorama(self.app.terrain_for(seed), self.app.sprites, seed)
        self.background = _panoramas[seed]
        self.lighting = Lighting(theme.SCREEN_SIZE, seed + 1)
        self.time_ms = 0.0
        self.path = showcase_drone_path()
        cx = theme.SCREEN_SIZE[0] - 250
        self.card_rect = pygame.Rect(0, 0, 380, 450)
        self.card_rect.center = (cx, 440)
        self.buttons = [
            Button((cx, 360), "Играть", lambda: self.app.start("missions")),
            Button((cx, 440), "Магазин", lambda: self.app.start("shop")),
            Button((cx, 520), "Настройки (скоро)", lambda: None, enabled=False),
            Button((cx, 600), "Выход", self.app.quit),
        ]

    def menu_buttons(self) -> list:
        return self.buttons

    def handle_event(self, event: pygame.event.Event) -> None:
        for button in self.buttons:
            button.handle_event(event)

    def update(self, dt_ms: float) -> None:
        self.time_ms += dt_ms
        self.lighting.update_dust(dt_ms)

    def draw(self, surface: pygame.Surface) -> None:
        surface.blit(self.background, (0, 0))
        (x0, y0), (x1, y1) = self.path
        for i in range(2):
            t = (self.time_ms / DRONE_TRIP_MS + i * 0.5) % 1.0
            outbound = t < 0.5
            k = (1 - math.cos(t * 2 * math.pi)) / 2  # туда и обратно с плавным разгоном
            x, y = x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
            angle = math.atan2(y1 - y0, x1 - x0) + (0 if outbound else math.pi)
            sprite = drone_frame(self.app.sprites, angle, carrying=not outbound)
            bob = math.sin(self.time_ms / 260 + i) * 1.5
            surface.blit(sprite, sprite.get_rect(center=(x + i * 14, y - 8 + bob)))
        self.lighting.draw_dust(surface)
        surface.blit(card(self.card_rect.size), self.card_rect)
        theme.draw_text(surface, "КРАСНЫЙ КУПОЛ", (self.card_rect.centerx, self.card_rect.y + 34), 40, theme.SAND,
                        anchor="center", kind="title", shadow=True)
        theme.draw_text(surface, "Колония людей против ИИ «ВЕКТОР»", (self.card_rect.centerx, self.card_rect.y + 72),
                        17, theme.TEXT_QUIET, anchor="center")
        for button in self.buttons:
            button.draw(surface)
        theme.draw_text(surface, "Шрифты Russo One и Exo 2 — SIL OFL 1.1", (14, theme.SCREEN_SIZE[1] - 10), 13,
                        theme.dim(theme.TEXT, 0.7), anchor="bottomleft")
