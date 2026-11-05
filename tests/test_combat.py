"""Бой (W3-09): автозахват, атака, атака с движением, разрушение купола."""

from __future__ import annotations

from reddome.config.balance import Balance
from reddome.sim.simulation import Simulation
from reddome.sim.state import add_building, add_unit
from reddome.sim.types import Point
from tests.helpers import neighbors, open_spot, run_until


def test_idle_rover_kills_enemy_drone_in_range(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    spot = open_spot(sim.state, sim.state.map.bases["player"])
    rover = add_unit(sim.state, balance, "player", "guard_rover", spot)
    enemy = add_unit(sim.state, balance, "vector", "drone", neighbors(spot)[0])

    events = run_until(sim, lambda _: enemy not in sim.state.units, max_ms=10_000)

    assert any(e.kind == "unit_destroyed" and e.side == "vector" for e in events)
    assert any(e.kind == "shot" and e.side == "player" for e in events)
    assert sim.state.stats["player"].enemy_units_killed == 1
    assert sim.state.stats["vector"].units_lost == 1
    assert rover.hp == balance.units["guard_rover"].hp


def test_attack_order_destroys_building(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    spot = open_spot(sim.state, sim.state.map.bases["player"])
    rover = add_unit(sim.state, balance, "player", "guard_rover", spot)
    target = add_building(sim.state, balance, "vector", "solar", Point(spot.x + 3, spot.y))

    assert sim.attack("player", [rover.id], target.id).ok
    events = run_until(sim, lambda _: target not in sim.state.buildings, max_ms=60_000)

    assert any(e.kind == "building_destroyed" and e.subject == "solar" for e in events)
    sim.update(100)  # цель пропала — на следующем тике ровер возвращается в idle
    assert rover.task == "idle"


def test_moving_rover_ignores_enemies(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    spot = open_spot(sim.state, sim.state.map.bases["player"])
    rover = add_unit(sim.state, balance, "player", "guard_rover", spot)
    enemy = add_unit(sim.state, balance, "vector", "drone", neighbors(spot)[0])
    back = sim.state.map.bases["player"]

    assert sim.move("player", [rover.id], Point(back.x + 1, back.y)).ok
    sim.update(1_000)

    assert enemy.hp == balance.units["drone"].hp


def test_attack_move_engages_on_the_way(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    spot = open_spot(sim.state, sim.state.map.bases["player"])
    rover = add_unit(sim.state, balance, "player", "guard_rover", spot)
    enemy = add_unit(sim.state, balance, "vector", "drone", Point(spot.x + 2, spot.y))
    point = Point(spot.x, spot.y - 1)

    assert sim.attack_move("player", [rover.id], point).ok
    run_until(sim, lambda _: enemy not in sim.state.units and rover.task == "idle", max_ms=30_000)

    assert (round(rover.x), round(rover.y)) == (point.x, point.y)


def test_destroying_dome_ends_the_game(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    dome = next(b for b in sim.state.buildings if b.side == "vector" and b.type == "dome")
    rovers = []
    for p in neighbors(Point(dome.x, dome.y)):
        if sim.state.map.tiles[p.y * sim.state.map.width + p.x] != "rock":
            rovers.append(add_unit(sim.state, balance, "player", "guard_rover", p))
    assert sim.attack("player", [r.id for r in rovers], dome.id).ok

    run_until(sim, lambda _: sim.state.outcome is not None, max_ms=300_000)

    assert sim.state.outcome is not None
    assert (sim.state.outcome.winner, sim.state.outcome.reason) == ("player", "dome_destroyed")
