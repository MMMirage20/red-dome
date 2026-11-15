"""Экономика сола (ФТ-05)."""

from __future__ import annotations

from reddome.config.balance import Balance
from reddome.sim.economy import apply_sol
from reddome.sim.simulation import Simulation
from reddome.sim.state import add_building, create_initial_state
from reddome.sim.types import Point


def sol_ms(balance: Balance) -> float:
    return balance.sol_seconds * 1000


def test_dome_gives_energy_and_colonists_consume(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    sim.update(sol_ms(balance))

    colony = sim.state.colonies["player"]
    metal = balance.side("player").start.metal
    assert sim.state.sol == 1
    assert colony.resources == {"energy": 110, "water": 54, "oxygen": 54, "metal": metal}
    assert colony.last_delta == {"energy": 10, "water": -6, "oxygen": -6, "metal": 0}


def test_energy_shortage_shuts_down_by_priority(balance: Balance) -> None:
    state = create_initial_state(balance, seed=1)
    colony = state.colonies["player"]
    colony.resources["energy"] = 0
    hangar = add_building(state, balance, "player", "hangar", Point(20, 2))
    regolith = add_building(state, balance, "player", "regolith", Point(21, 2))
    drill = add_building(state, balance, "player", "ice_drill", Point(22, 2))
    generator = add_building(state, balance, "player", "oxy_gen", Point(23, 2))

    apply_sol(state, balance, "player")

    assert [hangar.powered, regolith.powered, drill.powered] == [False, False, False]
    assert generator.powered
    assert colony.resources == {"energy": 2, "water": 48, "oxygen": 66, "metal": balance.side("player").start.metal}


def test_oxygen_generator_stops_without_water(balance: Balance) -> None:
    state = create_initial_state(balance, seed=1)
    colony = state.colonies["player"]
    colony.resources["water"] = 0
    generator = add_building(state, balance, "player", "oxy_gen", Point(20, 2))

    apply_sol(state, balance, "player")

    assert not generator.powered
    assert colony.resources["water"] == 0
    assert colony.resources["oxygen"] == 54


def test_oxygen_deficit_longer_than_one_sol_loses(balance: Balance) -> None:
    sim = Simulation(balance, seed=1)
    sim.state.colonies["player"].resources["oxygen"] = 0

    sim.update(sol_ms(balance))
    assert sim.state.colonies["player"].oxygen_deficit_sols == 1
    assert sim.state.outcome is None

    sim.update(sol_ms(balance))
    assert sim.state.outcome is not None
    assert (sim.state.outcome.winner, sim.state.outcome.reason) == ("vector", "oxygen")
