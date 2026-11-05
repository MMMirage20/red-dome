"""Баланс игры. Все числа живут в balance.json (НФТ-07), здесь только их загрузка и проверка."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reddome.sim.types import BUILDING_TYPES, UNIT_TYPES

BALANCE_PATH = Path(__file__).with_name("balance.json")


@dataclass(frozen=True)
class StartSpec:
    energy: int
    water: int
    oxygen: int
    metal: int
    colonists: int
    drones: int


@dataclass(frozen=True)
class BuildingSpec:
    """Положительные значения ресурсов — выработка за сол, отрицательные — расход."""

    cost: int
    hp: int
    build_time_sec: float = 0
    energy: int = 0
    water: int = 0
    oxygen: int = 0
    metal: int = 0
    supply: int = 0
    colonist_slots: int = 0
    needs: str | None = None


@dataclass(frozen=True)
class UnitSpec:
    cost: int
    hp: int
    speed: float
    supply: int
    build_time_sec: float
    dps: float = 0
    range: float = 0


@dataclass(frozen=True)
class ConsumptionSpec:
    colonist_oxygen: int
    colonist_water: int
    rover_crew_oxygen: int


@dataclass(frozen=True)
class WorkerSpec:
    #: Сколько металла дрон уносит за рейс.
    carry: int
    gather_time_sec: float
    #: Надбавка к грузу при сдаче в запитанный переработчик (0.25 = +25 %).
    refinery_bonus: float
    repair_hp_per_sec: float
    repair_metal_per_100_hp: float


@dataclass(frozen=True)
class DepositSpec:
    #: Запас металла на одном рудном поле.
    ore_amount: int
    #: Сколько дронов одновременно добывают на одном поле.
    max_workers: int


@dataclass(frozen=True)
class ConstructionSpec:
    max_builders: int
    #: Доля металла, которая возвращается при отмене стройки.
    refund_ratio: float
    #: Доля здоровья стройплощадки в начале стройки.
    start_hp_ratio: float


@dataclass(frozen=True)
class ProductionSpec:
    queue_limit: int


@dataclass(frozen=True)
class CombatSpec:
    #: Радиус, в котором юнит сам замечает врага, клетки.
    aggro_radius: float
    #: Как часто пересчитывать путь к движущейся цели, мс.
    repath_ms: int
    #: Как часто показывать выстрел (на урон не влияет), мс.
    shot_interval_ms: int


@dataclass(frozen=True)
class BotSpec:
    think_interval_ms: int
    target_drones: int
    first_wave_sec: float
    wave_interval_sec: float
    wave_size_start: int
    wave_growth: int


@dataclass(frozen=True)
class GestureSpec:
    #: Кадр с меньшей уверенностью не считается и сбрасывает удержание.
    min_score: float
    #: Удержание для выделения, добычи, отступления и сборки.
    hold_ms: int
    #: Удержание для атаки на базу ВЕКТОРа: команда дорогая, держать дольше.
    attack_hold_ms: int
    #: Удержание для паузы.
    pause_hold_ms: int
    #: Пауза после любой сработавшей команды, чтобы одна поза не дала две команды подряд.
    cooldown_ms: int


@dataclass(frozen=True)
class ScoreSpec:
    win: int
    killed_unit: int
    population: int
    green_sol: int
    lost_colonist: int


@dataclass(frozen=True)
class Balance:
    sol_seconds: float
    start: StartSpec
    buildings: dict[str, BuildingSpec]
    consumption: ConsumptionSpec
    units: dict[str, UnitSpec]
    workers: WorkerSpec
    deposit: DepositSpec
    construction: ConstructionSpec
    production: ProductionSpec
    combat: CombatSpec
    bot: BotSpec
    gestures: GestureSpec
    score: ScoreSpec


def balance_from_dict(raw: dict[str, Any]) -> Balance:
    """Собирает Balance из словаря. Лишний или пропущенный ключ сразу даёт понятную ошибку."""
    for section, names in (("buildings", BUILDING_TYPES), ("units", UNIT_TYPES)):
        if set(raw[section]) != set(names):
            raise ValueError(f"balance.json: в разделе {section} ожидаются ключи {sorted(names)}")
    consumption = raw["consumption"]
    return Balance(
        sol_seconds=raw["sol_seconds"],
        start=StartSpec(**raw["start"]),
        buildings={name: BuildingSpec(**spec) for name, spec in raw["buildings"].items()},
        consumption=ConsumptionSpec(
            colonist_oxygen=consumption["colonist"]["oxygen"],
            colonist_water=consumption["colonist"]["water"],
            rover_crew_oxygen=consumption["rover_crew"]["oxygen"],
        ),
        units={name: UnitSpec(**spec) for name, spec in raw["units"].items()},
        workers=WorkerSpec(**raw["workers"]),
        deposit=DepositSpec(**raw["deposit"]),
        construction=ConstructionSpec(**raw["construction"]),
        production=ProductionSpec(**raw["production"]),
        combat=CombatSpec(**raw["combat"]),
        bot=BotSpec(**raw["bot"]),
        gestures=GestureSpec(**raw["gestures"]),
        score=ScoreSpec(**raw["score"]),
    )


def load_balance(path: Path = BALANCE_PATH) -> Balance:
    with path.open(encoding="utf-8") as file:
        return balance_from_dict(json.load(file))
