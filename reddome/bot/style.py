"""Классификатор стиля игрока (этап 3, ФТ-30, ФТ-31): признаки, модель в JSON и правило-запасной вариант.

Стили из устава (docs/charter.md, раздел 4): «Раш», «Черепаха», «Экономист», «Техно».
Признаки — только то, что ВЕКТОР видит на карте: здания и юниты соперника и когда его армия впервые
подошла к базе. Модель — многоклассовая логистическая регрессия, обученная tools/train_style.py
на scikit-learn; здесь только предсказание на чистом Python, поэтому игре scikit-learn не нужен (НФТ-12).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reddome.sim.state import distance
from reddome.sim.types import GameState, Side, opponent_of

STYLES: tuple[str, ...] = ("rush", "turtle", "economy", "tech")
STYLE_NAMES: dict[str, str] = {"rush": "Раш", "turtle": "Черепаха", "economy": "Экономист", "tech": "Техно"}

MODEL_PATH = Path(__file__).with_name("style_model.json")

#: Армия соперника ближе стольких клеток к командному куполу — это атака.
ATTACK_RADIUS = 10
#: Время «ещё не было» для признаков-времён: столько секунд.
NEVER_SEC = 900.0

FEATURES: tuple[str, ...] = (
    "minutes",
    "fighters",
    "rockets",
    "turrets",
    "drills",
    "refineries",
    "solars",
    "drones",
    "has_reactor",
    "hangar_sec",
    "reactor_sec",
    "attack_sec",
    "army_near_base",
)


@dataclass
class StyleMemory:
    """Что бот запомнил о сопернике по ходу партии: когда впервые увидел ангар, реактор и атаку."""

    hangar_sec: float | None = None
    reactor_sec: float | None = None
    attack_sec: float | None = None

    def observe(self, state: GameState, opponent: Side) -> None:
        now = state.elapsed_ms / 1000
        if self.hangar_sec is None and any(b.side == opponent and b.type == "hangar" for b in state.buildings):
            self.hangar_sec = now
        if self.reactor_sec is None and any(b.side == opponent and b.type == "reactor" for b in state.buildings):
            self.reactor_sec = now
        if self.attack_sec is None and army_near_base(state, opponent) > 0:
            self.attack_sec = now


def _fighter(unit_type: str) -> bool:
    return unit_type in ("guard_rover", "rocket_rover")


def army_near_base(state: GameState, opponent: Side) -> int:
    """Сколько роверов соперника у командного купола наблюдателя."""
    me = opponent_of(opponent)
    dome = next((b for b in state.buildings if b.side == me and b.type == "dome"), None)
    if dome is None:
        return 0
    return sum(
        1
        for u in state.units
        if u.side == opponent and _fighter(u.type) and distance(u.x, u.y, dome.x, dome.y) <= ATTACK_RADIUS
    )


def features(state: GameState, opponent: Side, memory: StyleMemory) -> dict[str, float]:
    """Признаки стиля соперника в текущий момент."""

    def count_b(type_: str) -> int:
        return sum(1 for b in state.buildings if b.side == opponent and b.type == type_)

    def count_u(type_: str) -> int:
        return sum(1 for u in state.units if u.side == opponent and u.type == type_)

    def when(value: float | None) -> float:
        return NEVER_SEC if value is None else value

    return {
        "minutes": state.elapsed_ms / 60_000,
        "fighters": count_u("guard_rover") + count_u("rocket_rover"),
        "rockets": count_u("rocket_rover"),
        "turrets": count_b("turret"),
        "drills": count_b("ice_drill"),
        "refineries": count_b("regolith"),
        "solars": count_b("solar"),
        "drones": count_u("drone"),
        "has_reactor": float(count_b("reactor") > 0),
        "hangar_sec": when(memory.hangar_sec),
        "reactor_sec": when(memory.reactor_sec),
        "attack_sec": when(memory.attack_sec),
        "army_near_base": army_near_base(state, opponent),
    }


@dataclass(frozen=True)
class StyleModel:
    """Логистическая регрессия: стандартизация (mean, scale), потом softmax(coef · x + intercept)."""

    features: tuple[str, ...]
    classes: tuple[str, ...]
    mean: tuple[float, ...]
    scale: tuple[float, ...]
    coef: tuple[tuple[float, ...], ...]
    intercept: tuple[float, ...]
    meta: dict[str, Any] = field(default_factory=dict, compare=False)

    def probabilities(self, values: dict[str, float]) -> dict[str, float]:
        x = [(values[name] - m) / (s or 1.0) for name, m, s in zip(self.features, self.mean, self.scale, strict=True)]
        logits = [sum(w * v for w, v in zip(row, x, strict=True)) + b for row, b in zip(self.coef, self.intercept, strict=True)]
        top = max(logits)
        exps = [math.exp(z - top) for z in logits]
        total = sum(exps)
        return {name: e / total for name, e in zip(self.classes, exps, strict=True)}

    def predict(self, values: dict[str, float]) -> str:
        probs = self.probabilities(values)
        return max(self.classes, key=lambda name: (probs[name], -self.classes.index(name)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "features": list(self.features),
            "classes": list(self.classes),
            "mean": list(self.mean),
            "scale": list(self.scale),
            "coef": [list(row) for row in self.coef],
            "intercept": list(self.intercept),
            "meta": self.meta,
        }

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> StyleModel:
        model = StyleModel(
            features=tuple(raw["features"]),
            classes=tuple(raw["classes"]),
            mean=tuple(raw["mean"]),
            scale=tuple(raw["scale"]),
            coef=tuple(tuple(row) for row in raw["coef"]),
            intercept=tuple(raw["intercept"]),
            meta=raw.get("meta", {}),
        )
        if set(model.features) - set(FEATURES):
            raise ValueError(f"Модель стиля: неизвестные признаки {sorted(set(model.features) - set(FEATURES))}")
        if set(model.classes) - set(STYLES):
            raise ValueError(f"Модель стиля: неизвестные стили {sorted(set(model.classes) - set(STYLES))}")
        return model


def load_model(path: Path = MODEL_PATH) -> StyleModel | None:
    """Модель из JSON; если файла нет или он испорчен — None, и бот берёт правила rule_based_style."""
    try:
        with path.open(encoding="utf-8") as file:
            return StyleModel.from_dict(json.load(file))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def rule_based_style(values: dict[str, float]) -> str:
    """Запасной вариант без модели — прямо по таблице признаков из устава."""
    if values["attack_sec"] < 240 or values["hangar_sec"] < 90:
        return "rush"
    if values["turrets"] >= 2 and values["turrets"] >= values["drills"]:
        return "turtle"
    if values["has_reactor"] and values["reactor_sec"] < 300:
        return "tech"
    return "economy"


class StyleClassifier:
    """То, чем пользуется бот: модель, если она есть, иначе правила."""

    def __init__(self, model: StyleModel | None = None) -> None:
        self.model = model

    @property
    def source(self) -> str:
        return "ML" if self.model is not None else "правила"

    def predict(self, values: dict[str, float]) -> str:
        return self.model.predict(values) if self.model is not None else rule_based_style(values)
