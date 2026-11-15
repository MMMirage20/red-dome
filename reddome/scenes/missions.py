"""Выбор миссии (ФТ-02, W3-01; этап 3 — ФТ-33): кампания из трёх миссий.

Миссия 1 бесплатна. Миссии 2–3 входят в «Полную экспедицию»: пока она не куплена (профиль игрока,
reddome/profile.py), карточка серая с замком и ведёт в магазин; после демо-покупки — играется.
Сложность общая для всех миссий: кнопка под карточками или стрелки ← →. Enter — начать миссию 1
(или последнюю сыгранную, если она открыта).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pygame

from reddome.bot.factory import BOT_TITLES
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
    #: Бесплатна; остальные входят в «Полную экспедицию» (магазин).
    free: bool
    #: Что нового в миссии — строка на карточке.
    novelty: str


#: Кампания из устава (docs/charter.md, раздел 5). Числа целей — в balance.json → missions.
MISSIONS: tuple[Mission, ...] = (
    Mission(1, "Высадка", "Построить базу и разрушить купол ВЕКТОРа", "dome", True, "Пылевой вихрь"),
    Mission(2, "Война за лёд", "Удержать {fields} из 3 ледяных полей {sols} солов подряд", "ice_drill", False,
            "Турель, реактор, ракетный ровер · буря"),
    Mission(3, "Последний купол", "Разрушить купол ВЕКТОРа или первым построить Большой купол", "great_dome", False,
            "Большой купол · метеориты · вспышки"),
)

CARD_SIZE = (360, 420)
CARD_GAP = 26


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
        self.play_buttons: dict[int, Button] = {}
        self.lock_buttons: dict[int, Button] = {}
        for i, mission in enumerate(MISSIONS):
            rect = pygame.Rect(left + i * (CARD_SIZE[0] + CARD_GAP), 132, *CARD_SIZE)
            self.cards.append((mission, rect))
            if self.unlocked(mission.number):
                button = Button((rect.centerx, rect.bottom - 52), "Начать",
                                lambda n=mission.number: self.play(n), width=280)
                self.play_buttons[mission.number] = button
            else:
                button = Button((rect.centerx, rect.bottom - 52), "В магазин", self.open_shop, width=280)
                self.lock_buttons[mission.number] = button
            self.buttons.append(button)
        #: Кнопка миссии 1 — для Enter и тестов.
        self.play_button = self.play_buttons[1]
        self.difficulty_button = Button((w // 2, 600), difficulty_label(self.app.difficulty), self.change_difficulty,
                                        width=320, height=44)
        self.buttons.append(self.difficulty_button)
        self.buttons.append(Button((w // 2, 668), "Назад в меню", lambda: self.app.start("menu"), width=260))

    def goal_text(self, mission: Mission) -> str:
        """Цель на карточке: числа (сколько полей и солов) — из balance.json → missions."""
        spec = self.app.balance.mission(mission.number)
        return mission.goal.format(fields=spec.hold_fields, sols=spec.hold_sols_for("player"))

    def unlocked(self, number: int) -> bool:
        profile = getattr(self.app, "profile", None)
        free = next(m.free for m in MISSIONS if m.number == number)
        return free or (profile is not None and profile.mission_unlocked(number))

    def menu_buttons(self) -> list[Button]:
        return self.buttons

    def menu_back(self) -> None:
        self.app.start("menu")

    def play(self, number: int = 1) -> None:
        self.app.mission = number
        self.app.start("game", mission=number)

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
                self.play(self.app.mission if self.unlocked(self.app.mission) else 1)
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
        theme.draw_text(surface, "Выбор миссии", (cx, 70), 48, theme.SAND, anchor="center", kind="title", shadow=True)
        profile = getattr(self.app, "profile", None)
        for mission, rect in self.cards:
            unlocked = self.unlocked(mission.number)
            surface.blit(card(rect.size), rect)
            picture = icon(mission.picture, 104)
            if not unlocked:
                picture = picture.copy()
                picture.fill((90, 90, 90), special_flags=pygame.BLEND_MULT)
            surface.blit(picture, picture.get_rect(center=(rect.centerx, rect.y + 80)))
            if not unlocked:
                surface.blit(icon("lock", 56), (rect.centerx + 22, rect.y + 92))
            color = theme.TEXT if unlocked else theme.TEXT_QUIET
            theme.draw_text(surface, f"Миссия {mission.number}", (rect.centerx, rect.y + 152), 17, theme.TEXT_QUIET,
                            anchor="center")
            theme.draw_text(surface, f"«{mission.title}»", (rect.centerx, rect.y + 182), 28, color, anchor="center",
                            kind="title")
            self._wrap(surface, self.goal_text(mission), rect.centerx, rect.y + 218, rect.width - 40, 15, theme.TEXT_QUIET)
            bot = self.app.balance.mission(mission.number).bot
            theme.draw_text(surface, f"ВЕКТОР: «{BOT_TITLES[bot]}»", (rect.centerx, rect.y + 268), 15, theme.ACCENT,
                            anchor="center")
            theme.draw_text(surface, mission.novelty, (rect.centerx, rect.y + 292), 14, theme.TEXT_QUIET, anchor="center")
            if not unlocked:
                theme.draw_text(surface, "Входит в «Полную экспедицию»", (rect.centerx, rect.bottom - 100), 16,
                                theme.ACCENT, anchor="center")
            elif profile is not None and profile.best_score(mission.number) is not None:
                best = f"{profile.best_score(mission.number):,}".replace(",", " ")
                theme.draw_text(surface, f"Лучший счёт: {best} · побед: {profile.wins(mission.number)}",
                                (rect.centerx, rect.bottom - 100), 15, theme.SUCCESS, anchor="center")
        for button in self.buttons:
            button.draw(surface)

    @staticmethod
    def _wrap(surface: pygame.Surface, text: str, cx: int, y: int, width: int, size: int, color: theme.Color) -> None:
        """Текст по центру в несколько строк по ширине карточки."""
        words, line = text.split(), ""
        lines = []
        for word in words:
            probe = f"{line} {word}".strip()
            if theme.font(size).size(probe)[0] > width and line:
                lines.append(line)
                line = word
            else:
                line = probe
        lines.append(line)
        for i, part in enumerate(lines):
            theme.draw_text(surface, part, (cx, y + i * (size + 5)), size, color, anchor="center")
