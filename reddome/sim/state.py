"""Создание стартового состояния и общие запросы к нему."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from reddome.sim.map import create_map, in_bounds, tile_at, tile_index
from reddome.sim.pathfinding import find_path
from reddome.sim.types import (
    SIDES,
    Building,
    BuildingType,
    Colony,
    Deposit,
    GameState,
    Point,
    Side,
    Unit,
    UnitType,
)

if TYPE_CHECKING:
    from reddome.config.balance import Balance


def create_colony(side: Side, balance: Balance) -> Colony:
    start = balance.side(side).start
    return Colony(
        side=side,
        resources={"energy": start.energy, "water": start.water, "oxygen": start.oxygen, "metal": start.metal},
        colonists=start.colonists,
        sol_start_metal=start.metal,
    )


# --- Поиск объектов ---------------------------------------------------------


def building_at(state: GameState, x: int, y: int) -> Building | None:
    return next((b for b in state.buildings if b.x == x and b.y == y), None)


def unit_at(state: GameState, x: int, y: int) -> Unit | None:
    return next((u for u in state.units if round(u.x) == x and round(u.y) == y), None)


def building_by_id(state: GameState, building_id: int | None) -> Building | None:
    return next((b for b in state.buildings if b.id == building_id), None)


def unit_by_id(state: GameState, unit_id: int | None) -> Unit | None:
    return next((u for u in state.units if u.id == unit_id), None)


def deposit_by_id(state: GameState, deposit_id: int | None) -> Deposit | None:
    return next((d for d in state.deposits if d.id == deposit_id), None)


def deposit_at(state: GameState, x: int, y: int) -> Deposit | None:
    """Месторождение, которому принадлежит клетка руды, если запас ещё не кончился."""
    point = Point(x, y)
    return next((d for d in state.deposits if d.amount > 0 and point in d.tiles), None)


def distance(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


def chebyshev(ax: float, ay: float, bx: float, by: float) -> int:
    return max(abs(round(ax) - round(bx)), abs(round(ay) - round(by)))


# --- Проходимость и пути ------------------------------------------------------


def is_blocked(state: GameState, x: int, y: int) -> bool:
    """Клетка непроходима для юнитов: за картой, скала или здание."""
    tile = tile_at(state.map, x, y)
    return tile is None or tile == "rock" or building_at(state, x, y) is not None


def find_free_tile_near(state: GameState, origin: Point, max_radius: int = 6) -> Point | None:
    """Ближайшая свободная клетка: обход расширяющимися квадратами в фиксированном порядке."""
    for r in range(1, max_radius + 1):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if max(abs(dx), abs(dy)) != r:
                    continue
                x, y = origin.x + dx, origin.y + dy
                if in_bounds(state.map, x, y) and not is_blocked(state, x, y) and unit_at(state, x, y) is None:
                    return Point(x, y)
    return None


def unit_tile(unit: Unit) -> Point:
    return Point(round(unit.x), round(unit.y))


def path_unit_to(state: GameState, unit: Unit, target: Point) -> bool:
    """Строит юниту путь A* до клетки. False — пути нет, старый путь не трогается."""
    path = find_path(state.map, lambda x, y: is_blocked(state, x, y), unit_tile(unit), target)
    if path is None:
        return False
    unit.path = path
    return True


def path_unit_next_to(state: GameState, unit: Unit, x: int, y: int) -> bool:
    """Путь к свободной клетке рядом с (x, y) — к зданию нельзя встать вплотную на его клетку.

    Если юнит уже стоит рядом, путь пустой и возвращается True.
    """
    if chebyshev(unit.x, unit.y, x, y) <= 1 and not is_blocked(state, round(unit.x), round(unit.y)):
        unit.path = []
        return True
    candidates = [
        Point(x + dx, y + dy)
        for dy in (-1, 0, 1)
        for dx in (-1, 0, 1)
        if (dx or dy) and in_bounds(state.map, x + dx, y + dy) and not is_blocked(state, x + dx, y + dy)
    ]
    candidates.sort(key=lambda p: (distance(unit.x, unit.y, p.x, p.y), p.y, p.x))
    return any(path_unit_to(state, unit, p) for p in candidates)


# --- Создание объектов --------------------------------------------------------


def add_building(
    state: GameState,
    balance: Balance,
    side: Side,
    type: BuildingType,
    at: Point,
    complete: bool = True,
) -> Building:
    """Добавляет здание. complete=False — стройплощадка с начальным здоровьем start_hp_ratio."""
    max_hp = balance.max_hp(side, type)
    building = Building(
        id=state.next_id,
        side=side,
        type=type,
        x=at.x,
        y=at.y,
        hp=max_hp if complete else max(1.0, max_hp * balance.construction.start_hp_ratio),
        complete=complete,
        build_progress=1.0 if complete else 0.0,
    )
    state.next_id += 1
    state.buildings.append(building)
    return building


def add_unit(state: GameState, balance: Balance, side: Side, type: UnitType, at: Point) -> Unit:
    unit = Unit(id=state.next_id, side=side, type=type, x=at.x, y=at.y, hp=float(balance.units[type].hp))
    state.next_id += 1
    state.units.append(unit)
    return unit


def deplete_deposit(state: GameState, deposit: Deposit) -> None:
    """Пустое поле превращается в грунт."""
    deposit.amount = 0
    for p in deposit.tiles:
        state.map.tiles[tile_index(state.map, p.x, p.y)] = "ground"


def create_initial_state(balance: Balance, seed: int) -> GameState:
    """У каждой стороны командный купол на базе и стартовые дроны рядом; рудные поля с полным запасом."""
    game_map = create_map(seed)
    state = GameState(
        seed=seed,
        map=game_map,
        colonies={side: create_colony(side, balance) for side in SIDES},
        difficulty=balance.difficulty,
    )
    state.deposits = [
        Deposit(id=i + 1, tiles=list(tiles), amount=balance.deposit.ore_amount, initial=balance.deposit.ore_amount)
        for i, tiles in enumerate(game_map.ore_fields)
    ]
    for side in SIDES:
        base = game_map.bases[side]
        add_building(state, balance, side, "dome", base)
        for _ in range(balance.side(side).start.drones):
            spot = find_free_tile_near(state, base)
            if spot is not None:
                add_unit(state, balance, side, "drone", spot)
    return state
