"""Очки миссии по balance.score (W3-10, ФТ-11, ФТ-12) и зелёная зона экономики."""

from __future__ import annotations

from reddome.config.balance import load_balance
from reddome.sim.economy import is_green
from reddome.sim.score import compute_score
from reddome.sim.simulation import Simulation
from reddome.sim.types import Colony, Outcome


def make_sim() -> Simulation:
    return Simulation(load_balance(), seed=1)


def points(sim: Simulation) -> dict[str, int]:
    return {line.key: line.points for line in compute_score(sim.state, sim.balance).lines}


def test_start_score_counts_only_population() -> None:
    sim = make_sim()
    weights = sim.balance.score
    colonists = sim.balance.start.colonists
    score = compute_score(sim.state, sim.balance)
    assert points(sim) == {"win": 0, "killed_unit": 0, "population": colonists * weights.population,
                           "green_sol": 0, "lost_colonist": 0}
    assert score.total == colonists * weights.population


def test_win_and_kills_add_points() -> None:
    sim = make_sim()
    weights = sim.balance.score
    sim.state.stats["player"].enemy_units_killed = 7
    sim.state.colonies["player"].green_sols = 4
    vector_dome = next(b for b in sim.state.buildings if b.side == "vector" and b.type == "dome")
    sim.damage_building(vector_dome.id, vector_dome.hp)
    assert sim.state.outcome == Outcome(winner="player", reason="dome_destroyed")
    got = points(sim)
    assert got["win"] == weights.win
    assert got["killed_unit"] == 7 * weights.killed_unit
    assert got["green_sol"] == 4 * weights.green_sol
    assert compute_score(sim.state, sim.balance).total == sum(got.values())


def test_lost_dome_means_lost_colonists() -> None:
    sim = make_sim()
    weights = sim.balance.score
    dome = next(b for b in sim.state.buildings if b.side == "player" and b.type == "dome")
    sim.damage_building(dome.id, dome.hp)
    assert sim.state.outcome is not None and sim.state.outcome.winner == "vector"
    got = points(sim)
    assert got["win"] == 0
    assert got["population"] == 0
    assert got["lost_colonist"] == sim.balance.start.colonists * weights.lost_colonist


def test_weights_come_from_balance() -> None:
    sim = make_sim()
    raw = dict(sim.balance.raw)
    raw["score"] = {**raw["score"], "population": 7}
    from reddome.config.balance import balance_from_dict

    sim.balance = balance_from_dict(raw)
    assert points(sim)["population"] == sim.balance.start.colonists * 7


def colony(**resources: int) -> Colony:
    return Colony(side="player", resources={"energy": 100, "water": 100, "oxygen": 100, "metal": 0, **resources},
                  colonists=6)


def test_green_zone_needs_more_than_three_sols_of_stock() -> None:
    c = colony(oxygen=31)
    c.last_delta["oxygen"] = -10
    assert is_green(c)
    c.resources["oxygen"] = 30
    assert not is_green(c)


def test_growing_resource_is_always_green_and_metal_is_ignored() -> None:
    c = colony(water=0, metal=0)
    c.last_delta["water"] = 5
    c.last_delta["metal"] = -100
    assert is_green(c)


def test_green_sols_are_counted_each_sol() -> None:
    sim = make_sim()
    sol_ms = int(sim.balance.sol_seconds * 1000)
    for _ in range(3):
        sim.update(sol_ms)
    colony_state = sim.state.colonies["player"]
    assert sim.state.sol == 3
    assert 0 <= colony_state.green_sols <= 3
