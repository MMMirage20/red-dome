"""Экономика одного сола (ФТ-05) и лимит армии.

Металл раз в сол не начисляется: его добывают дроны (sim/workers.py).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from reddome.sim.types import RESOURCE_KEYS, Building, BuildingType, Colony, GameState, ResourceKey, Side

if TYPE_CHECKING:
    from reddome.config.balance import Balance, BuildingSpec

#: Ресурсы «зелёной зоны» (очки, W3-10). Металл не входит: его приносят дроны, а не здания раз в сол.
GREEN_RESOURCES: tuple[ResourceKey, ...] = ("energy", "water", "oxygen")
#: Зелёная зона — запаса хватает больше чем на столько солов (ГКД в docs/charter.md).
GREEN_SOLS_AHEAD = 3

#: Порядок отключения потребителей при нехватке энергии. Купол не отключается никогда.
ENERGY_SHUTDOWN_ORDER: tuple[BuildingType, ...] = ("hangar", "regolith", "ice_drill", "oxy_gen")


def alive_buildings(state: GameState, side: Side) -> list[Building]:
    """Готовые здания стороны. Стройплощадки не производят и не тратят ресурсы."""
    return [b for b in state.buildings if b.side == side and b.hp > 0 and b.complete]


def shutdown_candidates(buildings: list[Building]) -> list[Building]:
    """Потребители по ENERGY_SHUTDOWN_ORDER; внутри типа — с последнего построенного."""
    ordered: list[Building] = []
    for type_ in ENERGY_SHUTDOWN_ORDER:
        ordered.extend(sorted((b for b in buildings if b.type == type_), key=lambda b: -b.id))
    return ordered


def supply_cap(state: GameState, balance: Balance, side: Side) -> int:
    return sum(
        balance.buildings[b.type].supply
        for b in alive_buildings(state, side)
        if b.powered or b.type == "dome"
    )


def supply_used(state: GameState, balance: Balance, side: Side) -> int:
    return sum(balance.units[u.type].supply for u in state.units if u.side == side and u.hp > 0)


def supply_reserved(state: GameState, balance: Balance, side: Side) -> int:
    """Лимит, занятый юнитами в очередях сборки."""
    return sum(
        balance.units[item.type].supply
        for b in state.buildings
        if b.side == side
        for item in b.queue
    )


def is_green(colony: Colony) -> bool:
    """Сол в зелёной зоне: каждого ресурса из GREEN_RESOURCES хватит больше чем на GREEN_SOLS_AHEAD солов
    при расходе последнего сола. Ресурс, который за сол не убыл, хватает всегда."""
    for key in GREEN_RESOURCES:
        loss = -colony.last_delta[key]
        if loss > 0 and colony.resources[key] <= loss * GREEN_SOLS_AHEAD:
            return False
    return True


def apply_sol(state: GameState, balance: Balance, side: Side) -> None:
    """Один сол для стороны:
    1) энергия — при нехватке потребители отключаются по ENERGY_SHUTDOWN_ORDER;
    2) вода — при нехватке отключаются генераторы кислорода;
    3) кислород — дышат колонисты и экипажи роверов, при нехватке растёт счётчик дефицита.
    """
    colony = state.colonies[side]
    before = dict(colony.resources)
    buildings = alive_buildings(state, side)

    def spec(b: Building) -> BuildingSpec:
        return balance.buildings[b.type]

    for b in buildings:
        b.powered = True

    # 1. Энергия. Панель, засыпанная пылевым вихрем (sim/dust.py), выдаёт меньше.
    def energy_output(b: Building) -> int:
        dusted = b.type == "solar" and b.dust_ms > 0
        return round(spec(b).energy * (1 - balance.dust_devil.solar_penalty)) if dusted else spec(b).energy

    energy_produced = sum(energy_output(b) for b in buildings if spec(b).energy > 0)

    def energy_consumed() -> int:
        return sum(-spec(b).energy for b in buildings if b.powered and spec(b).energy < 0)

    for candidate in shutdown_candidates(buildings):
        if colony.resources["energy"] + energy_produced - energy_consumed() >= 0:
            break
        candidate.powered = False
    colony.resources["energy"] += energy_produced - energy_consumed()

    def powered(type_: BuildingType) -> list[Building]:
        return [b for b in buildings if b.powered and b.type == type_]

    # 2. Вода
    water_produced = sum(spec(b).water for b in powered("ice_drill"))
    colonist_water = colony.colonists * abs(balance.consumption.colonist_water)
    water_available = colony.resources["water"] + water_produced - colonist_water
    for generator in sorted(powered("oxy_gen"), key=lambda b: b.id):
        need = abs(spec(generator).water)
        if water_available >= need:
            water_available -= need
        else:
            generator.powered = False
    colony.resources["water"] = max(0, water_available)

    # 3. Кислород
    oxygen_produced = sum(spec(b).oxygen for b in powered("oxy_gen"))
    rovers = sum(1 for u in state.units if u.side == side and u.hp > 0 and u.type == "guard_rover")
    oxygen_consumed = colony.colonists * abs(balance.consumption.colonist_oxygen) + rovers * abs(
        balance.consumption.rover_crew_oxygen
    )
    oxygen_left = colony.resources["oxygen"] + oxygen_produced - oxygen_consumed
    colony.oxygen_deficit_sols = colony.oxygen_deficit_sols + 1 if oxygen_left < 0 else 0
    colony.resources["oxygen"] = max(0, oxygen_left)

    before["metal"] = colony.sol_start_metal
    for key in RESOURCE_KEYS:
        colony.last_delta[key] = colony.resources[key] - before[key]
    colony.sol_start_metal = colony.resources["metal"]
    if is_green(colony):
        colony.green_sols += 1
