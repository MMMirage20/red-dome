"""Баланс игры. Все числа живут в balance.json (НФТ-07), здесь только их загрузка и проверка."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from reddome.sim.types import BUILDING_TYPES, DIFFICULTIES, UNIT_TYPES, BuildingType, Difficulty, Side

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
    #: Размер первой волны.
    wave_size_start: int
    #: На сколько роверов растёт волна...
    wave_growth: int
    #: ...и раз в сколько волн: при 1 и 2 волны идут 2, 2, 3, 3, 4, 4…
    wave_growth_every: int
    #: Множитель размера волн от сложности. В balance.json его нет: считается при загрузке.
    wave_size_ratio: float = 1.0

    def wave_size(self, n: int) -> int:
        """Сколько роверов уходит в волну номер n (считая с нуля), не меньше одного."""
        base = self.wave_size_start + (n // self.wave_growth_every) * self.wave_growth
        return max(1, math.floor(base * self.wave_size_ratio + 0.5))


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
class PlayerSpec:
    """Фора стороны игрока поверх общих правил (этап 2: миссия 1 для новичка)."""

    start_metal: int
    dome_hp: int


@dataclass(frozen=True)
class DifficultySpec:
    """Множители уровня сложности. У «Обычного» все 1.0 — это числа из остальных разделов balance.json."""

    #: Время до первой волны ВЕКТОРа и интервал между волнами.
    bot_timing: float
    #: Размер волн ВЕКТОРа.
    bot_waves: float
    #: Стартовые ресурсы ВЕКТОРа и металл, который сдают его дроны.
    bot_resources: float
    #: Полное здоровье купола игрока.
    player_dome_hp: float


def _scaled(value: float, ratio: float) -> int:
    """Целое после множителя, с округлением половины вверх (одинаково на любой платформе)."""
    return math.floor(value * ratio + 0.5)


@dataclass(frozen=True)
class SideSpec:
    """Числа, которые у игрока и ВЕКТОРа разные. Считаются один раз при загрузке баланса."""

    start: StartSpec
    dome_hp: int
    #: Множитель металла, который дроны этой стороны сдают на базу.
    income_ratio: float
    #: Настройки бота, если за эту сторону играет бот.
    bot: BotSpec


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
    player: PlayerSpec
    #: Итоговые числа каждой стороны с учётом сложности. Читать через side() и max_hp().
    sides: dict[Side, SideSpec]
    #: Сложность, для которой посчитаны sides.
    difficulty: Difficulty
    #: Множители всех уровней — для выбора в меню и отчётов.
    difficulties: dict[Difficulty, DifficultySpec]
    #: Исходный balance.json: из него пересчитывается баланс другой сложности.
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def side(self, side: Side) -> SideSpec:
        return self.sides[side]

    def max_hp(self, side: Side, type: BuildingType) -> int:
        """Полное здоровье здания: у купола своё для каждой стороны, у остальных зданий — общее."""
        if type == "dome":
            return self.sides[side].dome_hp
        return self.buildings[type].hp

    def with_difficulty(self, difficulty: Difficulty) -> Balance:
        """Тот же balance.json на другом уровне сложности."""
        if difficulty == self.difficulty:
            return self
        return balance_from_dict(self.raw, difficulty)


def side_specs(start: StartSpec, vector_dome_hp: int, bot: BotSpec, player: PlayerSpec, level: DifficultySpec) -> dict[Side, SideSpec]:
    """Единственное место, где множители сложности превращаются в числа партии.

    Сложность меняет только ВЕКТОРа и купол игрока. Сторона игрока остаётся с базовыми числами бота:
    в sim_cli за неё тоже играет бот, и сравнение уровней не должно его менять.
    """
    vector_start = replace(
        start,
        energy=_scaled(start.energy, level.bot_resources),
        water=_scaled(start.water, level.bot_resources),
        oxygen=_scaled(start.oxygen, level.bot_resources),
        metal=_scaled(start.metal, level.bot_resources),
    )
    vector_bot = replace(
        bot,
        first_wave_sec=bot.first_wave_sec * level.bot_timing,
        wave_interval_sec=bot.wave_interval_sec * level.bot_timing,
        wave_size_ratio=level.bot_waves,
    )
    return {
        "player": SideSpec(
            start=replace(start, metal=player.start_metal),
            dome_hp=_scaled(player.dome_hp, level.player_dome_hp),
            income_ratio=1.0,
            bot=bot,
        ),
        "vector": SideSpec(start=vector_start, dome_hp=vector_dome_hp, income_ratio=level.bot_resources, bot=vector_bot),
    }


def balance_from_dict(raw: dict[str, Any], difficulty: str | None = None) -> Balance:
    """Собирает Balance из словаря на уровне сложности difficulty (по умолчанию — difficulty.default).
    Лишний или пропущенный ключ и неизвестная сложность сразу дают понятную ошибку."""
    for section, names in (("buildings", BUILDING_TYPES), ("units", UNIT_TYPES)):
        if set(raw[section]) != set(names):
            raise ValueError(f"balance.json: в разделе {section} ожидаются ключи {sorted(names)}")
    consumption = raw["consumption"]
    start = StartSpec(**raw["start"])
    buildings = {name: BuildingSpec(**spec) for name, spec in raw["buildings"].items()}
    bot = BotSpec(**raw["bot"])
    if bot.wave_growth_every < 1:
        raise ValueError("balance.json: bot.wave_growth_every должен быть не меньше 1")
    player = PlayerSpec(**raw["player"])
    levels = raw["difficulty"]["levels"]
    if set(levels) != set(DIFFICULTIES):
        raise ValueError(f"balance.json: в разделе difficulty.levels ожидаются ключи {list(DIFFICULTIES)}")
    difficulties: dict[Difficulty, DifficultySpec] = {name: DifficultySpec(**levels[name]) for name in DIFFICULTIES}
    level = difficulty or raw["difficulty"]["default"]
    if level not in difficulties:
        raise ValueError(f"Неизвестная сложность {level!r}: есть {', '.join(DIFFICULTIES)}")
    sides = side_specs(start, buildings["dome"].hp, bot, player, difficulties[level])
    return Balance(
        sol_seconds=raw["sol_seconds"],
        start=start,
        buildings=buildings,
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
        bot=bot,
        gestures=GestureSpec(**raw["gestures"]),
        score=ScoreSpec(**raw["score"]),
        player=player,
        sides=sides,
        difficulty=level,
        difficulties=difficulties,
        raw=raw,
    )


def load_balance(path: Path = BALANCE_PATH, difficulty: str | None = None) -> Balance:
    with path.open(encoding="utf-8") as file:
        return balance_from_dict(json.load(file), difficulty)
