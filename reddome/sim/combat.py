"""Бой (W3-09): автозахват цели, атака, атака с движением, разрушение юнитов и зданий.

Боевые задачи юнита с dps > 0:
    idle        — стоит, но сам атакует врага в радиусе aggro_radius;
    attacking   — атакует назначенную цель (target_id), догоняя её;
    attack_move — идёт к attack_point и по дороге атакует всех встречных врагов;
    moving      — просто идёт, врагов игнорирует.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from reddome.sim.state import building_by_id, distance, path_unit_next_to, path_unit_to, unit_by_id, unit_tile
from reddome.sim.types import Building, CommandResult, GameState, Point, SimEvent, Side, Unit

if TYPE_CHECKING:
    from reddome.config.balance import Balance

#: Сколько добавить к дальности атаки: половина клетки юнита или чуть больше для здания.
UNIT_REACH = 0.5
BUILDING_REACH = 0.75


def entity_by_id(state: GameState, entity_id: int | None) -> Unit | Building | None:
    return unit_by_id(state, entity_id) or building_by_id(state, entity_id)


def is_fighter(balance: Balance, unit: Unit) -> bool:
    return balance.units[unit.type].dps > 0


def destroy_unit(state: GameState, unit: Unit, killer: Side, events: list[SimEvent]) -> None:
    state.units = [u for u in state.units if u.id != unit.id]
    state.stats[unit.side].units_lost += 1
    state.stats[killer].enemy_units_killed += 1
    events.append(SimEvent("unit_destroyed", unit.side, unit.x, unit.y, subject=unit.type))


def destroy_building(state: GameState, building: Building, killer: Side, events: list[SimEvent]) -> None:
    state.buildings = [b for b in state.buildings if b.id != building.id]
    state.stats[killer].enemy_buildings_destroyed += 1
    events.append(SimEvent("building_destroyed", building.side, building.x, building.y, subject=building.type))


def apply_damage(
    state: GameState, target: Unit | Building, amount: float, attacker: Side, events: list[SimEvent]
) -> None:
    target.hp -= amount
    if target.hp > 0:
        return
    if isinstance(target, Unit):
        destroy_unit(state, target, attacker, events)
    else:
        destroy_building(state, target, attacker, events)


def find_enemy(state: GameState, unit: Unit, radius: float) -> Unit | Building | None:
    """Ближайший враг в радиусе: юниты и здания вместе; при равенстве — с меньшим id."""
    best: tuple[float, int] | None = None
    result: Unit | Building | None = None
    for enemy in [*state.units, *state.buildings]:
        if enemy.side == unit.side or enemy.hp <= 0:
            continue
        d = distance(unit.x, unit.y, enemy.x, enemy.y)
        if d <= radius and (best is None or (d, enemy.id) < best):
            best, result = (d, enemy.id), enemy
    return result


def _chase(state: GameState, balance: Balance, unit: Unit, target: Unit | Building) -> None:
    if unit.repath_ms > 0:
        return
    unit.repath_ms = balance.combat.repath_ms
    if isinstance(target, Unit):
        path_unit_to(state, unit, Point(round(target.x), round(target.y)))
    else:
        path_unit_next_to(state, unit, target.x, target.y)


def combat_step(state: GameState, balance: Balance, dt_ms: int, events: list[SimEvent]) -> None:
    for unit in list(state.units):
        spec = balance.units[unit.type]
        if spec.dps <= 0 or unit.hp <= 0:
            continue
        unit.repath_ms = max(0, unit.repath_ms - dt_ms)
        if unit.task not in ("idle", "attacking", "attack_move"):
            continue

        target = entity_by_id(state, unit.target_id)
        if target is not None and (target.hp <= 0 or target.side == unit.side):
            target = None
        if target is None:
            if unit.task == "attacking":
                unit.task = "idle"
            target = find_enemy(state, unit, balance.combat.aggro_radius)
            unit.target_id = target.id if target is not None else None

        if target is None:
            unit.aim = unit.facing
            if unit.task == "attack_move" and unit.attack_point is not None:
                if unit_tile(unit) == unit.attack_point:
                    unit.task = "idle"
                    unit.attack_point = None
                elif unit.repath_ms == 0:
                    unit.repath_ms = balance.combat.repath_ms
                    path_unit_to(state, unit, unit.attack_point)
            continue

        reach = spec.range + (UNIT_REACH if isinstance(target, Unit) else BUILDING_REACH)
        if distance(unit.x, unit.y, target.x, target.y) <= reach:
            unit.path = []
            unit.aim = math.atan2(target.y - unit.y, target.x - unit.x)
            unit.fire_ms += dt_ms
            if unit.fire_ms >= balance.combat.shot_interval_ms:
                unit.fire_ms = 0
                events.append(SimEvent("shot", unit.side, unit.x, unit.y, tx=target.x, ty=target.y))
            apply_damage(state, target, spec.dps * dt_ms / 1000, unit.side, events)
        else:
            _chase(state, balance, unit, target)


def command_attack(state: GameState, balance: Balance, side: Side, unit_ids: list[int], target_id: int) -> CommandResult:
    target = entity_by_id(state, target_id)
    if target is None or target.side == side:
        return CommandResult.failure("Это не враг")
    ordered = 0
    for unit in state.units:
        if unit.side == side and unit.id in unit_ids and is_fighter(balance, unit):
            unit.task = "attacking"
            unit.target_id = target_id
            unit.attack_point = None
            unit.repath_ms = 0
            ordered += 1
    return CommandResult.success() if ordered else CommandResult.failure("Атаковать могут только роверы")


def command_attack_move(state: GameState, balance: Balance, side: Side, unit_ids: list[int], point: Point) -> CommandResult:
    ordered = 0
    for unit in state.units:
        if unit.side == side and unit.id in unit_ids and is_fighter(balance, unit):
            if path_unit_to(state, unit, point):
                unit.task = "attack_move"
                unit.attack_point = point
                unit.target_id = None
                unit.repath_ms = balance.combat.repath_ms
                ordered += 1
    return CommandResult.success() if ordered else CommandResult.failure("Путь не найден")
