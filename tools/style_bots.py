"""Скрипты «игрока» с заданным стилем — для обучения классификатора стиля (этап 3, ФТ-31).

Устав (раздел 4): стиль игрока известен заранее, потому что за игрока играет скрипт. Четыре стиля:
    rush     — ранний ангар, частые атаки охранными роверами;
    turtle   — турели у базы, мало буров, не атакует;
    economy  — много дронов, буров и переработчиков, армии почти нет;
    tech     — ранний реактор и ракетные роверы, атака позже.
У каждой партии свой небольшой разброс от seed: тайминги волн, число дронов и порядок соседних
шагов стройки, чтобы стили не были «нарисованы по линейке».
"""

from __future__ import annotations

import random
from dataclasses import replace
from typing import TYPE_CHECKING

from reddome.bot.bot_v0 import BuildStep
from reddome.bot.strategist import BotStrategist

if TYPE_CHECKING:
    from reddome.config.balance import BotSpec
    from reddome.sim.simulation import Simulation
    from reddome.sim.types import Side

NEVER = 1e6


def _s(kind: str, type_: str, where: str = "") -> BuildStep:
    return BuildStep(kind, type_, where)  # type: ignore[arg-type]


ORDERS: dict[str, tuple[BuildStep, ...]] = {
    "rush": (
        _s("unit", "drone"), _s("building", "hangar"), _s("building", "oxy_gen"), _s("building", "solar"),
        _s("building", "ice_drill", "own"), _s("unit", "drone"), _s("building", "solar"), _s("building", "oxy_gen"),
    ),
    "turtle": (
        _s("unit", "drone"), _s("building", "oxy_gen"), _s("building", "solar"), _s("building", "turret", "base"),
        _s("building", "ice_drill", "own"), _s("building", "turret", "base"), _s("building", "hangar"),
        _s("building", "solar"), _s("building", "turret", "base"), _s("building", "oxy_gen"),
    ),
    "economy": (
        _s("unit", "drone"), _s("unit", "drone"), _s("building", "oxy_gen"), _s("building", "solar"),
        _s("building", "ice_drill", "own"), _s("building", "regolith"), _s("unit", "drone"),
        _s("building", "ice_drill", "own"), _s("building", "solar"), _s("building", "regolith"),
        _s("building", "oxy_gen"),
    ),
    "tech": (
        _s("unit", "drone"), _s("building", "oxy_gen"), _s("building", "solar"), _s("building", "reactor"),
        _s("building", "hangar"), _s("building", "ice_drill", "own"), _s("building", "solar"),
        _s("building", "regolith"),
    ),
}

#: Числа волн и дронов каждого стиля до разброса: (первая волна, с; интервал, с; целевые дроны).
WAVES: dict[str, tuple[float, float, int]] = {
    "rush": (130, 75, 5),
    "turtle": (NEVER, NEVER, 5),
    "economy": (NEVER, NEVER, 9),
    "tech": (310, 120, 6),
}


def _shuffle_neighbors(order: tuple[BuildStep, ...], rng: random.Random, chance: float) -> tuple[BuildStep, ...]:
    """Иногда меняет местами соседние шаги после первого — так игроки одного стиля немного разные."""
    steps = list(order)
    for i in range(1, len(steps) - 1):
        if rng.random() < chance:
            steps[i], steps[i + 1] = steps[i + 1], steps[i]
    return tuple(steps)


class StyleBot(BotStrategist):
    """Игрок со стилем style. Разброс берётся из rng — генератора от seed партии."""

    def __init__(self, style: str, side: Side = "player", base: BotSpec | None = None,
                 rng: random.Random | None = None, jitter: float = 0.2) -> None:
        rng = rng or random.Random(0)
        first, interval, drones = WAVES[style]

        def scale(value: float) -> float:
            return value if value >= NEVER else round(value * rng.uniform(1 - jitter, 1 + jitter), 1)

        params = None
        if base is not None:
            params = replace(base, first_wave_sec=scale(first), wave_interval_sec=scale(interval),
                             target_drones=max(3, drones + rng.choice((-1, 0, 1))))
        super().__init__(side, params)
        self.style = style
        self.build_order = _shuffle_neighbors(ORDERS[style], rng, 0.25 if jitter > 0 else 0.0)
        self.early_fields = style == "economy"

    def _contest_ice(self, sim: Simulation, building_now: set[str]) -> bool:
        if self.style in ("turtle", "rush"):
            return False
        return super()._contest_ice(sim, building_now)

    def _grow(self, sim: Simulation) -> None:
        if self.style == "turtle":
            turrets = len(self._own_buildings(sim, "turret"))
            if turrets < 5 and not any(b.side == self.side and b.type == "turret" and not b.complete
                                       for b in sim.state.buildings):
                if self._try_build(sim, "turret", "base"):
                    return
        if self.style == "economy" and len(self._own_buildings(sim, "ice_drill")) < 3:
            if self._try_build(sim, "ice_drill", "own"):
                return
        super()._grow(sim)

    def train_rover(self, sim: Simulation) -> None:
        if self.style == "economy" and sim.state.elapsed_ms < 360_000:
            return
        if self.style == "tech" and sim.train(self.side, "rocket_rover").ok:
            return
        if self.style == "rush":
            sim.train(self.side, "guard_rover")
            return
        super().train_rover(sim)
