"""Детерминизм, движение юнитов, победа и поражение."""

from __future__ import annotations

from dataclasses import asdict

from reddome.config.balance import Balance
from reddome.sim.simulation import Simulation
from reddome.sim.types import Point


def run_scripted(balance: Balance, seed: int) -> Simulation:
    sim = Simulation(balance, seed)
    drone = next(u for u in sim.state.units if u.side == "player")
    base = sim.state.map.bases["player"]
    sim.move("player", [drone.id], Point(base.x + 2, base.y - 2))
    # Шаг 16 мс не кратен шагу логики 100 мс: накопление времени не должно ломать детерминизм.
    for _ in range(2500):
        sim.update(16)
    return sim


def test_same_seed_and_commands_give_same_game(balance: Balance) -> None:
    assert asdict(run_scripted(balance, 42).state) == asdict(run_scripted(balance, 42).state)


def test_unit_reaches_target(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    drone = next(u for u in sim.state.units if u.side == "player")
    base = sim.state.map.bases["player"]
    # Клетка внутри расчищенного круга вокруг базы — гарантированно не скала.
    target = Point(base.x + 2, base.y - 2)

    assert sim.move("player", [drone.id], target).ok
    sim.update(10_000)

    assert (drone.x, drone.y) == (target.x, target.y)
    assert drone.path == []


def test_destroyed_dome_means_victory_for_opponent(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    dome = next(b for b in sim.state.buildings if b.side == "vector" and b.type == "dome")

    sim.damage_building(dome.id, dome.hp)

    assert sim.state.outcome is not None
    assert (sim.state.outcome.winner, sim.state.outcome.reason) == ("player", "dome_destroyed")


def test_time_stops_after_game_over(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    dome = next(b for b in sim.state.buildings if b.side == "player" and b.type == "dome")
    sim.damage_building(dome.id, dome.hp)
    tick = sim.state.tick

    sim.update(5_000)

    assert sim.state.tick == tick
