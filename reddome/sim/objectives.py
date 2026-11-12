"""Цели миссий этапа 3 (ФТ-24, ФТ-27): удержание ледяных полей и Большой купол.

Поле держит сторона, у которой на нём есть готовый бур, а у соперника нет. В конце каждого сола
счётчик ice_hold_sols стороны растёт, если она держит не меньше hold_fields полей, иначе сбрасывается.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from reddome.sim.types import SIDES, GameState, OutcomeReason, Point, Side

if TYPE_CHECKING:
    from reddome.config.balance import Balance, MissionSpec


def drills_on(state: GameState, field: list[Point], side: Side) -> int:
    tiles = set(field)
    return sum(
        1
        for b in state.buildings
        if b.side == side and b.type == "ice_drill" and b.complete and b.hp > 0 and Point(b.x, b.y) in tiles
    )


def field_owner(state: GameState, field: list[Point]) -> Side | None:
    player, vector = drills_on(state, field, "player"), drills_on(state, field, "vector")
    if player and not vector:
        return "player"
    if vector and not player:
        return "vector"
    return None


def field_of(state: GameState, x: int, y: int) -> int | None:
    """Номер ледяного поля, которому принадлежит клетка."""
    p = Point(x, y)
    return next((i for i, field in enumerate(state.map.ice_fields) if p in field), None)


def fields_held(state: GameState, side: Side) -> int:
    return sum(1 for field in state.map.ice_fields if field_owner(state, field) == side)


def update_ice_hold(state: GameState, mission: MissionSpec) -> None:
    """Вызывается в конце сола."""
    for side in SIDES:
        if fields_held(state, side) >= mission.hold_fields:
            state.ice_hold_sols[side] += 1
        else:
            state.ice_hold_sols[side] = 0


def great_dome_progress(state: GameState, side: Side) -> float | None:
    """Прогресс Большого купола стороны от 0 до 1; None — стройка не начата."""
    dome = next((b for b in state.buildings if b.side == side and b.type == "great_dome"), None)
    return None if dome is None else dome.build_progress


def mission_winner(state: GameState, balance: Balance) -> tuple[Side, OutcomeReason] | None:
    """Победа по цели миссии (а не по разрушенному куполу): (сторона, причина)."""
    mission = balance.mission(state.mission)
    for side in SIDES:
        if mission.goal == "hold_ice" and state.ice_hold_sols[side] >= mission.hold_sols:
            return side, "ice_held"
        if mission.goal == "great_dome" and any(
            b.side == side and b.type == "great_dome" and b.complete and b.hp > 0 for b in state.buildings
        ):
            return side, "great_dome"
    return None
