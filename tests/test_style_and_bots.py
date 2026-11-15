"""Этап 3: классификатор стиля игрока (ФТ-30, ФТ-31) и боты «Стратег» и «Адаптивный»."""

from __future__ import annotations

import json
import random
from pathlib import Path

from reddome.bot.adaptive import BotAdaptive
from reddome.bot.factory import make_bot
from reddome.bot.strategist import BotStrategist
from reddome.bot.style import (
    FEATURES,
    MODEL_PATH,
    STYLES,
    StyleClassifier,
    StyleMemory,
    StyleModel,
    features,
    load_model,
    rule_based_style,
)
from reddome.config.balance import Balance
from reddome.sim.simulation import Simulation
from tools.style_bots import StyleBot


def test_factory_picks_bot_by_mission(balance: Balance) -> None:
    assert type(make_bot(balance.mission(1).bot)).__name__ == "BotV0"
    assert isinstance(make_bot(balance.mission(2).bot), BotStrategist)
    assert isinstance(make_bot(balance.mission(3).bot), BotAdaptive)


def test_features_of_fresh_game(balance: Balance) -> None:
    sim = Simulation(balance, seed=1, mission=3)
    values = features(sim.state, "player", StyleMemory())
    assert set(values) == set(FEATURES)
    assert values["drones"] == balance.side("player").start.drones
    assert values["fighters"] == 0 and values["attack_sec"] == values["hangar_sec"]


def test_bundled_model_loads_and_predicts_every_style() -> None:
    model = load_model()
    assert model is not None, f"нет модели {MODEL_PATH} — запустите python -m tools.train_style"
    assert model.classes == STYLES
    assert model.meta["test_accuracy"] >= 0.75  # НФТ-14
    probs = model.probabilities(dict.fromkeys(FEATURES, 0.0))
    assert abs(sum(probs.values()) - 1) < 1e-9


def test_model_json_roundtrip(tmp_path: Path) -> None:
    model = StyleModel(FEATURES, STYLES, (0.0,) * len(FEATURES), (1.0,) * len(FEATURES),
                       tuple(tuple(float(i == j) for i in range(len(FEATURES))) for j in range(len(STYLES))),
                       (0.0, 0.0, 0.0, 0.0))
    path = tmp_path / "m.json"
    path.write_text(json.dumps(model.to_dict()), encoding="utf-8")
    loaded = load_model(path)
    assert loaded == model
    values = dict.fromkeys(FEATURES, 0.0)
    values["fighters"] = 5.0  # второй признак → второй класс
    assert loaded.predict(values) == "turtle"


def test_broken_model_falls_back_to_rules(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{", encoding="utf-8")
    assert load_model(path) is None
    assert StyleClassifier(None).source == "правила"


def test_rules_follow_charter_table() -> None:
    base = dict.fromkeys(FEATURES, 0.0) | {"hangar_sec": 900.0, "reactor_sec": 900.0, "attack_sec": 900.0}
    assert rule_based_style(base | {"attack_sec": 150.0}) == "rush"
    assert rule_based_style(base | {"turrets": 3.0, "drills": 1.0}) == "turtle"
    assert rule_based_style(base | {"has_reactor": 1.0, "reactor_sec": 200.0}) == "tech"
    assert rule_based_style(base | {"drills": 3.0, "drones": 9.0}) == "economy"


def _guess_against(balance: Balance, style: str, seed: int) -> str | None:
    sim = Simulation(balance, seed=seed, mission=3)
    sim.add_controller(StyleBot(style, "player", balance.side("player").bot, random.Random(seed)))
    vector = BotAdaptive("vector")
    sim.add_controller(vector)
    sim.update(300_000)
    return vector.style


def test_adaptive_bot_recognises_rush_and_turtle(balance: Balance) -> None:
    assert _guess_against(balance, "rush", 101) == "rush"
    assert _guess_against(balance, "turtle", 102) == "turtle"


def test_strategist_takes_center_field_after_its_time(balance: Balance) -> None:
    sim = Simulation(balance, seed=2, mission=2)
    bot = BotStrategist("vector")
    sim.add_controller(bot)
    center = bot.ice_field(sim, "center")
    # За игрока никто не играет: без запаса кислорода его колония задохнулась бы раньше, чем ВЕКТОР займёт центр.
    sim.state.colonies["player"].resources["oxygen"] = 10_000
    sim.update(int(sim.balance.side("vector").bot.center_from_sec * 1000) - 1000)
    assert bot.drills_by_field(sim)[1] == 0
    sim.update(90_000)
    tiles = set(center)
    assert any(b.side == "vector" and b.type == "ice_drill" and (b.x, b.y) in {(p.x, p.y) for p in tiles}
               for b in sim.state.buildings)
