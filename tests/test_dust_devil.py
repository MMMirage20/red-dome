"""Пылевой вихрь (W3-15, ФТ-18): появление, детерминированный маршрут, пыль на панелях и потеря энергии."""

from __future__ import annotations

import math

from reddome.config.balance import load_balance
from reddome.sim.dust import dust_step, next_spawn_ms, spawn_dust_devil
from reddome.sim.economy import apply_sol
from reddome.sim.simulation import TICK_MS, Simulation
from reddome.sim.state import add_building
from reddome.sim.types import Point


def make_sim(seed: int = 1) -> Simulation:
    return Simulation(load_balance(), seed=seed)


def test_first_devil_appears_on_schedule() -> None:
    sim = make_sim()
    spec = sim.balance.dust_devil
    sim.update(spec.first_sec * 1000 - TICK_MS)
    assert sim.state.dust_devil is None
    sim.update(2 * TICK_MS)
    assert sim.state.dust_devil is not None
    assert sim.state.dust_devils_spawned == 1


def test_devil_moves_slowly_and_disperses() -> None:
    sim = make_sim()
    spec = sim.balance.dust_devil
    devil = spawn_dust_devil(sim.state)
    x, y = devil.x, devil.y
    dust_step(sim.state, sim.balance, 1000, [])
    assert math.hypot(devil.x - x, devil.y - y) <= spec.speed + 1e-9
    dust_step(sim.state, sim.balance, round(spec.lifetime_sec * 1000), [])
    assert sim.state.dust_devil is None
    # Следующий — не раньше чем через interval_sec после исчезновения.
    assert next_spawn_ms(sim.state, sim.balance) == round(
        (spec.first_sec + spec.lifetime_sec + spec.interval_sec) * 1000)


def test_route_is_deterministic_by_seed() -> None:
    def track(seed: int) -> list[tuple[float, float]]:
        sim = make_sim(seed)
        points = []
        for _ in range(40):
            sim.update(5000)
            d = sim.state.dust_devil
            points.append((round(d.x, 3), round(d.y, 3)) if d else (-1.0, -1.0))
        return points

    assert track(3) == track(3)
    assert track(3) != track(4)


def test_devil_dusts_panel_and_cuts_its_energy() -> None:
    sim = make_sim()
    state, balance = sim.state, sim.balance
    spec = balance.dust_devil
    panel = add_building(state, balance, "player", "solar", Point(20, 20))
    devil = spawn_dust_devil(state)
    devil.x, devil.y, devil.target = 19.0, 20.0, Point(25, 20)
    events: list = []
    dust_step(state, balance, TICK_MS, events)
    assert panel.dust_ms > 0
    assert [e.kind for e in events] == ["panel_dusted"]

    colony = state.colonies["player"]
    before = colony.resources["energy"]
    apply_sol(state, balance, "player")
    dusted_gain = colony.resources["energy"] - before

    panel.dust_ms = 0
    before = colony.resources["energy"]
    apply_sol(state, balance, "player")
    clean_gain = colony.resources["energy"] - before
    lost = round(balance.buildings["solar"].energy * spec.solar_penalty)
    assert clean_gain - dusted_gain == lost


def test_dust_wears_off() -> None:
    sim = make_sim()
    state, balance = sim.state, sim.balance
    panel = add_building(state, balance, "vector", "solar", Point(30, 10))
    panel.dust_ms = 1000
    dust_step(state, balance, 600, [])
    assert panel.dust_ms == 400
    dust_step(state, balance, 600, [])
    assert panel.dust_ms == 0


def test_other_buildings_are_not_dusted() -> None:
    sim = make_sim()
    state, balance = sim.state, sim.balance
    drill = add_building(state, balance, "player", "hangar", Point(20, 20))
    devil = spawn_dust_devil(state)
    devil.x, devil.y = 20.0, 20.0
    dust_step(state, balance, TICK_MS, [])
    assert drill.dust_ms == 0
