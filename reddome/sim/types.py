"""Типы состояния игры."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Side = Literal["player", "vector"]
SIDES: tuple[Side, ...] = ("player", "vector")

#: Уровни сложности партии (этап 2). Множители каждого — в balance.json → difficulty.
Difficulty = Literal["easy", "normal", "hard"]
DIFFICULTIES: tuple[Difficulty, ...] = ("easy", "normal", "hard")

ResourceKey = Literal["energy", "water", "oxygen", "metal"]
RESOURCE_KEYS: tuple[ResourceKey, ...] = ("energy", "water", "oxygen", "metal")

BuildingType = Literal["dome", "solar", "ice_drill", "oxy_gen", "regolith", "hangar"]
BUILDING_TYPES: tuple[BuildingType, ...] = ("dome", "solar", "ice_drill", "oxy_gen", "regolith", "hangar")

UnitType = Literal["drone", "guard_rover"]
UNIT_TYPES: tuple[UnitType, ...] = ("drone", "guard_rover")

TileKind = Literal["ground", "ice", "ore", "rock"]

OutcomeReason = Literal["dome_destroyed", "oxygen"]

#: Задачи юнита. Рабочие состояния дрона описаны в sim/workers.py, боевые — в sim/combat.py.
UnitTask = Literal[
    "idle",
    "moving",
    "to_resource",
    "gathering",
    "waiting",
    "returning",
    "to_site",
    "building",
    "repairing",
    "attacking",
    "attack_move",
]

#: Задачи, после которых дрон сам возвращается к добыче.
GATHER_TASKS: tuple[UnitTask, ...] = ("to_resource", "gathering", "waiting", "returning")

EventKind = Literal[
    "dropoff",
    "shot",
    "unit_destroyed",
    "building_destroyed",
    "construction_complete",
    "unit_trained",
    "deposit_depleted",
]


def opponent_of(side: Side) -> Side:
    return "vector" if side == "player" else "player"


@dataclass(frozen=True)
class Point:
    x: int
    y: int


@dataclass
class GameMap:
    width: int
    height: int
    #: Клетки построчно: индекс = y * width + x.
    tiles: list[TileKind]
    bases: dict[Side, Point]
    #: Клетки каждого рудного поля: сначала поля игрока, потом зеркальные поля ВЕКТОРа.
    ore_fields: list[list[Point]] = field(default_factory=list)


@dataclass
class QueueItem:
    type: UnitType
    remaining_ms: int


@dataclass
class Building:
    id: int
    side: Side
    type: BuildingType
    x: int
    y: int
    hp: float
    #: False — здание отключено из-за нехватки энергии или воды.
    powered: bool = True
    #: False — стройплощадка: ничего не производит, не даёт лимит армии и не тратит энергию.
    complete: bool = True
    #: Прогресс стройки от 0 до 1.
    build_progress: float = 1.0
    #: Очередь сборки юнитов (купол и ангар).
    queue: list[QueueItem] = field(default_factory=list)
    #: Точка сбора новых юнитов.
    rally: Point | None = None


@dataclass
class Unit:
    id: int
    side: Side
    type: UnitType
    #: Позиция в клетках, во время движения дробная.
    x: float
    y: float
    hp: float
    #: Оставшиеся точки пути без текущей клетки.
    path: list[Point] = field(default_factory=list)
    task: UnitTask = "idle"
    #: Цель задачи: id поля руды, здания или вражеского юнита — зависит от task.
    target_id: int | None = None
    #: Сколько металла несёт дрон.
    carry: int = 0
    #: Таймер текущей работы (добыча), мс.
    work_ms: int = 0
    #: Поле, к которому дрон возвращается после сдачи груза.
    home_deposit: int | None = None
    #: Вернуться к добыче после стройки или ремонта.
    resume_gathering: bool = False
    #: Точка, к которой идёт атака с движением.
    attack_point: Point | None = None
    #: Через сколько мс можно снова пересчитать путь к движущейся цели.
    repath_ms: int = 0
    #: Таймер для событий выстрела (для эффектов), мс.
    fire_ms: int = 0
    #: Направление корпуса и турели, радианы (для отрисовки).
    facing: float = 0.0
    aim: float = 0.0


@dataclass
class Deposit:
    id: int
    tiles: list[Point]
    amount: int
    initial: int


def empty_resources() -> dict[ResourceKey, int]:
    return dict.fromkeys(RESOURCE_KEYS, 0)


@dataclass
class Colony:
    side: Side
    resources: dict[ResourceKey, int]
    colonists: int
    #: Сколько солов подряд кислорода не хватило.
    oxygen_deficit_sols: int = 0
    #: Изменение ресурсов за последний сол — для HUD.
    last_delta: dict[ResourceKey, int] = field(default_factory=empty_resources)
    #: Металл в начале сола: он меняется добычей и тратами в течение сола, а не раз в сол.
    sol_start_metal: int = 0
    #: Солы в «зелёной зоне» — для очков (W3-10), считается в economy.apply_sol.
    green_sols: int = 0


@dataclass
class SideStats:
    """Счётчики для экрана итогов."""

    metal_mined: int = 0
    units_trained: int = 0
    units_lost: int = 0
    buildings_built: int = 0
    enemy_units_killed: int = 0
    enemy_buildings_destroyed: int = 0


@dataclass(frozen=True)
class Outcome:
    winner: Side
    reason: OutcomeReason


@dataclass
class GameState:
    seed: int
    map: GameMap
    colonies: dict[Side, Colony]
    buildings: list[Building] = field(default_factory=list)
    units: list[Unit] = field(default_factory=list)
    deposits: list[Deposit] = field(default_factory=list)
    stats: dict[Side, SideStats] = field(default_factory=lambda: {side: SideStats() for side in SIDES})
    tick: int = 0
    elapsed_ms: int = 0
    sol: int = 0
    sol_elapsed_ms: int = 0
    next_id: int = 1
    outcome: Outcome | None = None
    difficulty: Difficulty = "normal"


@dataclass(frozen=True)
class SimEvent:
    """Событие для отрисовки и отчётов. Хранится вне GameState и на логику не влияет."""

    kind: EventKind
    side: Side
    x: float
    y: float
    #: Для выстрела — куда.
    tx: float = 0.0
    ty: float = 0.0
    #: Сколько металла сдано и т.п.
    value: int = 0
    #: Тип здания или юнита.
    subject: str = ""


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    reason: str = ""
    id: int | None = None

    @staticmethod
    def success(id: int | None = None) -> CommandResult:
        return CommandResult(ok=True, id=id)

    @staticmethod
    def failure(reason: str) -> CommandResult:
        return CommandResult(ok=False, reason=reason)
