"""Нижняя панель в духе Warcraft III (B4): мини-карта (W3-02), портрет Аяна (ФТ-04),
карточка выбранного (HP, состояние дрона, очередь сборки) и сетка команд 3×3 с горячими клавишамиrfr.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from reddome.config.balance import Balance
from reddome.render.draw import radial_disc, rounded_panel
from reddome.render.terrain import Terrain, ore_level
from reddome.render.world import health_color
from reddome.sim.types import Building, Deposit, GameState, Unit
from reddome.ui import theme
from reddome.ui.commands import BUILDING_NAMES, UNIT_NAMES, Command, building_lines
from reddome.ui.icons import icon
from reddome.ui.widgets import draw_tooltip

W, H = theme.SCREEN_SIZE
PANEL_HEIGHT = 176
PANEL_TOP = H - PANEL_HEIGHT
MINIMAP_RECT = pygame.Rect(12, PANEL_TOP + 18, 216, 144)
PORTRAIT_RECT = pygame.Rect(240, PANEL_TOP + 18, 112, 144)
BUTTON = 50
GAP = 6
GRID_RECT = pygame.Rect(W - 12 - (BUTTON * 3 + GAP * 2), PANEL_TOP + 12, BUTTON * 3 + GAP * 2, BUTTON * 3 + GAP * 2)
INFO_RECT = pygame.Rect(PORTRAIT_RECT.right + 12, PANEL_TOP + 18, GRID_RECT.left - PORTRAIT_RECT.right - 28, 144)
IDLE_RECT = pygame.Rect(12, PANEL_TOP - 46, 76, 38)
SLOT = 40
QUEUE_SLOTS = 5
MULTI_COLUMNS = 14

TASK_TEXT = {
    "idle": "Ждёт приказа",
    "moving": "Идёт по приказу",
    "to_resource": "Летит к руде",
    "waiting": "Ждёт места у рудного поля",
    "gathering": "Добывает руду",
    "returning": "Несёт руду на базу",
    "to_site": "Летит на стройку",
    "building": "Строит",
    "repairing": "Чинит",
    "attacking": "Атакует",
    "attack_move": "Атака с движением",
}


def slot_rect(slot: int) -> pygame.Rect:
    col, row = slot % 3, slot // 3
    return pygame.Rect(GRID_RECT.x + col * (BUTTON + GAP), GRID_RECT.y + row * (BUTTON + GAP), BUTTON, BUTTON)


def _recess(surface: pygame.Surface, rect: pygame.Rect) -> None:
    """Утопленная рамка: тёмная заливка, тень сверху и светлая кромка снизу."""
    pygame.draw.rect(surface, (8, 14, 24), rect, border_radius=8)
    pygame.draw.rect(surface, (0, 0, 0), rect, 2, border_radius=8)
    pygame.draw.line(surface, theme.PANEL_EDGE, (rect.left + 8, rect.bottom), (rect.right - 8, rect.bottom))


def _panel_background() -> pygame.Surface:
    surface = pygame.Surface((W, PANEL_HEIGHT + 8), pygame.SRCALPHA)
    for y in range(8):
        pygame.draw.line(surface, (0, 0, 0, 10 + y * 10), (0, y), (W, y))
    body = rounded_panel((W + 20, PANEL_HEIGHT + 20), 16, (*theme.PANEL, 250), (*theme.PANEL_EDGE, 255))
    surface.blit(body, (-10, 8))
    # Металлическая кромка с заклёпками.
    pygame.draw.line(surface, theme.mix(theme.PANEL_EDGE, (255, 255, 255), 0.3), (6, 9), (W - 6, 9), 2)
    for x in range(30, W, 120):
        pygame.draw.circle(surface, theme.PANEL_EDGE, (x, 16), 2)
    for rect in (MINIMAP_RECT, PORTRAIT_RECT, INFO_RECT):
        # Фон рисуется с y = PANEL_TOP - 8, поэтому экранные прямоугольники сдвигаем.
        _recess(surface, rect.inflate(8, 8).move(0, 8 - PANEL_TOP))
    return surface


def _portrait(action: bool) -> pygame.Surface:
    """Аян — командир колонии: шлем со светящимся визором (Action — визор горит ярче)."""
    w, h = PORTRAIT_RECT.size
    s = pygame.Surface((w * 2, h * 2), pygame.SRCALPHA)
    for y in range(h * 2):
        pygame.draw.line(s, theme.mix((60, 28, 18), (14, 20, 34), y / (h * 2)), (0, y), (w * 2, y))
    cx, cy = w, h + 6
    pygame.draw.ellipse(s, theme.mix(theme.HULL_PLAYER_DARK, (0, 0, 0), 0.2), (cx - 86, cy + 60, 172, 120))
    pygame.draw.rect(s, theme.TEAM_PLAYER, (cx - 70, cy + 92, 140, 8))
    radial_disc(s, (cx, cy), 74, theme.HULL_PLAYER, theme.HULL_PLAYER_DARK)
    visor = pygame.Rect(0, 0, 112, 78)
    visor.center = (cx, cy + 4)
    hi = (255, 190, 90) if action else (70, 120, 160)
    lo = (120, 40, 10) if action else (12, 22, 40)
    layer = pygame.Surface(visor.size, pygame.SRCALPHA)
    for y in range(visor.height):
        pygame.draw.line(layer, theme.mix(hi, lo, y / visor.height), (0, y), (visor.width, y))
    mask = pygame.Surface(visor.size, pygame.SRCALPHA)
    pygame.draw.ellipse(mask, (255, 255, 255, 255), mask.get_rect())
    layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    s.blit(layer, visor)
    pygame.draw.ellipse(s, theme.mix(theme.HULL_PLAYER_DARK, (0, 0, 0), 0.3), visor, 4)
    pygame.draw.ellipse(s, (255, 255, 255, 110), (visor.x + 18, visor.y + 10, 40, 16))
    if action:
        for i in range(3):
            pygame.draw.line(s, (255, 240, 200), (visor.x + 30, visor.y + 40 + i * 8), (visor.right - 30 - i * 10, visor.y + 40 + i * 8), 2)
    pygame.draw.circle(s, theme.TEAM_PLAYER, (cx + 58, cy - 34), 6)
    return pygame.transform.smoothscale(s, (w, h))


@dataclass
class Selection:
    units: list[Unit]
    building: Building | None
    deposit: Deposit | None


class BottomPanel:
    def __init__(self, terrain: Terrain, game_map_size: tuple[int, int]) -> None:
        self.terrain = terrain
        self.map_w, self.map_h = game_map_size
        self.background = _panel_background()
        self.portraits = {False: _portrait(False), True: _portrait(True)}
        self._minimap_key: tuple[int, ...] = ()
        self._minimap: pygame.Surface | None = None
        self.commands: list[Command] = []
        self._idle_visible = False

    # --- Попадания -------------------------------------------------------------------

    def contains(self, pos: tuple[int, int]) -> bool:
        return pos[1] >= PANEL_TOP or (IDLE_RECT.collidepoint(pos) and self._idle_visible)

    def minimap_tile(self, pos: tuple[int, int]) -> tuple[float, float] | None:
        if not MINIMAP_RECT.collidepoint(pos):
            return None
        return ((pos[0] - MINIMAP_RECT.x) / MINIMAP_RECT.w * self.map_w,
                (pos[1] - MINIMAP_RECT.y) / MINIMAP_RECT.h * self.map_h)

    def command_at(self, pos: tuple[int, int]) -> Command | None:
        for command in self.commands:
            if slot_rect(command.slot).collidepoint(pos):
                return command
        return None

    def queue_index_at(self, pos: tuple[int, int], building: Building | None) -> int | None:
        if building is None:
            return None
        for i in range(len(building.queue)):
            if self._queue_rect(i).collidepoint(pos):
                return i
        return None

    def unit_index_at(self, pos: tuple[int, int], count: int) -> int | None:
        if count < 2:
            return None
        for i in range(min(count, MULTI_COLUMNS * 3)):
            if self._multi_rect(i).collidepoint(pos):
                return i
        return None

    def idle_clicked(self, pos: tuple[int, int]) -> bool:
        return self._idle_visible and IDLE_RECT.collidepoint(pos)

    @staticmethod
    def _queue_rect(i: int) -> pygame.Rect:
        return pygame.Rect(INFO_RECT.x + 96 + i * (SLOT + 6), INFO_RECT.bottom - SLOT - 10, SLOT, SLOT)

    @staticmethod
    def _multi_rect(i: int) -> pygame.Rect:
        col, row = i % MULTI_COLUMNS, i // MULTI_COLUMNS
        return pygame.Rect(INFO_RECT.x + 12 + col * (SLOT + 4), INFO_RECT.y + 30 + row * (SLOT + 4), SLOT, SLOT)

    # --- Кадр -------------------------------------------------------------------------

    def draw(self, surface: pygame.Surface, state: GameState, balance: Balance, selection: Selection,
             camera: tuple[float, float], view_height: int, action: bool, idle_drones: int,
             mouse: tuple[int, int], time_ms: float) -> None:
        surface.blit(self.background, (0, PANEL_TOP - 8))
        self._draw_minimap(surface, state, camera, view_height)
        surface.blit(self.portraits[action], PORTRAIT_RECT)
        theme.draw_text(surface, "Аян", (PORTRAIT_RECT.x + 8, PORTRAIT_RECT.bottom - 24), 17, theme.TEXT, kind="title", shadow=True)
        theme.draw_text(surface, "Action" if action else "Idle", (PORTRAIT_RECT.right - 8, PORTRAIT_RECT.bottom - 22), 13,
                        theme.WARNING if action else theme.TEXT_QUIET, anchor="topright")
        self._draw_info(surface, state, balance, selection, time_ms)
        self._draw_grid(surface, state, mouse)
        self._idle_visible = idle_drones > 0
        if idle_drones:
            hovered = IDLE_RECT.collidepoint(mouse)
            surface.blit(rounded_panel(IDLE_RECT.size, 8, (*theme.PANEL, 235), (*(theme.ACCENT if hovered else theme.PANEL_EDGE), 255)), IDLE_RECT)
            surface.blit(icon("drone", 28), (IDLE_RECT.x + 6, IDLE_RECT.y + 5))
            theme.draw_text(surface, str(idle_drones), (IDLE_RECT.right - 10, IDLE_RECT.centery), 20, theme.WARNING,
                            anchor="midright", kind="title")

    def draw_tooltips(self, surface: pygame.Surface, metal: int, mouse: tuple[int, int]) -> None:
        command = self.command_at(mouse)
        if command is not None:
            draw_tooltip(surface, command.title, command.lines, (GRID_RECT.right, GRID_RECT.top - 8),
                         command.cost, metal >= (command.cost or 0), command.key_label)
        elif self._idle_visible and IDLE_RECT.collidepoint(mouse):
            draw_tooltip(surface, "Свободный дрон", [("Выбрать простаивающего дрона", theme.TEXT_QUIET)],
                         (IDLE_RECT.left + 300, IDLE_RECT.top - 8), hotkey=".")

    def _draw_minimap(self, surface: pygame.Surface, state: GameState, camera: tuple[float, float],
                      view_height: int) -> None:
        key = tuple(ore_level(d) for d in state.deposits)
        if self._minimap is None or key != self._minimap_key:
            self._minimap = self.terrain.minimap(MINIMAP_RECT.size, state.deposits)
            self._minimap_key = key
        surface.blit(self._minimap, MINIMAP_RECT)
        sx, sy = MINIMAP_RECT.w / self.map_w, MINIMAP_RECT.h / self.map_h
        for b in state.buildings:
            color = theme.team_color(b.side)
            size = 7 if b.type == "dome" else 4
            rect = pygame.Rect(0, 0, size, size)
            rect.center = (MINIMAP_RECT.x + (b.x + 0.5) * sx, MINIMAP_RECT.y + (b.y + 0.5) * sy)
            pygame.draw.rect(surface, color if b.complete else theme.dim(color, 0.6), rect)
            pygame.draw.rect(surface, (0, 0, 0), rect, 1)
        for u in state.units:
            color = theme.mix(theme.team_color(u.side), (255, 255, 255), 0.35)
            pos = (MINIMAP_RECT.x + (u.x + 0.5) * sx, MINIMAP_RECT.y + (u.y + 0.5) * sy)
            pygame.draw.circle(surface, color, pos, 2 if u.type == "drone" else 2.5)
        view = pygame.Rect(
            MINIMAP_RECT.x + camera[0] / theme.TILE * sx,
            MINIMAP_RECT.y + camera[1] / theme.TILE * sy,
            W / theme.TILE * sx,
            view_height / theme.TILE * sy,
        ).clip(MINIMAP_RECT)
        pygame.draw.rect(surface, theme.TEXT, view, 1)

    def _draw_info(self, surface: pygame.Surface, state: GameState, balance: Balance, selection: Selection,
                   time_ms: float) -> None:
        r = INFO_RECT
        if selection.building is not None:
            self._draw_building(surface, state, balance, selection.building)
        elif len(selection.units) == 1:
            self._draw_unit(surface, state, balance, selection.units[0])
        elif selection.units:
            self._draw_group(surface, balance, selection.units)
        elif selection.deposit is not None:
            d = selection.deposit
            surface.blit(icon("metal", 64), (r.x + 14, r.y + 14))
            theme.draw_text(surface, "Рудное поле", (r.x + 94, r.y + 12), 22, theme.TEXT, kind="title")
            workers = sum(1 for u in state.units if u.task == "gathering" and u.target_id == d.id)
            theme.draw_text(surface, f"Осталось руды: {d.amount} из {d.initial}", (r.x + 94, r.y + 46), 16)
            theme.draw_text(surface, f"Добывают сейчас: {workers} из {balance.deposit.max_workers}", (r.x + 94, r.y + 70), 16,
                            theme.TEXT_QUIET)
            self._bar(surface, pygame.Rect(r.x + 94, r.y + 100, 260, 10), d.amount / d.initial, theme.METAL)
        else:
            lines = (
                "Выделите дронов рамкой или щелчком.",
                "ПКМ по руде — добывать, по врагу — атаковать, по земле — идти.",
                "B — строить, Ctrl+цифра — группа, «.» — свободный дрон.",
            )
            for i, line in enumerate(lines):
                theme.draw_text(surface, line, (r.x + 16, r.y + 22 + i * 26), 16, theme.TEXT_QUIET)

    @staticmethod
    def _bar(surface: pygame.Surface, rect: pygame.Rect, fraction: float, color: theme.Color | None = None) -> None:
        fraction = max(0.0, min(1.0, fraction))
        pygame.draw.rect(surface, (6, 10, 16), rect, border_radius=4)
        fill = rect.inflate(-2, -2)
        fill.width = round(fill.width * fraction)
        if fill.width > 0:
            pygame.draw.rect(surface, color or health_color(fraction), fill, border_radius=4)
        pygame.draw.rect(surface, theme.PANEL_EDGE, rect, 1, border_radius=4)

    def _header(self, surface: pygame.Surface, icon_name: str, title: str, side: str, hp: float, max_hp: float) -> None:
        r = INFO_RECT
        frame = pygame.Rect(r.x + 12, r.y + 12, 72, 72)
        pygame.draw.rect(surface, theme.PANEL_LIGHT, frame, border_radius=8)
        pygame.draw.rect(surface, theme.team_color(side), frame, 2, border_radius=8)
        surface.blit(icon(icon_name, 64), (frame.x + 4, frame.y + 4))
        theme.draw_text(surface, title, (r.x + 96, r.y + 10), 22, theme.TEXT, kind="title")
        if side != "player":
            theme.draw_text(surface, "ВЕКТОР", (r.right - 14, r.y + 14), 16, theme.TEAM_VECTOR, anchor="topright", kind="title")
        self._bar(surface, pygame.Rect(r.x + 96, r.y + 42, 220, 12), hp / max_hp)
        theme.draw_text(surface, f"{math.ceil(hp)} / {max_hp}", (r.x + 324, r.y + 48), 15, theme.TEXT_QUIET, anchor="midleft")

    def _draw_unit(self, surface: pygame.Surface, state: GameState, balance: Balance, u: Unit) -> None:
        r = INFO_RECT
        spec = balance.units[u.type]
        self._header(surface, u.type, UNIT_NAMES[u.type], u.side, u.hp, spec.hp)
        status = TASK_TEXT[u.task]
        progress: float | None = None
        target = next((b for b in state.buildings if b.id == u.target_id), None)
        if u.task == "gathering":
            progress = u.work_ms / (balance.workers.gather_time_sec * 1000)
            status = f"Добывает руду: {round(progress * 100)} %"
        elif u.task in ("building", "to_site") and target is not None:
            progress = target.build_progress
            status = f"Строит «{BUILDING_NAMES[target.type]}»: {round(progress * 100)} %"
        elif u.task == "repairing" and target is not None:
            status = f"Чинит «{BUILDING_NAMES[target.type]}»"
        if u.carry > 0 and u.task != "gathering":
            status = f"Несёт {u.carry} металла" + (" на базу" if u.task == "returning" else "")
        theme.draw_text(surface, status, (r.x + 96, r.y + 66), 17, theme.TEXT)
        if progress is not None:
            self._bar(surface, pygame.Rect(r.x + 96, r.y + 92, 260, 8), progress, theme.ACCENT)
        if u.type == "drone":
            detail = f"Груз {u.carry}/{balance.workers.carry} · скорость {spec.speed:g}"
        else:
            detail = f"Урон {spec.dps:g}/с · дальность {spec.range:g} · скорость {spec.speed:g}"
        theme.draw_text(surface, detail, (r.x + 96, r.y + 110), 15, theme.TEXT_QUIET)

    def _draw_group(self, surface: pygame.Surface, balance: Balance, units: list[Unit]) -> None:
        r = INFO_RECT
        drones = sum(1 for u in units if u.type == "drone")
        title = f"Выделено: {len(units)}"
        parts = []
        if drones:
            parts.append(f"дронов {drones}")
        if len(units) - drones:
            parts.append(f"роверов {len(units) - drones}")
        theme.draw_text(surface, title + " · " + ", ".join(parts), (r.x + 14, r.y + 6), 17, theme.TEXT, kind="title")
        for i, u in enumerate(units[: MULTI_COLUMNS * 3]):
            rect = self._multi_rect(i)
            pygame.draw.rect(surface, theme.PANEL_LIGHT, rect, border_radius=6)
            pygame.draw.rect(surface, theme.PANEL_EDGE, rect, 1, border_radius=6)
            surface.blit(icon(u.type, 32), (rect.x + 4, rect.y + 2))
            frac = u.hp / balance.units[u.type].hp
            bar = pygame.Rect(rect.x + 4, rect.bottom - 6, round((rect.w - 8) * frac), 3)
            pygame.draw.rect(surface, health_color(frac), bar)

    def _draw_building(self, surface: pygame.Surface, state: GameState, balance: Balance, b: Building) -> None:
        r = INFO_RECT
        spec = balance.buildings[b.type]
        self._header(surface, b.type, BUILDING_NAMES[b.type], b.side, b.hp, balance.max_hp(b.side, b.type))
        if not b.complete:
            builders = sum(1 for u in state.units if u.task == "building" and u.target_id == b.id)
            theme.draw_text(surface, f"Строится: {round(b.build_progress * 100)} % · строят дронов: {builders}",
                            (r.x + 96, r.y + 66), 17, theme.TEXT)
            self._bar(surface, pygame.Rect(r.x + 96, r.y + 92, 260, 8), b.build_progress, theme.ACCENT)
            if builders == 0:
                theme.draw_text(surface, "Нет строителей — ПКМ дроном по площадке", (r.x + 96, r.y + 108), 15, theme.WARNING)
            return
        if not b.powered:
            theme.draw_text(surface, "Отключено: не хватает энергии или воды", (r.x + 96, r.y + 66), 17, theme.ALARM)
        elif b.side == "player":
            lines = building_lines(balance, b.type)
            text = lines[0][0] if lines else "Работает"
            if b.type == "dome":
                text = f"Пункт сдачи руды · +{spec.supply} к лимиту армии · мест: {spec.colonist_slots}"
            theme.draw_text(surface, text, (r.x + 96, r.y + 66), 16, theme.TEXT_QUIET)
        if b.queue or b.type in ("dome", "hangar") and b.side == "player":
            theme.draw_text(surface, "Очередь:", (r.x + 14, r.bottom - SLOT // 2 - 10), 15, theme.TEXT_QUIET, anchor="midleft")
            for i in range(QUEUE_SLOTS):
                rect = self._queue_rect(i)
                pygame.draw.rect(surface, theme.PANEL_LIGHT if i < len(b.queue) else (10, 18, 30), rect, border_radius=6)
                pygame.draw.rect(surface, theme.PANEL_EDGE, rect, 1, border_radius=6)
                if i < len(b.queue):
                    item = b.queue[i]
                    surface.blit(icon(item.type, 32), (rect.x + 4, rect.y + 2))
                    if i == 0:
                        total = balance.units[item.type].build_time_sec * 1000
                        frac = 1 - item.remaining_ms / total
                        pygame.draw.rect(surface, theme.ACCENT, (rect.x + 3, rect.bottom - 6, round((rect.w - 6) * frac), 3))

    def _draw_grid(self, surface: pygame.Surface, state: GameState, mouse: tuple[int, int]) -> None:
        for slot in range(9):
            rect = slot_rect(slot)
            pygame.draw.rect(surface, (8, 14, 24), rect, border_radius=8)
            pygame.draw.rect(surface, (30, 44, 64), rect, 1, border_radius=8)
        metal = state.colonies["player"].resources["metal"]
        for command in self.commands:
            rect = slot_rect(command.slot)
            hovered = rect.collidepoint(mouse)
            top = theme.mix(theme.PANEL_LIGHT, theme.ACCENT, 0.35) if hovered else theme.PANEL_LIGHT
            pygame.draw.rect(surface, top, rect, border_radius=8)
            pygame.draw.rect(surface, theme.ACCENT if hovered else theme.PANEL_EDGE, rect, 2, border_radius=8)
            image = icon(command.icon, 36)
            if not command.enabled:
                image = image.copy()
                image.fill((90, 90, 90, 255), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(image, (rect.x + 7, rect.y + 5))
            theme.draw_text(surface, command.key_label, (rect.right - 4, rect.bottom - 2), 13, theme.WARNING,
                            anchor="bottomright", kind="title", shadow=True)
            if command.cost is not None:
                color = theme.TEXT if metal >= command.cost else theme.ALARM
                theme.draw_text(surface, str(command.cost), (rect.x + 4, rect.bottom - 2), 12, color, anchor="bottomleft", shadow=True)
