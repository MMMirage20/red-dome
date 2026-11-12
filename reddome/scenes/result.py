"""Экран итогов (ФТ-12): результат, время, статистика партии крупными числами и очки (W3-10).

Очки считает sim/score.py по весам из balance.score; здесь — итог и расшифровка по строкам.
"""

from __future__ import annotations

from typing import Any

import pygame

from reddome.render.draw import glow
from reddome.scenes.base import Scene
from reddome.sim.score import Score, ScoreLine
from reddome.sim.types import Outcome, SideStats
from reddome.ui import theme
from reddome.ui.commands import difficulty_line
from reddome.ui.widgets import Button, card

REASONS = {
    "dome_destroyed": ("Купол ВЕКТОРа разрушен", "Ваш командный купол разрушен"),
    "oxygen": ("У ВЕКТОРа закончился кислород", "Кислород закончился"),
    "ice_held": ("Ледяные поля удержаны", "ВЕКТОР удержал ледяные поля"),
    "great_dome": ("Большой купол построен первым", "ВЕКТОР первым построил Большой купол"),
}
LAST_MISSION = 3


def score_part(line: ScoreLine) -> str:
    """«Победа +1000», «Враги 7×20», «Погибшие колонисты 6×−200»."""
    if line.key == "win":
        return f"{line.label} +{line.weight}"
    return f"{line.label} {line.count}×{line.weight}".replace("-", "−")


class ResultScene(Scene):
    opaque = True

    def enter(self, outcome: Outcome, sol: int = 0, elapsed_ms: int = 0, stats: dict[str, SideStats] | None = None,
              background: pygame.Surface | None = None, difficulty: str | None = None, score: Score | None = None,
              mission: int | None = None, **data: Any) -> None:
        self.mission = mission if mission is not None else self.app.mission
        self.background = background
        self.difficulty_text = difficulty_line(difficulty or self.app.difficulty)
        self.won = outcome.winner == "player"
        win_text, loss_text = REASONS[outcome.reason]
        self.reason = win_text if self.won else loss_text
        minutes, seconds = divmod(elapsed_ms // 1000, 60)
        own = (stats or {}).get("player", SideStats())
        self.tiles = [
            ("Время", f"{minutes}:{seconds:02d}"),
            ("Солов прожито", str(sol)),
            ("Добыто металла", str(own.metal_mined)),
            ("Собрано юнитов", str(own.units_trained)),
            ("Уничтожено врагов", str(own.enemy_units_killed + own.enemy_buildings_destroyed)),
            ("Потеряно юнитов", str(own.units_lost)),
        ]
        self.score = score
        self.score_text = f"Очки: {score.total:,}".replace(",", " ") if score is not None else ""
        #: Расшифровка — только ненулевые строки: «Победа +1000 · Население 6×50 …».
        self.score_parts = [score_part(line) for line in (score.lines if score is not None else ()) if line.count]
        w, h = theme.SCREEN_SIZE
        self.card_rect = pygame.Rect(0, 0, 720, 600 if score is not None else 520)
        self.card_rect.center = (w // 2, h // 2)
        color = theme.SUCCESS if self.won else theme.ALARM
        self.halo = glow(160, color)
        self.halo.fill((110, 110, 110), special_flags=pygame.BLEND_MULT)
        bottom = self.card_rect.bottom - 56
        self.buttons = [
            Button((w // 2 - 130, bottom), "Ещё раз", lambda: self.app.start("game", mission=self.mission), width=220),
            Button((w // 2 + 130, bottom), "В меню", lambda: self.app.start("menu"), width=220),
        ]
        profile = getattr(self.app, "profile", None)
        if profile is not None:
            profile.record_result(self.mission, self.won, score.total if score is not None else 0)
        if self.won and self.mission < LAST_MISSION:
            # ФТ-34: «Следующая миссия»; закрытая ведёт в магазин.
            self.buttons = [
                Button((w // 2 - 230, bottom), "Ещё раз", lambda: self.app.start("game", mission=self.mission), width=190),
                Button((w // 2, bottom), "Следующая миссия", self.next_mission, width=230),
                Button((w // 2 + 230, bottom), "В меню", lambda: self.app.start("menu"), width=190),
            ]

    def next_mission(self) -> None:
        nxt = self.mission + 1
        profile = getattr(self.app, "profile", None)
        if profile is not None and not profile.mission_unlocked(nxt):
            self.app.start("shop", back="missions")
            return
        self.app.mission = nxt
        self.app.start("game", mission=nxt)

    def handle_event(self, event: pygame.event.Event) -> None:
        for button in self.buttons:
            button.handle_event(event)

    def draw(self, surface: pygame.Surface) -> None:
        if self.background is not None:
            surface.blit(self.background, (0, 0))
        r = self.card_rect
        surface.blit(card(r.size), r)
        title, color = ("Победа", theme.SUCCESS) if self.won else ("Поражение", theme.ALARM)
        surface.blit(self.halo, self.halo.get_rect(center=(r.centerx, r.y + 70)), special_flags=pygame.BLEND_ADD)
        theme.draw_text(surface, title, (r.centerx, r.y + 70), 64, color, anchor="center", kind="title", shadow=True)
        theme.draw_text(surface, self.reason, (r.centerx, r.y + 128), 22, theme.TEXT, anchor="center")
        theme.draw_text(surface, self.difficulty_text, (r.right - 24, r.y + 20), 15, theme.TEXT_QUIET, anchor="topright")
        theme.draw_text(surface, f"Миссия {self.mission}", (r.x + 24, r.y + 20), 15, theme.TEXT_QUIET)
        for i, (label, value) in enumerate(self.tiles):
            col, row = i % 3, i // 3
            tile = pygame.Rect(r.x + 30 + col * 224, r.y + 170 + row * 124, 208, 108)
            pygame.draw.rect(surface, theme.PANEL_LIGHT, tile, border_radius=10)
            pygame.draw.rect(surface, theme.PANEL_EDGE, tile, 1, border_radius=10)
            theme.draw_text(surface, value, (tile.centerx, tile.y + 44), 40, theme.SAND, anchor="center", kind="title")
            theme.draw_text(surface, label, (tile.centerx, tile.bottom - 20), 15, theme.TEXT_QUIET, anchor="center")
        if self.score is not None:
            y = r.y + 170 + 2 * 124 + 14
            theme.draw_text(surface, self.score_text, (r.centerx, y + 18), 34, theme.WARNING, anchor="center",
                            kind="title", shadow=True)
            theme.draw_text(surface, " · ".join(self.score_parts), (r.centerx, y + 54), 15, theme.TEXT_QUIET,
                            anchor="center")
        for button in self.buttons:
            button.draw(surface)
