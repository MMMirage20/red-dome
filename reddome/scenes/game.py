"""Игровая сцена: переводит ввод игрока в команды Simulation и рисует мир, HUD и нижнюю панель.

Управление (W3-02, W3-04, W3-05):
    ЛКМ — выделить, рамка — выделить несколько, Shift — добавить, двойной щелчок — все такие же на экране;
    ПКМ — приказ по цели: руда — добывать, враг — атаковать, своя площадка — строить, земля — идти;
    Ctrl+цифра — назначить группу, цифра — выбрать группу (дважды — камера к группе);
    «.» — свободный дрон; WASD, стрелки и край экрана — камера; щелчок по мини-карте — камера туда.
Команды на клавишах из ui/commands.py; Esc отменяет режим, а без режима ставит паузу.

Жесты (W3-12) приходят из App в on_gesture и исполняются теми же методами, что мышь и клавиатура.
"""

from __future__ import annotations

import math
from typing import Any, cast

import pygame

from reddome.bot.adaptive import BotAdaptive
from reddome.bot.base import Bot
from reddome.bot.bot_v0 import BotV0
from reddome.bot.factory import make_bot
from reddome.bot.strategist import BotStrategist
from reddome.bot.style import STYLE_NAMES
from reddome.input.gestures import GestureFired
from reddome.render.world import WorldRenderer, tile_center
from reddome.scenes.base import Scene
from reddome.sim.build import can_place
from reddome.sim.map import tile_at
from reddome.sim.score import compute_score
from reddome.sim.state import building_by_id, deposit_at, find_free_tile_near, unit_by_id
from reddome.sim.simulation import Simulation
from reddome.sim.types import Building, BuildingType, Point, Side, Unit, UnitType
from reddome.sim.workers import DROPOFF_TYPES, nearest_deposit
from reddome.ui import theme
from reddome.ui.commands import Command, commands_for
from reddome.ui.cursor import OrderMarker, draw_markers, update_markers
from reddome.ui.gesture_hud import describe, draw_camera_icon, draw_indicator
from reddome.ui.hud import HUD_HEIGHT, TopBar
from reddome.ui.objective import draw_objective
from reddome.ui.panel import PANEL_TOP, BottomPanel, Selection
from reddome.ui.theme import Color

CAMERA_SPEED = 700  # пикселей в секунду
EDGE_SCROLL_ZONE = 10
HINT_MS = 2500
COMMANDER_ACTION_MS = 1200
DOUBLE_CLICK_MS = 350
DRAG_THRESHOLD = 6
END_DELAY_MS = 1500
GROUP_KEYS = {getattr(pygame, f"K_{d}"): d for d in range(10)}
MARKER_COLORS = {"move": theme.SUCCESS, "attack": theme.ALARM, "gather": theme.WARNING, "build": theme.ACCENT}
CAMERA_WARNING = "Камера недоступна — жесты выключены"
NO_DRONES = "Дронов нет"
NO_ROVERS = "Роверов нет — соберите в ангаре"
#: Подсказки событий среды и целей миссий (этап 3).
EVENT_HINTS: dict[str, tuple[str, Color]] = {
    "storm_start": ("Глобальная буря! Солнечные панели почти не дают энергии", theme.WARNING),
    "storm_end": ("Буря стихла — панели снова работают", theme.SUCCESS),
    "flare_start": ("Вспышка на Солнце! Роверы вне купола получают урон", theme.ALARM),
    "flare_end": ("Вспышка закончилась", theme.SUCCESS),
    "meteor_warning": ("Метеорит! Уведите юнитов из красного круга", theme.ALARM),
}


