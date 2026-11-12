"""События среды этапа 3: глобальная буря (ФТ-25), метеориты (ФТ-28) и вспышки на Солнце (ФТ-29).

Буря и вспышка идут по расписанию: первая — через first_sec, следующие — каждые interval_sec от начала
предыдущей, длятся duration_sec, а за warning_sec до начала приходит предупреждение. Место удара
метеорита зависит только от seed партии, номера метеорита и состояния мира, поэтому партия
детерминирована (НФТ-10). Миссия включает события списком events в balance.json → missions.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from reddome.sim.combat import apply_damage
from reddome.sim.map import in_bounds
from reddome.sim.state import distance
from reddome.sim.types import GameState, Meteor, Point, SimEvent, Side

if TYPE_CHECKING:
    from reddome.config.balance import Balance, MissionSpec


def _phase(elapsed_ms: int, first_sec: float, interval_sec: float, duration_sec: float) -> tuple[bool, int]:
    """(идёт ли событие сейчас, мс до начала следующего)."""
    first, period, duration = round(first_sec * 1000), round(interval_sec * 1000), round(duration_sec * 1000)
    if elapsed_ms < first:
        return False, first - elapsed_ms
    into = (elapsed_ms - first) % period
    return into < duration, period - into


def storm_phase(state: GameState, balance: Balance) -> tuple[bool, int]:
    spec = balance.storm
    return _phase(state.elapsed_ms, spec.first_sec, spec.interval_sec, spec.duration_sec)


def flare_phase(state: GameState, balance: Balance) -> tuple[bool, int]:
    spec = balance.solar_flare
    return _phase(state.elapsed_ms, spec.first_sec, spec.interval_sec, spec.duration_sec)


def _warn_now(active: bool, until_ms: int, warning_sec: float, dt_ms: int) -> bool:
    """Предупреждение приходит в тот тик, когда до начала остаётся warning_sec."""
    warning = round(warning_sec * 1000)
    return not active and until_ms <= warning < until_ms + dt_ms


def meteor_impact_ms(balance: Balance, number: int) -> int:
    spec = balance.meteors
    return round((spec.first_sec + number * spec.interval_sec) * 1000)


def _meteor_spot(state: GameState, balance: Balance, number: int) -> Point:
    """Часть метеоритов падает рядом со зданием любой стороны, остальные — в случайную клетку карты."""
    rng = random.Random(f"meteor:{state.seed}:{number}")
    targets = sorted((b for b in state.buildings if b.hp > 0), key=lambda b: b.id)
    if targets and rng.random() < balance.meteors.aim_at_buildings:
        b = targets[rng.randrange(len(targets))]
        spot = Point(b.x + rng.randint(-1, 1), b.y + rng.randint(-1, 1))
        if in_bounds(state.map, spot.x, spot.y):
            return spot
    return Point(rng.randrange(state.map.width), rng.randrange(state.map.height))


def _strike(state: GameState, balance: Balance, meteor: Meteor, events: list[SimEvent]) -> None:
    spec = balance.meteors
    events.append(SimEvent("meteor_impact", "player", meteor.x, meteor.y, value=round(spec.damage)))
    for target in [*state.units, *state.buildings]:
        if target.hp > 0 and distance(target.x, target.y, meteor.x, meteor.y) <= spec.radius:
            apply_damage(state, target, spec.damage, None, events)


def meteors_step(state: GameState, balance: Balance, dt_ms: int, events: list[SimEvent]) -> None:
    warning = round(balance.meteors.warning_sec * 1000)
    while meteor_impact_ms(balance, state.meteors_spawned) - warning <= state.elapsed_ms:
        number = state.meteors_spawned
        spot = _meteor_spot(state, balance, number)
        meteor = Meteor(spot.x, spot.y, meteor_impact_ms(balance, number), number)
        state.meteors.append(meteor)
        state.meteors_spawned += 1
        events.append(SimEvent("meteor_warning", "player", spot.x, spot.y))
    for meteor in [m for m in state.meteors if m.impact_ms <= state.elapsed_ms]:
        state.meteors.remove(meteor)
        _strike(state, balance, meteor, events)


def storm_step(state: GameState, balance: Balance, dt_ms: int, events: list[SimEvent]) -> None:
    active, until_ms = storm_phase(state, balance)
    if _warn_now(active, until_ms, balance.storm.warning_sec, dt_ms):
        events.append(SimEvent("storm_warning", "player", 0, 0, value=round(balance.storm.warning_sec)))
    if active != state.storm_active:
        state.storm_active = active
        events.append(SimEvent("storm_start" if active else "storm_end", "player", 0, 0))


def in_shelter(state: GameState, balance: Balance, x: float, y: float, side: Side) -> bool:
    """Укрытие от вспышки — рядом со своим командным куполом."""
    dome = next((b for b in state.buildings if b.side == side and b.type == "dome"), None)
    return dome is not None and distance(x, y, dome.x, dome.y) <= balance.solar_flare.shelter_radius


def flare_step(state: GameState, balance: Balance, dt_ms: int, events: list[SimEvent]) -> None:
    spec = balance.solar_flare
    active, until_ms = flare_phase(state, balance)
    if _warn_now(active, until_ms, spec.warning_sec, dt_ms):
        events.append(SimEvent("flare_warning", "player", 0, 0, value=round(spec.warning_sec)))
    if active != state.flare_active:
        state.flare_active = active
        events.append(SimEvent("flare_start" if active else "flare_end", "player", 0, 0))
    if not active:
        return
    for unit in list(state.units):
        if balance.units[unit.type].dps > 0 and not in_shelter(state, balance, unit.x, unit.y, unit.side):
            apply_damage(state, unit, spec.damage_per_sec * dt_ms / 1000, None, events)


def hazards_step(state: GameState, balance: Balance, mission: MissionSpec, dt_ms: int, events: list[SimEvent]) -> None:
    if mission.has_event("storm"):
        storm_step(state, balance, dt_ms, events)
    if mission.has_event("meteors"):
        meteors_step(state, balance, dt_ms, events)
    if mission.has_event("solar_flare"):
        flare_step(state, balance, dt_ms, events)
