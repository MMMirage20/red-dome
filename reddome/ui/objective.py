"""Цель миссии и события среды на экране (этап 3, ФТ-24, ФТ-25, ФТ-27–ФТ-29).

Слева под верхней панелью — карточка цели: что нужно сделать и как идут дела (ледяные поля,
Большой купол). По центру — баннер бури или вспышки: за сколько секунд начнётся и что делать.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from reddome.sim.hazards import flare_phase, storm_phase
from reddome.sim.objectives import fields_held, great_dome_progress
from reddome.ui import theme
from reddome.ui.hud import HUD_HEIGHT

if TYPE_CHECKING:
    from reddome.config.balance import Balance, MissionSpec
    from reddome.sim.types import GameState
    from reddome.ui.theme import Color

#: За сколько секунд до бури и вспышки показывать обратный отсчёт.
COUNTDOWN_SEC = 20


def objective_lines(state: GameState, mission: MissionSpec) -> list[tuple[str, Color]]:
    """Строки карточки цели: заголовок и прогресс."""
    if mission.goal == "hold_ice":
        total = len(state.map.ice_fields)
        mine, theirs = fields_held(state, "player"), fields_held(state, "vector")
        lines: list[tuple[str, Color]] = [
            (f"Цель: удержать {mission.hold_fields} из {total} ледяных полей {mission.hold_sols} солов", theme.TEXT),
            (f"Ваши поля: {mine} · удержание {state.ice_hold_sols['player']}/{mission.hold_sols}",
             theme.SUCCESS if mine >= mission.hold_fields else theme.TEXT_QUIET),
            (f"Поля ВЕКТОРа: {theirs} · удержание {state.ice_hold_sols['vector']}/{mission.hold_sols}",
             theme.ALARM if theirs >= mission.hold_fields else theme.TEXT_QUIET),
        ]
        return lines
    if mission.goal == "great_dome":
        def progress(side: str) -> str:
            value = great_dome_progress(state, side)  # type: ignore[arg-type]
            return "не начат" if value is None else f"{round(value * 100)} %"

        vector = great_dome_progress(state, "vector")
        return [
            ("Цель: разрушить купол ВЕКТОРа или первым построить Большой купол", theme.TEXT),
            (f"Ваш Большой купол: {progress('player')}", theme.TEXT_QUIET),
            (f"Большой купол ВЕКТОРа: {progress('vector')}", theme.ALARM if vector is not None else theme.TEXT_QUIET),
        ]
    return [("Цель: разрушить командный купол ВЕКТОРа", theme.TEXT)]


def hazard_banner(state: GameState, balance: Balance, mission: MissionSpec) -> tuple[str, Color] | None:
    """Текст баннера события: идёт сейчас или начнётся в ближайшие COUNTDOWN_SEC секунд."""
    if mission.has_event("solar_flare"):
        active, until_ms = flare_phase(state, balance)
        if active:
            return "Вспышка на Солнце: роверы вне купола получают урон — уведите их к куполу!", theme.ALARM
        if until_ms <= COUNTDOWN_SEC * 1000:
            return f"Вспышка на Солнце через {until_ms // 1000 + 1} с — уведите роверы к куполу", theme.WARNING
    if mission.has_event("storm"):
        active, until_ms = storm_phase(state, balance)
        if active:
            return "Глобальная буря: панели почти не дают энергии — выручит реактор", theme.WARNING
        if until_ms <= COUNTDOWN_SEC * 1000:
            return f"Глобальная буря через {until_ms // 1000 + 1} с — запасите энергию", theme.WARNING
    return None


def draw_objective(surface: pygame.Surface, state: GameState, balance: Balance, mission: MissionSpec) -> None:
    lines = objective_lines(state, mission)
    rendered = [theme.render_text(text, 15 if i else 16, color, "title" if i == 0 else "body")
                for i, (text, color) in enumerate(lines)]
    width = max(r.get_width() for r in rendered) + 24
    height = sum(r.get_height() + 3 for r in rendered) + 14
    box = pygame.Surface((width, height), pygame.SRCALPHA)
    box.fill((*theme.PANEL, 200))
    pygame.draw.rect(box, (*theme.PANEL_EDGE, 255), box.get_rect(), 1, border_radius=8)
    y = 7
    for r in rendered:
        box.blit(r, (12, y))
        y += r.get_height() + 3
    surface.blit(box, (10, HUD_HEIGHT + 8))

    banner = hazard_banner(state, balance, mission)
    if banner is None:
        return
    text, color = banner
    label = theme.render_text(text, 17, color, "title")
    rect = label.get_rect(midtop=(theme.SCREEN_SIZE[0] // 2, HUD_HEIGHT + 52))
    pygame.draw.rect(surface, (30, 14, 8), rect.inflate(24, 10), border_radius=8)
    pygame.draw.rect(surface, color, rect.inflate(24, 10), 1, border_radius=8)
    surface.blit(label, rect)
