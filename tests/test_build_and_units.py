"""Строительство (ФТ-06), сборка юнитов и лимит армии (ФТ-08)."""

from __future__ import annotations

from reddome.config.balance import Balance
from reddome.sim.build import can_place
from reddome.sim.economy import supply_cap, supply_used
from reddome.sim.simulation import Simulation
from reddome.sim.state import add_building, building_at, find_free_tile_near, unit_at
from reddome.sim.types import CommandResult, GameState, Point, TileKind


def first_free_tile(state: GameState, kind: TileKind) -> Point:
    game_map = state.map
    for y in range(game_map.height):
        for x in range(game_map.width):
            free = building_at(state, x, y) is None and unit_at(state, x, y) is None
            if game_map.tiles[y * game_map.width + x] == kind and free:
                return Point(x, y)
    raise AssertionError(f"На карте нет свободной клетки {kind}")


def test_ice_drill_only_on_ice(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    ground = first_free_tile(sim.state, "ground")
    ice = first_free_tile(sim.state, "ice")

    assert can_place(sim.state, balance, "player", "ice_drill", ground.x, ground.y) == CommandResult.failure(
        "Бур ставится только на ледяное поле"
    )
    assert can_place(sim.state, balance, "player", "ice_drill", ice.x, ice.y).ok


def test_building_costs_metal(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    spot = find_free_tile_near(sim.state, sim.state.map.bases["player"])
    assert spot is not None

    result = sim.build("player", "solar", spot.x, spot.y)

    assert result.ok
    start_metal = sim.balance.side("player").start.metal
    assert sim.state.colonies["player"].resources["metal"] == start_metal - balance.buildings["solar"].cost
    site = next(b for b in sim.state.buildings if b.type == "solar" and b.side == "player")
    assert not site.complete


def test_cannot_build_without_metal(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    sim.state.colonies["player"].resources["metal"] = 10
    spot = find_free_tile_near(sim.state, sim.state.map.bases["player"])
    assert spot is not None

    assert sim.build("player", "solar", spot.x, spot.y) == CommandResult.failure("Не хватает металла")


def test_rover_needs_hangar(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    assert sim.train("player", "guard_rover") == CommandResult.failure("Нужен ангар")


def test_oxygen_sets_army_limit(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    spot = find_free_tile_near(sim.state, sim.state.map.bases["player"])
    assert spot is not None
    add_building(sim.state, balance, "player", "hangar", spot)

    cap = balance.buildings["dome"].supply
    used = balance.side("player").start.drones
    assert supply_cap(sim.state, balance, "player") == cap
    assert supply_used(sim.state, balance, "player") == used
    for _ in range(cap - used):
        assert sim.train("player", "guard_rover").ok
    assert sim.train("player", "guard_rover") == CommandResult.failure("Нужен генератор кислорода")
