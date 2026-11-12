"""Баланс игры. Все числа живут в balance.json (НФТ-07), здесь только их загрузка и проверка."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from reddome.sim.types import (
    BUILDING_TYPES,
    DIFFICULTIES,
    MISSIONS,
    UNIT_TYPES,
    BuildingType,
    Difficulty,
    Side,
    UnitType,
)

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
    #: Турель (этап 3): урон в секунду и дальность в клетках.
    dps: float = 0
    range: float = 0
    #: Одно такое здание на сторону (Большой купол).
    unique: bool = False


@dataclass(frozen=True)
class UnitSpec:
    cost: int
    hp: int
    speed: float
    supply: int
    build_time_sec: float
    dps: float = 0
    range: float = 0
    #: Множитель урона по зданиям (ракетный ровер бьёт постройки сильнее).
    building_damage: float = 1.0
    #: Готовое здание, без которого юнит не собрать (ракетному роверу нужен реактор).
    requires: str | None = None


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
    #: На сколько роверов волна растёт за один шаг роста.
    wave_growth: int
    #: Раз в сколько волн делается шаг роста. Старт 2, рост 1, каждые 2 волны: 2, 2, 3, 3, 4, 4…
    wave_growth_every: int
    #: Боты этапа 3 («Стратег», «Адаптивный»): когда занимать центральное ледяное поле и поле соперника, с.
    center_from_sec: float = 240
    enemy_field_from_sec: float = 480
    #: Если соперник держит ледяные поля столько солов подряд, волна уходит сразу, не дожидаясь таймера.
    rush_hold_sols: int = 3
    #: «Адаптивный»: с какой секунды классифицировать стиль соперника и когда строить Большой купол.
    classify_from_sec: float = 180
    great_dome_from_sec: float = 600
    #: Множитель размера волн от сложности. В balance.json его нет: считается при загрузке.
    wave_size_ratio: float = 1.0

    def wave_size(self, n: int) -> int:
        """Сколько роверов уходит в волну номер n (считая с нуля), не меньше одного."""
        base = self.wave_size_start + (n // self.wave_growth_every) * self.wave_growth
        return max(1, math.floor(base * self.wave_size_ratio + 0.5))


@dataclass(frozen=True)
class DustDevilSpec:
    """Пылевой вихрь (ФТ-18, W3-15): нейтральный объект, засыпает солнечные панели на своём пути."""

    #: Когда появляется первый вихрь и через сколько после исчезновения — следующий, с.
    first_sec: float
    interval_sec: float
    #: Сколько вихрь живёт, прежде чем рассеяться, с.
    lifetime_sec: float
    #: Скорость, клеток в секунду.
    speed: float
    #: Радиус, в котором вихрь засыпает панели, клеток.
    radius: float
    #: Доля выработки, которую теряет засыпанная панель (0,5 — половину).
    solar_penalty: float
    #: Сколько панель остаётся засыпанной после прохода вихря, с.
    dust_sec: float


@dataclass(frozen=True)
class StormSpec:
    """Глобальная пылевая буря (этап 3, ФТ-25): солнечные панели обеих сторон почти не работают."""

    first_sec: float
    interval_sec: float
    duration_sec: float
    #: За сколько секунд до начала предупредить игрока.
    warning_sec: float
    #: Доля выработки, которую теряют панели во время бури.
    solar_penalty: float


@dataclass(frozen=True)
class MeteorSpec:
    """Метеориты (миссия 3, ФТ-28)."""

    first_sec: float
    interval_sec: float
    #: Метка на земле появляется за столько секунд до удара.
    warning_sec: float
    radius: float
    damage: float
    #: Доля метеоритов, которые падают рядом с каким-нибудь зданием (иначе — в случайную клетку).
    aim_at_buildings: float


@dataclass(frozen=True)
class FlareSpec:
    """Вспышка на Солнце (миссия 3, ФТ-29): роверы вне укрытия получают урон от радиации."""

    first_sec: float
    interval_sec: float
    duration_sec: float
    warning_sec: float
    #: Укрытие — не дальше стольких клеток от своего командного купола.
    shelter_radius: float
    damage_per_sec: float


#: Цели миссий: разрушить купол, удержать ледяные поля, первым построить Большой купол.
GOALS = ("destroy_dome", "hold_ice", "great_dome")
#: Боты ВЕКТОРа (устав, раздел 4): v0 «Новичок», «Стратег», «Адаптивный» с классификатором стиля.
BOT_KINDS = ("novice", "strategist", "adaptive")
#: События среды, которые миссия может включить.
EVENT_KINDS = ("dust_devil", "storm", "meteors", "solar_flare")


@dataclass(frozen=True)
class MissionSpec:
    """Состав миссии (этап 3, ФТ-19): что можно строить и собирать, какой бот, какая цель и события."""

    number: int
    title: str
    buildings: tuple[BuildingType, ...]
    units: tuple[UnitType, ...]
    bot: str
    goal: str
    events: tuple[str, ...]
    #: Запас руды на поле, если в миссии он другой (миссия 2: ближние месторождения беднее).
    ore_amount: int | None = None
    #: Миссия 2: сколько ледяных полей держать и сколько солов подряд.
    hold_fields: int = 0
    hold_sols: int = 0

    def allows_building(self, type: str) -> bool:
        return type == "dome" or type in self.buildings

    def allows_unit(self, type: str) -> bool:
        return type in self.units

    def has_event(self, kind: str) -> bool:
        return kind in self.events


def _mission_from_dict(number: int, raw: dict[str, Any]) -> MissionSpec:
    spec = MissionSpec(
        number=number,
        title=raw["title"],
        buildings=tuple(raw["buildings"]),
        units=tuple(raw["units"]),
        bot=raw["bot"],
        goal=raw["goal"],
        events=tuple(raw.get("events", ())),
        ore_amount=raw.get("ore_amount"),
        hold_fields=raw.get("hold_fields", 0),
        hold_sols=raw.get("hold_sols", 0),
    )
    where = f"balance.json: missions.{number}"
    unknown = [b for b in spec.buildings if b not in BUILDING_TYPES or b == "dome"]
    unknown += [u for u in spec.units if u not in UNIT_TYPES]
    unknown += [e for e in spec.events if e not in EVENT_KINDS]
    if unknown:
        raise ValueError(f"{where}: неизвестные названия {unknown}")
    if spec.bot not in BOT_KINDS:
        raise ValueError(f"{where}: bot должен быть одним из {list(BOT_KINDS)}")
    if spec.goal not in GOALS:
        raise ValueError(f"{where}: goal должен быть одним из {list(GOALS)}")
    if spec.goal == "hold_ice" and (spec.hold_fields < 1 or spec.hold_sols < 1):
        raise ValueError(f"{where}: для цели hold_ice нужны hold_fields и hold_sols")
    if spec.goal == "great_dome" and "great_dome" not in spec.buildings:
        raise ValueError(f"{where}: для цели great_dome Большой купол должен быть в buildings")
    return spec


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
    dust_devil: DustDevilSpec
    storm: StormSpec
    meteors: MeteorSpec
    solar_flare: FlareSpec
    #: Миссии кампании по номеру (этап 3).
    missions: dict[int, MissionSpec]
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

    def mission(self, number: int) -> MissionSpec:
        try:
            return self.missions[number]
        except KeyError:
            raise ValueError(f"Неизвестная миссия {number}: есть {sorted(self.missions)}") from None

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
        center_from_sec=bot.center_from_sec * level.bot_timing,
        enemy_field_from_sec=bot.enemy_field_from_sec * level.bot_timing,
        great_dome_from_sec=bot.great_dome_from_sec * level.bot_timing,
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
    if set(raw["missions"]) != {str(n) for n in MISSIONS}:
        raise ValueError(f"balance.json: в разделе missions ожидаются ключи {[str(n) for n in MISSIONS]}")
    missions = {n: _mission_from_dict(n, raw["missions"][str(n)]) for n in MISSIONS}
    units = {name: UnitSpec(**spec) for name, spec in raw["units"].items()}
    for name, unit in units.items():
        if unit.requires is not None and unit.requires not in BUILDING_TYPES:
            raise ValueError(f"balance.json: units.{name}.requires — неизвестное здание {unit.requires!r}")
    return Balance(
        sol_seconds=raw["sol_seconds"],
        start=start,
        buildings=buildings,
        consumption=ConsumptionSpec(
            colonist_oxygen=consumption["colonist"]["oxygen"],
            colonist_water=consumption["colonist"]["water"],
            rover_crew_oxygen=consumption["rover_crew"]["oxygen"],
        ),
        units=units,
        workers=WorkerSpec(**raw["workers"]),
        deposit=DepositSpec(**raw["deposit"]),
        construction=ConstructionSpec(**raw["construction"]),
        production=ProductionSpec(**raw["production"]),
        combat=CombatSpec(**raw["combat"]),
        bot=bot,
        gestures=GestureSpec(**raw["gestures"]),
        score=ScoreSpec(**raw["score"]),
        dust_devil=DustDevilSpec(**raw["dust_devil"]),
        storm=StormSpec(**raw["storm"]),
        meteors=MeteorSpec(**raw["meteors"]),
        solar_flare=FlareSpec(**raw["solar_flare"]),
        missions=missions,
        player=player,
        sides=sides,
        difficulty=level,
        difficulties=difficulties,
        raw=raw,
    )


def load_balance(path: Path = BALANCE_PATH, difficulty: str | None = None) -> Balance:
    with path.open(encoding="utf-8") as file:
        return balance_from_dict(json.load(file), difficulty)
