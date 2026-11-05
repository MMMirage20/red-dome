"""Общие помощники тестов."""

from __future__ import annotations

from collections.abc import Callable

from reddome.sim.map import tile_at
from reddome.sim.simulation import TICK_MS, Simulation
from reddome.sim.state import add_unit, building_at, find_free_tile_near, unit_at
from reddome.sim.types import GameState, Point, Side, SimEvent, Unit


def run_until(sim: Simulation, done: Callable[[list[SimEvent]], bool], max_ms: int = 120_000) -> list[SimEvent]:
    """Крутит симуляцию по тику, пока done(события) не станет True; возвращает накопленные события."""
    events: list[SimEvent] = []
    waited = 0
    while not done(events):
        assert waited < max_ms, "условие не выполнилось за отведённое время"
        sim.update(TICK_MS)
        events.extend(sim.drain_events())
        waited += TICK_MS
    return events


def open_spot(state: GameState, near: Point) -> Point:
    """Клетка грунта, у которой все 8 соседей — свободный грунт: удобно ставить здание и строителей вокруг."""
    for r in range(1, 12):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                p = Point(near.x + dx, near.y + dy)
                cells = [Point(p.x + i, p.y + j) for j in (-1, 0, 1) for i in (-1, 0, 1)]
                if all(
                    tile_at(state.map, c.x, c.y) == "ground"
                    and building_at(state, c.x, c.y) is None
                    and unit_at(state, c.x, c.y) is None
                    for c in cells
                ):
                    return p
    raise AssertionError("Не нашлось открытого места")


def neighbors(p: Point) -> list[Point]:
    return [Point(p.x + i, p.y + j) for j in (-1, 0, 1) for i in (-1, 0, 1) if i or j]


def add_rovers(sim: Simulation, side: Side, count: int) -> list[Unit]:
    """Охранные роверы рядом с куполом стороны — без стройки ангара и очереди сборки."""
    base = sim.state.map.bases[side]
    rovers = []
    for _ in range(count):
        spot = find_free_tile_near(sim.state, base)
        assert spot is not None, "у базы нет свободной клетки"
        rovers.append(add_unit(sim.state, sim.balance, side, "guard_rover", spot))
    return rovers
