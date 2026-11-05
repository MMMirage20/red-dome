"""Приказ на движение и движение юнитов по пути (ФТ-07)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from reddome.sim.pathfinding import find_path
from reddome.sim.state import is_blocked, unit_tile
from reddome.sim.types import CommandResult, GameState, Point, Side

if TYPE_CHECKING:
    from reddome.config.balance import Balance


def command_move(state: GameState, side: Side, unit_ids: list[int], target: Point) -> CommandResult:
    """Каждому выбранному юниту стороны строится путь A* до цели. Прежняя задача отменяется."""
    if is_blocked(state, target.x, target.y):
        return CommandResult.failure("Туда не пройти")

    def blocked(x: int, y: int) -> bool:
        return is_blocked(state, x, y)

    moved = 0
    for unit in state.units:
        if unit.side != side or unit.id not in unit_ids:
            continue
        path = find_path(state.map, blocked, unit_tile(unit), target)
        if path is not None:
            unit.path = path
            unit.task = "moving"
            unit.target_id = None
            unit.attack_point = None
            unit.work_ms = 0
            moved += 1
    return CommandResult.success() if moved else CommandResult.failure("Путь не найден")


def move_units(state: GameState, balance: Balance, dt_sec: float) -> None:
    """Движение по пути со скоростью из balance (клеток в секунду); facing — направление корпуса."""
    for unit in state.units:
        budget = balance.units[unit.type].speed * dt_sec
        while budget > 0 and unit.path:
            nxt = unit.path[0]
            dx, dy = nxt.x - unit.x, nxt.y - unit.y
            dist = math.hypot(dx, dy)
            if dist > 0:
                unit.facing = math.atan2(dy, dx)
            if dist <= budget:
                unit.x, unit.y = float(nxt.x), float(nxt.y)
                unit.path.pop(0)
                budget -= dist
            else:
                unit.x += dx / dist * budget
                unit.y += dy / dist * budget
                budget = 0
