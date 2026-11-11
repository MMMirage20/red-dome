"""Выбор миссии (ФТ-02, W3-01): миссия 1 открыта, миссии 2–3 показаны с замком и ведут в магазин (ФТ-15).

Переключатель сложности (этап 2) переехал сюда из главного меню: щелчок по нему или стрелки ← →.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pygame

from reddome.render.backdrop import starfield
from reddome.scenes.base import Scene
from reddome.sim.types import DIFFICULTIES
from reddome.ui import theme
from reddome.ui.commands import DIFFICULTY_NAMES
from reddome.ui.icons import icon
from reddome.ui.widgets import Button, card


@dataclass(frozen=True)
class Mission:
    number: int
    title: str
    goal: str
    picture: str
    #: Открыта бесплатно; закрытые миссии входят в «Полную экспедицию» в магазине.
    unlocked: bool


#: Кампания из устава (docs/charter.md, раздел 5). В MVP играется только «Высадка».
MISSIONS: tuple[Mission, ...] = (
    Mission(1, "Высадка", "Построить базу и отбить налёт ВЕКТОРа", "dome", True),
    Mission(2, "Война за лёд", "Удержать 2 из 3 ледяных полей 5 солов", "ice_drill", False),
    Mission(3, "Последний купол", "Разрушить купол ВЕКТОРа первым", "hangar", False),
)

CARD_SIZE = (340, 420)
CARD_GAP = 30


def difficulty_label(difficulty: str) -> str:
    return f"Сложность: ‹ {DIFFICULTY_NAMES[difficulty]} ›"


class MissionsScene(Scene):
    def enter(self, **data: Any) -> None:
        self.sky = starfield(theme.SCREEN_SIZE, seed=7)
        w, _ = theme.SCREEN_SIZE
        total = len(MISSIONS) * CARD_SIZE[0] + (len(MISSIONS) - 1) * CARD_GAP
        left = (w - total) // 2
        self.cards: list[tuple[Mission, pygame.Rect]] = []
        self.buttons: list[Button] = []
        self.lock_buttons: dict[int, Button] = {}
        for i, mission in enumerate(MISSIONS):
            rect = pygame.Rect(left + i * (CARD_SIZE[0] + CARD_GAP), 150, *CARD_SIZE)
            self.cards.append((mission, rect))
            if mission.unlocked:
                self.difficulty_button = Button((rect.centerx, rect.bottom - 122), difficulty_label(self.app.difficulty),
                                                self.change_difficulty, width=280, height=44)
                self.play_button = Button((rect.centerx, rect.bottom - 56), "Начать", self.play, width=280)
                self.buttons += [self.difficulty_button, self.play_button]
            else:
                button = Button((rect.centerx, rect.bottom - 56), "В магазин", self.open_shop, width=280)
                self.lock_buttons[mission.number] = button
                self.buttons.append(button)
        self.buttons.append(Button((w // 2, 640), "Назад в меню", lambda: self.app.start("menu"), width=260))

    def play(self) -> None:
        self.app.start("game")

    def open_shop(self) -> None:
        self.app.start("shop", back="missions")

    def change_difficulty(self, step: int = 1) -> None:
        """Следующий (step=1) или предыдущий (step=-1) уровень по кругу: Лёгкий → Обычный → Сложный."""
        index = DIFFICULTIES.index(self.app.difficulty)
        self.app.difficulty = DIFFICULTIES[(index + step) % len(DIFFICULTIES)]
        self.difficulty_button.label = difficulty_label(self.app.difficulty)

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                self.change_difficulty(1 if event.key == pygame.K_RIGHT else -1)
                return
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.play()
                return
            if event.key == pygame.K_ESCAPE:
                self.app.start("menu")
                return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            # Щелчок по самой закрытой карточке (не только по кнопке) тоже ведёт в магазин.
            for mission, rect in self.cards:
                button = self.lock_buttons.get(mission.number)
                if button is not None and rect.collidepoint(event.pos) and not button.rect.collidepoint(event.pos):
                    self.open_shop()
                    return
        for button in self.buttons:
            button.handle_event(event)

    def draw(self, surface: pygame.Surface) -> None:
        surface.blit(self.sky, (0, 0))
        cx = theme.SCREEN_SIZE[0] // 2
        theme.draw_text(surface, "Выбор миссии", (cx, 80), 48, theme.SAND, anchor="center", kind="title", shadow=True)
        for mission, rect in self.cards:
            surface.blit(card(rect.size), rect)
            picture = icon(mission.picture, 110)
            if not mission.unlocked:
                picture = picture.copy()
                picture.fill((90, 90, 90), special_flags=pygame.BLEND_MULT)
            surface.blit(picture, picture.get_rect(center=(rect.centerx, rect.y + 90)))
            if not mission.unlocked:
                surface.blit(icon("lock", 56), (rect.centerx + 22, rect.y + 104))
            color = theme.TEXT if mission.unlocked else theme.TEXT_QUIET
            theme.draw_text(surface, f"Миссия {mission.number}", (rect.centerx, rect.y + 168), 17, theme.TEXT_QUIET,
                            anchor="center")
            theme.draw_text(surface, f"«{mission.title}»", (rect.centerx, rect.y + 198), 28, color, anchor="center",
                            kind="title")
            theme.draw_text(surface, mission.goal, (rect.centerx, rect.y + 236), 15, theme.TEXT_QUIET, anchor="center")
            if not mission.unlocked:
                theme.draw_text(surface, "Входит в «Полную экспедицию»", (rect.centerx, rect.bottom - 120), 16,
                                theme.ACCENT, anchor="center")
        for button in self.buttons:
            button.draw(surface)