class GameScene(Scene):
    def enter(self, seed: int | None = None, autoplay: bool = False, mission: int | None = None, **data: Any) -> None:
        seed = self.app.seed if seed is None else seed
        mission = self.app.mission if mission is None else mission
        self.app.mission = mission
        self.sim = Simulation(self.app.balance, seed, self.app.difficulty, mission)
        #: ВЕКТОР миссии: v0 «Новичок», «Стратег» или «Адаптивный» (balance.json → missions).
        self.bot: Bot = make_bot(self.sim.mission.bot, "vector")
        self.sim.add_controller(self.bot)
        if autoplay:
            # Демо и скриншоты: за игрока тоже играет бот.
            self.sim.add_controller(BotV0("player") if mission == 1 else BotStrategist("player"))
        self.vector_great_dome_warned = False
        self.vector_hold_warned = False
        state = self.sim.state
        terrain = self.app.terrain_for(seed)
        self.world = WorldRenderer(self.app.sprites, self.app.graphics, self.sim, terrain)
        self.hud = TopBar("player")
        self.panel = BottomPanel(terrain, (state.map.width, state.map.height))
        self.selected: list[int] = []
        self.deposit_id: int | None = None
        self.groups: dict[int, list[int]] = {}
        self.menu = ""
        self.placing: BuildingType | None = None
        self.targeting: str | None = None
        self.markers: list[OrderMarker] = []
        self.drag_start: tuple[int, int] | None = None
        self.minimap_drag = False
        self.last_click = (-1000.0, "")
        self.last_group_key = (-1000.0, -1)
        self.idle_cycle = 0
        #: id последнего дрона, выбранного ладонью левой руки, когда свободных нет (обход по кругу).
        self.drone_cycle_id = 0
        self.gesture_last: GestureFired | None = None
        self.gesture_fired_ms = -1e9
        self.camera_warned = False
        self.time_ms = 0.0
        self.end_ms = 0.0
        self.hint = ""
        self.hint_until = 0.0
        self.hint_color: Color = theme.ALARM
        self.commander_action_until = 0.0
        self.camera = pygame.Vector2()
        base = state.map.bases["player"]
        self.center_camera(base.x, base.y)

    # --- Выделение ---------------------------------------------------------------

    def selection(self) -> Selection:
        state = self.sim.state
        units = [u for u in (unit_by_id(state, i) for i in self.selected) if u is not None]
        building = None
        if not units and len(self.selected) == 1:
            building = building_by_id(state, self.selected[0])
        deposit = next((d for d in state.deposits if d.id == self.deposit_id and d.amount > 0), None)
        return Selection(units, building, deposit if not units and building is None else None)

    def own_units(self) -> list[Unit]:
        return [u for u in self.selection().units if u.side == "player"]

    def own_building(self) -> Building | None:
        building = self.selection().building
        return building if building is not None and building.side == "player" else None

    def select(self, ids: list[int], add: bool = False) -> None:
        if add:
            current = [i for i in self.selected if unit_by_id(self.sim.state, i) is not None]
            self.selected = current + [i for i in ids if i not in current]
        else:
            self.selected = list(ids)
        self.deposit_id = None
        self.menu = ""
        self.placing = None
        self.targeting = None

    def idle_drones(self) -> list[Unit]:
        return [u for u in self.sim.state.units if u.side == "player" and u.type == "drone" and u.task == "idle"]

    def player_units(self, type_: UnitType) -> list[Unit]:
        return [u for u in self.sim.state.units if u.side == "player" and u.type == type_]

    # --- Камера и координаты ------------------------------------------------------------

    def center_camera(self, tile_x: float, tile_y: float) -> None:
        x, y = tile_center(tile_x, tile_y)
        self.camera.update(x - theme.SCREEN_SIZE[0] / 2, y - (HUD_HEIGHT + PANEL_TOP) / 2)
        self._clamp_camera()

    def _clamp_camera(self) -> None:
        game_map = self.sim.state.map
        max_x = game_map.width * theme.TILE - theme.SCREEN_SIZE[0]
        max_y = game_map.height * theme.TILE - PANEL_TOP
        self.camera.x = max(0, min(self.camera.x, max_x))
        self.camera.y = max(-HUD_HEIGHT, min(self.camera.y, max_y))

    def _scroll_camera(self, dt_ms: float) -> None:
        step = CAMERA_SPEED * dt_ms / 1000
        keys = pygame.key.get_pressed()
        mouse_x, mouse_y = pygame.mouse.get_pos()
        focused = pygame.mouse.get_focused() and self.drag_start is None
        width, height = theme.SCREEN_SIZE
        if keys[pygame.K_a] or keys[pygame.K_LEFT] or (focused and mouse_x < EDGE_SCROLL_ZONE):
            self.camera.x -= step
        if keys[pygame.K_d] or keys[pygame.K_RIGHT] or (focused and mouse_x > width - EDGE_SCROLL_ZONE):
            self.camera.x += step
        if keys[pygame.K_w] or keys[pygame.K_UP] or (focused and mouse_y < EDGE_SCROLL_ZONE):
            self.camera.y -= step
        if keys[pygame.K_s] or keys[pygame.K_DOWN] or (focused and mouse_y > height - EDGE_SCROLL_ZONE):
            self.camera.y += step
        self._clamp_camera()

    def to_world(self, pos: tuple[int, int]) -> tuple[float, float]:
        """Экран → клетки (дробные, центр клетки — x + 0.5)."""
        return (pos[0] + self.camera.x) / theme.TILE, (pos[1] + self.camera.y) / theme.TILE

    def tile_under(self, pos: tuple[int, int]) -> Point:
        x, y = self.to_world(pos)
        return Point(math.floor(x), math.floor(y))

    def entity_at(self, pos: tuple[int, int]) -> Unit | Building | None:
        x, y = self.to_world(pos)
        x, y = x - 0.5, y - 0.5
        state = self.sim.state
        best: tuple[float, Unit] | None = None
        for u in state.units:
            d = math.hypot(u.x - x, u.y - y)
            if d < (0.55 if u.type == "drone" else 0.65) and (best is None or d < best[0]):
                best = (d, u)
        if best is not None:
            return best[1]
        for b in state.buildings:
            reach = 1.15 if b.type in ("dome", "great_dome") else 0.65
            if abs(b.x - x) <= reach and abs(b.y - y) <= reach:
                return b
        return None

    def in_world(self, pos: tuple[int, int]) -> bool:
        return pos[1] >= HUD_HEIGHT and not self.panel.contains(pos)

    # --- Ввод -------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            self._on_key(event)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            self._on_mouse_down(event)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._on_left_up(event.pos)
        elif event.type == pygame.MOUSEMOTION and self.minimap_drag:
            tile = self.panel.minimap_tile(event.pos)
            if tile is not None:
                self.center_camera(tile[0] - 0.5, tile[1] - 0.5)

    def _on_key(self, event: pygame.event.Event) -> None:
        key = event.key
        if key == pygame.K_ESCAPE:
            if self.placing or self.targeting:
                self.placing = None
                self.targeting = None
            elif self.menu:
                self.menu = ""
            else:
                self.app.push("pause", background=self.app.snapshot(), difficulty=self.sim.state.difficulty)
            return
        if self.app.debug and key == pygame.K_k:
            self._debug_destroy_dome("vector")
            return
        if self.app.debug and key == pygame.K_l:
            self._debug_destroy_dome("player")
            return
        if key in GROUP_KEYS:
            self._on_group_key(GROUP_KEYS[key], bool(event.mod & pygame.KMOD_CTRL))
            return
        if key == pygame.K_PERIOD:
            self._select_idle_drone()
            return
        for command in self.panel.commands:
            if command.key == key:
                self.run_command(command)
                return

    def _on_group_key(self, digit: int, assign: bool) -> None:
        if assign:
            units = self.own_units()
            if units:
                self.groups[digit] = [u.id for u in units]
                self.show_hint(f"Группа {digit}: {len(units)}")
            return
        ids = [i for i in self.groups.get(digit, []) if unit_by_id(self.sim.state, i) is not None]
        if not ids:
            return
        self.select(ids)
        last_ms, last_digit = self.last_group_key
        if last_digit == digit and self.time_ms - last_ms < DOUBLE_CLICK_MS:
            first = unit_by_id(self.sim.state, ids[0])
            if first is not None:
                self.center_camera(first.x, first.y)
        self.last_group_key = (self.time_ms, digit)

    def _select_idle_drone(self, any_drone: bool = False) -> Unit | None:
        """Следующий свободный дрон (клавиша «.»). any_drone — если свободных нет, следующий дрон по кругу по id."""
        idle = self.idle_drones()
        if idle:
            drone = idle[self.idle_cycle % len(idle)]
            self.idle_cycle += 1
        elif any_drone and self.player_units("drone"):
            drones = sorted(self.player_units("drone"), key=lambda u: u.id)
            drone = next((u for u in drones if u.id > self.drone_cycle_id), drones[0])
            self.drone_cycle_id = drone.id
        else:
            self.show_hint(NO_DRONES if any_drone else "Свободных дронов нет")
            return None
        self.select([drone.id])
        self.center_camera(drone.x, drone.y)
        return drone

    def _on_mouse_down(self, event: pygame.event.Event) -> None:
        pos = event.pos
        if pos[1] < HUD_HEIGHT:
            return
        if self.panel.contains(pos):
            self._on_panel_click(event)
            return
        if event.button == 1:
            if self.placing:
                self._place_building(self.tile_under(pos), keep=bool(pygame.key.get_mods() & pygame.KMOD_SHIFT))
            elif self.targeting:
                self._apply_target(pos)
            else:
                self.drag_start = pos
        elif event.button == 3:
            if self.placing or self.targeting:
                self.placing = None
                self.targeting = None
            else:
                self._context_order(pos)

    def _on_panel_click(self, event: pygame.event.Event) -> None:
        pos = event.pos
        tile = self.panel.minimap_tile(pos)
        if tile is not None:
            if event.button == 1:
                self.minimap_drag = True
                self.center_camera(tile[0] - 0.5, tile[1] - 0.5)
            elif event.button == 3:
                self._order_to_point(Point(int(tile[0]), int(tile[1])))
            return
        if event.button != 1:
            return
        if self.panel.idle_clicked(pos):
            self._select_idle_drone()
            return
        command = self.panel.command_at(pos)
        if command is not None:
            self.run_command(command)
            return
        building = self.own_building()
        index = self.panel.queue_index_at(pos, building)
        if building is not None and index is not None:
            self._report(self.sim.cancel_training("player", building.id, index))
            return
        units = self.selection().units
        index = self.panel.unit_index_at(pos, len(units))
        if index is not None:
            if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                self.select([u.id for i, u in enumerate(units) if i != index])
            else:
                self.select([units[index].id])

    def _on_left_up(self, pos: tuple[int, int]) -> None:
        self.minimap_drag = False
        start, self.drag_start = self.drag_start, None
        if start is None:
            return
        add = bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
        if abs(pos[0] - start[0]) > DRAG_THRESHOLD or abs(pos[1] - start[1]) > DRAG_THRESHOLD:
            self._box_select(pygame.Rect(min(start[0], pos[0]), min(start[1], pos[1]),
                                         abs(pos[0] - start[0]), abs(pos[1] - start[1])), add)
        else:
            self._click_select(pos, add)

    def _screen_pos(self, x: float, y: float) -> tuple[float, float]:
        cx, cy = tile_center(x, y)
        return cx - self.camera.x, cy - self.camera.y

    def _box_select(self, rect: pygame.Rect, add: bool) -> None:
        ids = [u.id for u in self.sim.state.units if u.side == "player" and rect.collidepoint(self._screen_pos(u.x, u.y))]
        if ids or not add:
            self.select(ids, add)

    def _click_select(self, pos: tuple[int, int], add: bool) -> None:
        entity = self.entity_at(pos)
        if isinstance(entity, Unit):
            last_ms, last_type = self.last_click
            key = f"{entity.side}:{entity.type}"
            if entity.side == "player" and last_type == key and self.time_ms - last_ms < DOUBLE_CLICK_MS:
                view = pygame.Rect(0, HUD_HEIGHT, theme.SCREEN_SIZE[0], PANEL_TOP - HUD_HEIGHT)
                same = [u.id for u in self.sim.state.units if u.side == "player" and u.type == entity.type
                        and view.collidepoint(self._screen_pos(u.x, u.y))]
                self.select(same)
            elif add and entity.side == "player":
                if entity.id in self.selected:
                    self.selected = [i for i in self.selected if i != entity.id]
                else:
                    self.select([entity.id], add=True)
            else:
                self.select([entity.id])
            self.last_click = (self.time_ms, key)
            return
        if isinstance(entity, Building):
            self.select([entity.id])
            return
        if add:
            return
        tile = self.tile_under(pos)
        deposit = deposit_at(self.sim.state, tile.x, tile.y)
        self.select([])
        self.deposit_id = deposit.id if deposit is not None else None

    # --- Приказы -------------------------------------------------------------------

    def _marker(self, tile: Point, kind: str) -> None:
        x, y = tile_center(tile.x, tile.y)
        self.markers.append(OrderMarker(x, y, MARKER_COLORS[kind]))

    def _report(self, result: Any, tile: Point | None = None, kind: str = "move") -> bool:
        if result.ok:
            self.commander_action_until = self.time_ms + COMMANDER_ACTION_MS
            if tile is not None:
                self._marker(tile, kind)
            return True
        self.show_hint(result.reason)
        return False

    def _split(self) -> tuple[list[int], list[int], list[int]]:
        """id выделенных юнитов игрока: все, дроны, бойцы."""
        units = self.own_units()
        return ([u.id for u in units], [u.id for u in units if u.type == "drone"],
                [u.id for u in units if self.sim.is_fighter(u)])

    def _context_order(self, pos: tuple[int, int]) -> None:
        tile = self.tile_under(pos)
        building = self.own_building()
        everyone, drones, fighters = self._split()
        if not everyone:
            if building is not None and building.type in ("dome", "hangar") and building.complete:
                self._report(self.sim.set_rally("player", building.id, tile), tile, "build")
            return
        target = self.entity_at(pos)
        state = self.sim.state
        if target is not None and target.side != "player":
            if fighters:
                self._report(self.sim.attack("player", fighters, target.id), tile, "attack")
            others = [i for i in everyone if i not in fighters]
            if others:
                self._report(self.sim.move("player", others, tile), None if fighters else tile)
            return
        if isinstance(target, Building) and drones:
            others = [i for i in everyone if i not in drones]
            if not target.complete:
                self._report(self.sim.help_build("player", drones, target.id), tile, "build")
            elif target.hp < self.sim.balance.max_hp(target.side, target.type):
                self._report(self.sim.repair("player", drones, target.id), tile, "build")
            elif target.type in DROPOFF_TYPES and any(u.carry > 0 for u in self.own_units() if u.id in drones):
                self._report(self.sim.return_home("player", drones), tile, "gather")
            else:
                others = everyone
            if others:
                self._report(self.sim.move("player", others, tile), tile)
            return
        deposit = deposit_at(state, tile.x, tile.y)
        if deposit is not None and drones:
            self._report(self.sim.gather("player", drones, deposit.id), tile, "gather")
            others = [i for i in everyone if i not in drones]
            if others:
                self._report(self.sim.move("player", others, tile))
            return
        self._order_to_point(tile)

    def _order_to_point(self, tile: Point) -> None:
        everyone, _, _ = self._split()
        if not everyone:
            building = self.own_building()
            if building is not None and building.type in ("dome", "hangar") and building.complete:
                self._report(self.sim.set_rally("player", building.id, tile), tile, "build")
            return
        self._report(self.sim.move("player", everyone, tile), tile)

    def _apply_target(self, pos: tuple[int, int]) -> None:
        mode, self.targeting = self.targeting, None
        tile = self.tile_under(pos)
        _, drones, fighters = self._split()
        target = self.entity_at(pos)
        if mode == "gather":
            deposit = deposit_at(self.sim.state, tile.x, tile.y)
            if deposit is None:
                self.show_hint("Щёлкните по рудному полю")
            else:
                self._report(self.sim.gather("player", drones, deposit.id), tile, "gather")
        elif mode == "repair":
            if isinstance(target, Building) and target.side == "player":
                self._report(self.sim.repair("player", drones, target.id), tile, "build")
            else:
                self.show_hint("Щёлкните по своему зданию")
        elif mode == "attack":
            if target is not None and target.side != "player":
                self._report(self.sim.attack("player", fighters, target.id), tile, "attack")
            else:
                self._report(self.sim.attack_move("player", fighters, tile), tile, "attack")
        elif mode == "rally":
            building = self.own_building()
            if building is not None:
                self._report(self.sim.set_rally("player", building.id, tile), tile, "build")

    def _place_building(self, tile: Point, keep: bool) -> None:
        assert self.placing is not None
        drones = [u for u in self.own_units() if u.type == "drone"]
        builder = min(drones, key=lambda u: (math.hypot(u.x - tile.x, u.y - tile.y), u.id), default=None)
        result = self.sim.build("player", self.placing, tile.x, tile.y, builder.id if builder else None)
        if self._report(result, tile, "build") and not keep:
            self.placing = None
            self.menu = ""

    def run_command(self, command: Command) -> None:
        everyone, _, _ = self._split()
        building = self.own_building()
        action = command.action
        if action in ("gather", "repair", "attack", "rally"):
            self.targeting = action
            self.placing = None
        elif action == "build_menu":
            self.menu = "build"
        elif action == "back":
            self.menu = ""
        elif action == "place":
            if command.enabled:
                self.placing = command.arg  # type: ignore[assignment]
                self.targeting = None
            else:
                self.show_hint("Не хватает металла")
        elif action == "return":
            self._report(self.sim.return_home("player", everyone))
        elif action == "stop":
            self._report(self.sim.stop("player", everyone))
        elif action == "train" and building is not None:
            self._report(self.sim.train("player", cast(UnitType, command.arg), building.id))
        elif action == "cancel_build" and building is not None:
            if self._report(self.sim.cancel_construction("player", building.id)):
                self.select([])
        elif action == "cancel_train" and building is not None:
            self._report(self.sim.cancel_training("player", building.id))

    def show_hint(self, message: str, color: Color = theme.ALARM) -> None:
        self.hint = message
        self.hint_color = color
        self.hint_until = self.time_ms + HINT_MS

    # --- Жесты (W3-12) -------------------------------------------------------------

    def on_gesture(self, fired: GestureFired) -> None:
        """Команда жеста. Отказы показываются той же подсказкой, что ошибки мыши (текст из CommandResult)."""
        self.commander_action_until = self.time_ms + COMMANDER_ACTION_MS
        self.gesture_last = fired
        self.gesture_fired_ms = self.time_ms
        handlers = {
            "select_drone": self._gesture_select_drone,
            "select_rovers": self._gesture_select_rovers,
            "attack_base": self._gesture_attack_base,
            "gather": self._gesture_gather,
            "retreat": self._gesture_retreat,
            "train_drone": lambda: self._gesture_train("drone"),
            "train_rover": lambda: self._gesture_train("guard_rover"),
            "pause": self._gesture_pause,
            "help_build": self._gesture_help_build,
            "train_rocket": lambda: self._gesture_train("rocket_rover"),
        }
        done = handlers[fired.command]()
        if done:
            self.show_hint(f"Жест: {describe(fired)} — {done}", theme.SUCCESS)

    def _gesture_select_drone(self) -> str | None:
        return "выбран дрон" if self._select_idle_drone(any_drone=True) is not None else None

    def _gesture_select_rovers(self) -> str | None:
        rovers = self.player_units("guard_rover")
        if not rovers:
            self.show_hint(NO_ROVERS)
            return None
        self.select([u.id for u in rovers])
        return f"выбраны роверы: {len(rovers)}"

    def _gesture_attack_base(self) -> str | None:
        """Выделенные роверы (или все, если среди выделенных роверов нет) идут атакой с движением к куполу ВЕКТОРа."""
        _, _, fighters = self._split()
        if not fighters:
            fighters = [u.id for u in self.sim.state.units if u.side == "player" and self.sim.is_fighter(u)]
        if not fighters:
            self.show_hint(NO_ROVERS)
            return None
        dome = next((b for b in self.sim.state.buildings if b.side == "vector" and b.type == "dome"), None)
        if dome is None:
            return None
        target = find_free_tile_near(self.sim.state, Point(dome.x, dome.y)) or Point(dome.x, dome.y)
        ok = self._report(self.sim.attack_move("player", fighters, target), target, "attack")
        return f"роверы идут на базу ВЕКТОРа: {len(fighters)}" if ok else None

    def _gesture_gather(self) -> str | None:
        """«За работу»: выделенные дроны или все свободные — на ближайшее к каждому непустое поле."""
        _, drones, _ = self._split()
        if not drones:
            drones = [u.id for u in self.idle_drones()]
        if not drones:
            self.show_hint("Свободных дронов нет" if self.player_units("drone") else NO_DRONES)
            return None
        groups: dict[int, list[int]] = {}
        for drone_id in drones:
            drone = unit_by_id(self.sim.state, drone_id)
            deposit = nearest_deposit(self.sim.state, drone.x, drone.y) if drone is not None else None
            if deposit is not None:
                groups.setdefault(deposit.id, []).append(drone_id)
        if not groups:
            self.show_hint("Здесь нет руды")
            return None
        sent = 0
        for deposit_id, ids in sorted(groups.items()):
            deposit = next(d for d in self.sim.state.deposits if d.id == deposit_id)
            tile = deposit.tiles[len(deposit.tiles) // 2]
            if self._report(self.sim.gather("player", ids, deposit_id), tile, "gather"):
                sent += len(ids)
        return f"дроны за работой: {sent}" if sent else None

    def _gesture_retreat(self) -> str | None:
        """«Отступить»: выделенные юниты, а если ничего не выделено — все роверы, к куполу."""
        units, _, _ = self._split()
        if not units:
            units = [u.id for u in self.player_units("guard_rover")]
        if not units:
            self.show_hint(NO_ROVERS)
            return None
        dome = next((b for b in self.sim.state.buildings if b.side == "player" and b.type == "dome"), None)
        tile = Point(dome.x, dome.y) if dome is not None else None
        ok = self._report(self.sim.return_home("player", units), tile, "move")
        return "отступают к куполу" if ok else None

    def _gesture_help_build(self) -> str | None:
        """Кулак левой: выделенные дроны (или все свободные) — на стройплощадку игрока.

        Сначала Большой купол, иначе ближайшая к куполу площадка, где строителей меньше всего.
        """
        state = self.sim.state
        sites = [b for b in state.buildings if b.side == "player" and not b.complete]
        if not sites:
            self.show_hint("Стройплощадок нет — начните стройку (B)")
            return None
        _, drones, _ = self._split()
        if not drones:
            drones = [u.id for u in self.idle_drones()]
        if not drones:
            drones = [u.id for u in self.player_units("drone") if u.task in ("to_resource", "gathering", "waiting")][:2]
        if not drones:
            self.show_hint(NO_DRONES)
            return None
        base = state.map.bases["player"]
        site = min(sites, key=lambda b: (b.type != "great_dome",
                                         sum(1 for u in state.units if u.target_id == b.id and u.task == "building"),
                                         math.hypot(b.x - base.x, b.y - base.y), b.id))
        if not self._report(self.sim.help_build("player", drones, site.id), Point(site.x, site.y), "build"):
            return None
        return f"дроны на стройку: {len(drones)}"

    def _gesture_train(self, unit_type: UnitType) -> str | None:
        result = self.sim.train("player", unit_type)
        producer_type = "dome" if unit_type == "drone" else "hangar"
        producer = next((b for b in self.sim.state.buildings
                         if b.side == "player" and b.type == producer_type and b.queue), None)
        tile = Point(producer.x, producer.y) if producer is not None else None
        if not self._report(result, tile, "build"):
            return None
        return {"drone": "дрон в очереди", "rocket_rover": "ракетный ровер в очереди"}.get(unit_type, "ровер в очереди")

    def _gesture_pause(self) -> str | None:
        self.app.push("pause", background=self.app.snapshot(), difficulty=self.sim.state.difficulty)
        return None

    def _debug_destroy_dome(self, side: Side) -> None:
        dome = next((b for b in self.sim.state.buildings if b.side == side and b.type == "dome"), None)
        if dome is not None:
            self.sim.damage_building(dome.id, dome.hp)

    # --- Обновление ---------------------------------------------------------

    def update(self, dt_ms: float) -> None:
        self.time_ms += dt_ms
        self._scroll_camera(dt_ms)
        self.sim.update(dt_ms)
        events = self.sim.drain_events()
        if any(e.kind == "panel_dusted" and e.side == "player" for e in events):
            self.show_hint("Пылевой вихрь засыпал солнечную панель — она даёт меньше энергии", theme.WARNING)
        for event in events:
            if event.kind in EVENT_HINTS:
                self.show_hint(*EVENT_HINTS[event.kind])
        self._mission_hints()
        self.world.handle_events(events)
        self.world.update(dt_ms, self.sim)
        self.markers = update_markers(self.markers, dt_ms)
        if self.app.gestures.unavailable and not self.camera_warned:
            # НФТ-06: предупреждение один раз за партию; причина видна в оверлее F9.
            self.camera_warned = True
            self.show_hint(CAMERA_WARNING, theme.WARNING)
        elif self.camera_warned and self.app.gestures.status == "running":
            # Камера переподключилась сама (input/camera.py, RETRY_S).
            self.camera_warned = False
            self.show_hint("Камера подключилась — жесты включены", theme.SUCCESS)

        state = self.sim.state
        alive = {u.id for u in state.units} | {b.id for b in state.buildings}
        self.selected = [i for i in self.selected if i in alive]
        metal = state.colonies["player"].resources["metal"]
        selection = self.selection()
        building = self.own_building()
        own_units = [u for u in selection.units if u.side == "player"]
        ready = frozenset(b.type for b in state.buildings if b.side == "player" and b.complete)
        self.panel.commands = commands_for(self.sim.balance, metal, own_units, building, self.menu, self.sim.mission, ready)
        if self.menu and not any(c.action == "place" for c in self.panel.commands):
            self.menu = ""
        self.app.cursor_kind = self._cursor_kind()

        if state.outcome is not None:
            self.end_ms += dt_ms
            if self.end_ms >= END_DELAY_MS:
                self.app.start("result", outcome=state.outcome, sol=state.sol, elapsed_ms=state.elapsed_ms,
                               stats=state.stats, difficulty=state.difficulty, background=self.app.snapshot(),
                               score=compute_score(state, self.sim.balance), mission=state.mission)

    def _mission_hints(self) -> None:
        """Однократные предупреждения о том, что ВЕКТОР близок к победе по цели миссии."""
        state, mission = self.sim.state, self.sim.mission
        if mission.goal == "great_dome" and not self.vector_great_dome_warned:
            if any(b.side == "vector" and b.type == "great_dome" for b in state.buildings):
                self.vector_great_dome_warned = True
                self.show_hint("ВЕКТОР строит Большой купол! Разрушьте стройку, пока он не достроен", theme.ALARM)
        if mission.goal == "hold_ice" and not self.vector_hold_warned and state.ice_hold_sols["vector"] >= 1:
            self.vector_hold_warned = True
            self.show_hint(f"ВЕКТОР держит {mission.hold_fields} ледяных поля — отбейте хотя бы одно", theme.ALARM)

    def _cursor_kind(self) -> str:
        if self.targeting == "attack":
            return "attack"
        if self.targeting:
            return {"gather": "gather", "repair": "repair"}.get(self.targeting, "target")
        mouse = pygame.mouse.get_pos()
        if self.placing or not self.in_world(mouse):
            return "normal"
        _, drones, fighters = self._split()
        target = self.entity_at(mouse)
        if target is not None and target.side != "player" and fighters:
            return "attack"
        if drones:
            if isinstance(target, Building) and target.side == "player" and not target.complete:
                return "build"
            tile = self.tile_under(mouse)
            if target is None and tile_at(self.sim.state.map, tile.x, tile.y) == "ore":
                return "gather"
        return "normal"

    # --- Отрисовка ----------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        state = self.sim.state
        mouse = pygame.mouse.get_pos()
        camera = (self.camera.x, self.camera.y)
        hovered = self.entity_at(mouse) if self.in_world(mouse) else None
        building = self.own_building()
        rally_of = building if building is not None and building.type in ("dome", "hangar") else None
        self.world.draw(surface, self.sim, camera, set(self.selected), hovered.id if hovered else None, rally_of)
        draw_markers(surface, self.markers, camera)
        if self.placing and self.in_world(mouse):
            self._draw_ghost(surface, self.tile_under(mouse))
        if self.drag_start is not None:
            rect = pygame.Rect(min(self.drag_start[0], mouse[0]), min(self.drag_start[1], mouse[1]),
                               abs(mouse[0] - self.drag_start[0]), abs(mouse[1] - self.drag_start[1]))
            box = pygame.Surface(rect.size, pygame.SRCALPHA)
            box.fill((*theme.SUCCESS, 40))
            surface.blit(box, rect)
            pygame.draw.rect(surface, theme.SUCCESS, rect, 1)

        self.hud.draw(surface, state, self.sim.balance, self.time_ms)
        draw_objective(surface, state, self.sim.balance, self.sim.mission)
        action = self.time_ms < self.commander_action_until
        self.panel.draw(surface, state, self.sim.balance, self.selection(), camera, PANEL_TOP, action,
                        len(self.idle_drones()), mouse, self.time_ms)
        draw_camera_icon(surface, self.app.gestures)
        if self.app.gestures.active:
            draw_indicator(surface, self.app.gestures, self.gesture_last, self.gesture_fired_ms, self.time_ms)
        self._draw_mode_hint(surface)
        if not self.hud.draw_tooltip(surface, mouse):
            self.panel.draw_tooltips(surface, state.colonies["player"].resources["metal"], mouse)

    def _draw_mode_hint(self, surface: pygame.Surface) -> None:
        text, color = "", theme.TEXT
        if self.time_ms < self.hint_until:
            text, color = self.hint, self.hint_color
        elif self.placing:
            text = "ЛКМ — поставить · Shift — несколько · ПКМ или Esc — отмена"
        elif self.targeting:
            text = {
                "gather": "Укажите рудное поле",
                "repair": "Укажите своё здание для ремонта",
                "attack": "Укажите врага или точку для атаки с движением",
                "rally": "Укажите точку сбора",
            }[self.targeting]
        elif self.app.debug:
            text, color = "Отладка: K — победа, L — поражение", theme.TEXT_QUIET
            if isinstance(self.bot, BotAdaptive):
                guess = STYLE_NAMES[self.bot.style] if self.bot.style else "ещё не определён"
                text += f" · ВЕКТОР считает ваш стиль: {guess} ({self.bot.classifier.source})"
        if not text:
            return
        label = theme.render_text(text, 17, color)
        rect = label.get_rect(midbottom=(theme.SCREEN_SIZE[0] // 2, PANEL_TOP - 14))
        pygame.draw.rect(surface, (*theme.PANEL,), rect.inflate(24, 10), border_radius=8)
        pygame.draw.rect(surface, theme.PANEL_EDGE, rect.inflate(24, 10), 1, border_radius=8)
        surface.blit(label, rect)

    def _ghost_tiles(self, tile: Point) -> list[Point]:
        """Клетки для подсветки: для бура и переработчика — свой тип клеток на экране, иначе — вокруг курсора."""
        assert self.placing is not None
        state = self.sim.state
        needs = self.sim.balance.buildings[self.placing].needs
        if needs is None:
            return [Point(tile.x + dx, tile.y + dy) for dy in range(-2, 3) for dx in range(-2, 3)]
        x0, y0 = int(self.camera.x // theme.TILE), int(self.camera.y // theme.TILE)
        x1, y1 = x0 + theme.SCREEN_SIZE[0] // theme.TILE + 1, y0 + PANEL_TOP // theme.TILE + 1
        return [Point(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)
                if tile_at(state.map, x, y) == needs]

    def _draw_ghost(self, surface: pygame.Surface, tile: Point) -> None:
        assert self.placing is not None
        state, balance = self.sim.state, self.sim.balance
        mark = pygame.Surface((theme.TILE - 4, theme.TILE - 4), pygame.SRCALPHA)
        for p in self._ghost_tiles(tile):
            ok = can_place(state, balance, "player", self.placing, p.x, p.y).ok
            mark.fill((*(theme.SUCCESS if ok else theme.ALARM), 50 if ok else 30))
            surface.blit(mark, (p.x * theme.TILE + 2 - self.camera.x, p.y * theme.TILE + 2 - self.camera.y))
        result = can_place(state, balance, "player", self.placing, tile.x, tile.y)
        sprite = self.app.sprites.get_sprite(self.placing, "player", "on").copy()
        tint = (120, 255, 140, 170) if result.ok else (255, 110, 110, 170)
        sprite.fill(tint, special_flags=pygame.BLEND_RGBA_MULT)
        x, y = tile_center(tile.x, tile.y)
        surface.blit(sprite, sprite.get_rect(center=(x - self.camera.x, y - self.camera.y)))
        rect = pygame.Rect(tile.x * theme.TILE - self.camera.x, tile.y * theme.TILE - self.camera.y, theme.TILE, theme.TILE)
        pygame.draw.rect(surface, theme.SUCCESS if result.ok else theme.ALARM, rect, 2, border_radius=4)
        if not result.ok and result.reason != "Не хватает металла":
            theme.draw_text(surface, result.reason, (rect.centerx, rect.top - 22), 15, theme.ALARM, anchor="center", shadow=True)
