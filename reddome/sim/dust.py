"""Пылевой вихрь (ФТ-18, W3-15): нейтральный объект медленно идёт по случайному маршруту
и засыпает солнечные панели обеих сторон, через которые проходит.

Засыпанная панель (Building.dust_ms > 0) выдаёт в сол меньше энергии на dust_devil.solar_penalty
(economy.apply_sol). Маршрут зависит только от seed партии, номера вихря и номера отрезка,
поэтому партия остаётся детерминированной (НФТ-03). Числа — в balance.json → dust_devil.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from reddome.sim.types import Building, DustDevil, GameState, Point, SimEvent

if TYPE_CHECKING:
    from reddome.config.balance import Balance

#: Вихрь не подходит к краю карты ближе чем на столько клеток.
EDGE_MARGIN = 3


def _random_point(state: GameState, number: int, leg: int) -> Point:
    rng = random.Random(f"dust:{state.seed}:{number}:{leg}")
    width, height = state.map.width, state.map.height
    return Point(rng.randint(EDGE_MARGIN, width - 1 - EDGE_MARGIN), rng.randint(EDGE_MARGIN, height - 1 - EDGE_MARGIN))


def next_spawn_ms(state: GameState, balance: Balance) -> int:
    """Когда появится следующий вихрь: первый — через first_sec, дальше — через interval_sec после исчезновения."""
    spec = balance.dust_devil
    cycle = spec.lifetime_sec + spec.interval_sec
    return round((spec.first_sec + state.dust_devils_spawned * cycle) * 1000)


def spawn_dust_devil(state: GameState) -> DustDevil:
    number = state.dust_devils_spawned
    start = _random_point(state, number, 0)
    devil = DustDevil(x=float(start.x), y=float(start.y), target=_random_point(state, number, 1), leg=1, number=number)
    state.dust_devil = devil
    state.dust_devils_spawned += 1
    return devil


def is_dusted(building: Building) -> bool:
    return building.type == "solar" and building.dust_ms > 0


def dust_step(state: GameState, balance: Balance, dt_ms: int, events: list[SimEvent]) -> None:
    spec = balance.dust_devil
    for b in state.buildings:
        if b.dust_ms > 0:
            b.dust_ms = max(0, b.dust_ms - dt_ms)

    devil = state.dust_devil
    if devil is None:
        if state.elapsed_ms >= next_spawn_ms(state, balance):
            spawn_dust_devil(state)
        return

    devil.age_ms += dt_ms
    if devil.age_ms >= spec.lifetime_sec * 1000:
        state.dust_devil = None  # рассеялся
        return

    step = spec.speed * dt_ms / 1000
    dx, dy = devil.target.x - devil.x, devil.target.y - devil.y
    dist = math.hypot(dx, dy)
    if dist <= step:
        devil.x, devil.y = float(devil.target.x), float(devil.target.y)
        devil.leg += 1
        devil.target = _random_point(state, devil.number, devil.leg)
    else:
        devil.x += dx / dist * step
        devil.y += dy / dist * step

    for b in state.buildings:
        if b.type != "solar" or not b.complete or b.hp <= 0:
            continue
        if math.hypot(b.x - devil.x, b.y - devil.y) <= spec.radius:
            if b.dust_ms == 0:
                events.append(SimEvent("panel_dusted", b.side, b.x, b.y, subject=b.type))
            b.dust_ms = round(spec.dust_sec * 1000)
