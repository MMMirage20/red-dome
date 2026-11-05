"""Верхняя панель (ФТ-04, B4): ресурсы с иконками, изменение за сол, круговой таймер сола,
колонисты и лимит армии. Когда кислород на исходе, иконка мигает и появляется предупреждение.
"""

from __future__ import annotations

import math

import pygame

from reddome.config.balance import Balance
from reddome.sim.economy import supply_cap, supply_reserved, supply_used
from reddome.sim.types import RESOURCE_KEYS, GameState, Side
from reddome.ui import theme
from reddome.ui.icons import icon
from reddome.ui.theme import Color
from reddome.ui.widgets import draw_tooltip

HUD_HEIGHT = 40
ITEM_WIDTH = 150
FIRST_ITEM_X = 150
NAMES = {
    "energy": "Энергия",
    "water": "Вода",
    "oxygen": "Кислород",
    "metal": "Металл",
    "colonists": "Колонисты",
    "army": "Армия",
}
HINTS = {
    "energy": "Дают панели; бур, генератор, переработчик и ангар тратят",
    "water": "Даёт ледяной бур; тратят колонисты и генератор",
    "oxygen": "Даёт генератор; без кислорода колония погибнет",
    "metal": "Приносят дроны с рудных полей",
    "colonists": "Живут в куполе и дышат кислородом",
    "army": "Занято / доступно; лимит дают купол и генераторы",
}


def _background(width: int) -> pygame.Surface:
    surface = pygame.Surface((width, HUD_HEIGHT + 6), pygame.SRCALPHA)
    for y in range(HUD_HEIGHT):
        pygame.draw.line(surface, (*theme.mix(theme.PANEL_LIGHT, theme.PANEL, y / HUD_HEIGHT), 245), (0, y), (width, y))
    pygame.draw.line(surface, (*theme.PANEL_EDGE, 255), (0, HUD_HEIGHT - 1), (width, HUD_HEIGHT - 1))
    for y in range(6):
        pygame.draw.line(surface, (0, 0, 0, 70 - y * 12), (0, HUD_HEIGHT + y), (width, HUD_HEIGHT + y))
    for i in range(7):
        x = FIRST_ITEM_X - 10 + ITEM_WIDTH * i
        pygame.draw.line(surface, (*theme.PANEL_EDGE, 120), (x, 8), (x, HUD_HEIGHT - 8))
    return surface


class TopBar:
    def __init__(self, side: Side = "player") -> None:
        self.side = side
        self.background = _background(theme.SCREEN_SIZE[0])
        self.items: list[tuple[str, pygame.Rect]] = []

    def oxygen_low(self, state: GameState) -> bool:
        colony = state.colonies[self.side]
        delta = colony.last_delta["oxygen"]
        return colony.oxygen_deficit_sols > 0 or (delta < 0 and colony.resources["oxygen"] < -delta * 2)

    def draw(self, surface: pygame.Surface, state: GameState, balance: Balance, time_ms: float) -> None:
        surface.blit(self.background, (0, 0))
        colony = state.colonies[self.side]
        self._draw_sol(surface, state, balance)
        blink = (time_ms // 400) % 2 == 0
        self.items = []
        x = FIRST_ITEM_X
        for key in RESOURCE_KEYS:
            alarm = key == "oxygen" and self.oxygen_low(state)
            self._item(surface, x, key, str(colony.resources[key]), colony.last_delta[key], alarm and blink)
            x += ITEM_WIDTH
        self._item(surface, x, "colonists", str(colony.colonists), None, False)
        x += ITEM_WIDTH
        used = supply_used(state, balance, self.side) + supply_reserved(state, balance, self.side)
        cap = supply_cap(state, balance, self.side)
        self._item(surface, x, "army", f"{used}/{cap}", None, False, theme.ALARM if used >= cap else theme.TEXT)
        theme.draw_text(surface, "Esc — пауза", (theme.SCREEN_SIZE[0] - 14, HUD_HEIGHT // 2), 14,
                        theme.TEXT_QUIET, anchor="midright")
        if self.oxygen_low(state) and blink:
            banner = theme.render_text("Кислород на исходе — стройте генератор и бур!", 18, theme.ALARM, "title")
            rect = banner.get_rect(midtop=(theme.SCREEN_SIZE[0] // 2, HUD_HEIGHT + 10))
            pygame.draw.rect(surface, (40, 8, 10), rect.inflate(24, 10), border_radius=8)
            pygame.draw.rect(surface, theme.ALARM, rect.inflate(24, 10), 1, border_radius=8)
            surface.blit(banner, rect)

    def _draw_sol(self, surface: pygame.Surface, state: GameState, balance: Balance) -> None:
        center = (24, HUD_HEIGHT // 2)
        progress = state.sol_elapsed_ms / (balance.sol_seconds * 1000)
        pygame.draw.circle(surface, theme.PANEL, center, 14)
        if progress > 0:
            steps = max(2, int(32 * progress))
            points = [center] + [
                (center[0] + math.sin(progress * math.tau * i / steps) * 13,
                 center[1] - math.cos(progress * math.tau * i / steps) * 13)
                for i in range(steps + 1)
            ]
            pygame.draw.polygon(surface, theme.dim(theme.WARNING, 0.7), points)
        pygame.draw.circle(surface, theme.WARNING, center, 14, 2)
        surface.blit(icon("sol", 14), (center[0] - 7, center[1] - 7))
        seconds_left = max(0, math.ceil(balance.sol_seconds - state.sol_elapsed_ms / 1000))
        theme.draw_text(surface, f"Сол {state.sol}", (46, 5), 17, theme.TEXT, kind="title")
        theme.draw_text(surface, f"ещё {seconds_left} с", (46, 22), 13, theme.TEXT_QUIET)

    def _item(self, surface: pygame.Surface, x: int, key: str, value: str, delta: int | None, alarm: bool,
              color: Color = theme.TEXT) -> None:
        rect = pygame.Rect(x - 6, 4, ITEM_WIDTH - 10, HUD_HEIGHT - 8)
        self.items.append((key, rect))
        if alarm:
            pygame.draw.rect(surface, (120, 20, 24), rect, border_radius=6)
        surface.blit(icon(key, 22), (x, HUD_HEIGHT // 2 - 11))
        label = theme.draw_text(surface, value, (x + 28, HUD_HEIGHT // 2), 19, color, anchor="midleft", kind="title")
        if delta:
            delta_color = theme.SUCCESS if delta > 0 else theme.ALARM
            theme.draw_text(surface, f"{delta:+d}", (label.right + 5, HUD_HEIGHT // 2 + 1), 14, delta_color,
                            anchor="midleft")

    def draw_tooltip(self, surface: pygame.Surface, mouse: tuple[int, int]) -> bool:
        for key, rect in self.items:
            if rect.collidepoint(mouse):
                lines = [(HINTS[key], theme.TEXT_QUIET)]
                if key in RESOURCE_KEYS:
                    lines.append(("Справа — изменение за прошлый сол", theme.TEXT_QUIET))
                draw_tooltip(surface, NAMES[key], lines, (max(rect.left + 300, 300), rect.bottom + 70))
                return True
        return False
