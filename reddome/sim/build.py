"""Стройка через рабочих (ФТ-06): проверка клетки, стройплощадка, прогресс, отмена."""

from __future__ import annotations

from typing import TYPE_CHECKING

from reddome.sim.map import in_bounds, tile_at
from reddome.sim.state import add_building, building_at, building_by_id, distance, unit_at, unit_by_id
from reddome.sim.types import GATHER_TASKS, Building, BuildingType, CommandResult, GameState, Point, SimEvent, Side, Unit
from reddome.sim.workers import finish_job, is_worker, start_building

if TYPE_CHECKING:
    from reddome.config.balance import Balance


def can_place(state: GameState, balance: Balance, side: Side, type: BuildingType, x: int, y: int) -> CommandResult:
    if type == "dome":
        return CommandResult.failure("Командный купол у колонии один")
    if not balance.mission(state.mission).allows_building(type):
        return CommandResult.failure("В этой миссии такое здание недоступно")
    if not in_bounds(state.map, x, y):
        return CommandResult.failure("За пределами карты")
    spec = balance.buildings[type]
    if spec.unique and any(b.side == side and b.type == type for b in state.buildings):
        return CommandResult.failure("Такое здание у колонии может быть только одно")
    tile = tile_at(state.map, x, y)
    if spec.needs == "ice" and tile != "ice":
        return CommandResult.failure("Бур ставится только на ледяное поле")
    if spec.needs == "ore" and tile != "ore":
        return CommandResult.failure("Переработчик ставится только на рудный выход")
    if spec.needs is None and tile != "ground":
        return CommandResult.failure("Здесь нельзя строить")
    if building_at(state, x, y) is not None:
        return CommandResult.failure("Клетка занята")
    if unit_at(state, x, y) is not None:
        return CommandResult.failure("На клетке стоит юнит")
    if state.colonies[side].resources["metal"] < spec.cost:
        return CommandResult.failure("Не хватает металла")
    return CommandResult.success()


def pick_builder(state: GameState, side: Side, x: int, y: int) -> Unit | None:
    """Ближайший свободный дрон: сначала простаивающие, потом добывающие."""
    candidates = []
    for unit in state.units:
        if unit.side != side or not is_worker(unit):
            continue
        if unit.task in ("idle", "moving"):
            priority = 0
        elif unit.task in GATHER_TASKS:
            priority = 1
        else:
            continue
        candidates.append((priority, distance(unit.x, unit.y, x, y), unit.id, unit))
    return min(candidates, key=lambda c: c[:3])[3] if candidates else None


def place_building(
    state: GameState,
    balance: Balance,
    side: Side,
    type: BuildingType,
    x: int,
    y: int,
    worker_id: int | None = None,
) -> CommandResult:
    """Списывает металл и ставит стройплощадку; строить её идёт указанный или ближайший свободный дрон."""
    check = can_place(state, balance, side, type, x, y)
    if not check.ok:
        return check
    worker: Unit | None = None
    if worker_id is not None:
        worker = unit_by_id(state, worker_id)
        if worker is None or worker.side != side or not is_worker(worker):
            return CommandResult.failure("Строить может только дрон")
    state.colonies[side].resources["metal"] -= balance.buildings[type].cost
    site = add_building(state, balance, side, type, Point(x, y), complete=False)
    worker = worker or pick_builder(state, side, x, y)
    if worker is not None:
        start_building(state, worker, site)
    return CommandResult.success(site.id)


def cancel_construction(state: GameState, balance: Balance, side: Side, building_id: int) -> CommandResult:
    """Отмена стройки возвращает refund_ratio металла; строители возвращаются к прежней работе."""
    site = building_by_id(state, building_id)
    if site is None or site.side != side or site.complete:
        return CommandResult.failure("Это не стройплощадка")
    refund = int(balance.buildings[site.type].cost * balance.construction.refund_ratio)
    state.colonies[side].resources["metal"] += refund
    state.buildings = [b for b in state.buildings if b.id != building_id]
    for unit in state.units:
        if unit.target_id == building_id and unit.task in ("to_site", "building"):
            finish_job(state, unit)
    return CommandResult.success()


def builders_on(state: GameState, site: Building) -> int:
    return sum(1 for u in state.units if u.task == "building" and u.target_id == site.id)


def construction_step(state: GameState, balance: Balance, dt_ms: int, events: list[SimEvent]) -> None:
    """Прогресс стройки: несколько дронов строят быстрее, но не больше max_builders.

    Здоровье площадки растёт вместе с прогрессом от start_hp_ratio до полного.
    """
    for site in state.buildings:
        if site.complete:
            continue
        builders = min(builders_on(state, site), balance.construction.max_builders)
        if builders == 0:
            continue
        spec = balance.buildings[site.type]
        step = min(builders * dt_ms / (spec.build_time_sec * 1000), 1.0 - site.build_progress)
        site.build_progress += step
        max_hp = balance.max_hp(site.side, site.type)
        site.hp = min(float(max_hp), site.hp + max_hp * (1 - balance.construction.start_hp_ratio) * step)
        if site.build_progress >= 1.0 - 1e-9:
            site.build_progress = 1.0
            site.complete = True
            state.stats[site.side].buildings_built += 1
            events.append(SimEvent("construction_complete", site.side, site.x, site.y, subject=site.type))
            for unit in state.units:
                if unit.target_id == site.id and unit.task in ("to_site", "building"):
                    finish_job(state, unit)
