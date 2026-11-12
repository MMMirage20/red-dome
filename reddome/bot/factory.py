"""Какой бот играет за ВЕКТОРа в миссии (balance.json → missions.N.bot)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from reddome.bot.adaptive import BotAdaptive
from reddome.bot.bot_v0 import BotV0
from reddome.bot.strategist import BotStrategist

if TYPE_CHECKING:
    from reddome.config.balance import BotSpec
    from reddome.sim.types import Side

#: Ключ из balance.json → класс бота. Названия уровней — из устава: «Новичок», «Стратег», «Адаптивный».
BOT_CLASSES: dict[str, type[BotV0]] = {"novice": BotV0, "strategist": BotStrategist, "adaptive": BotAdaptive}
BOT_TITLES: dict[str, str] = {"novice": "Новичок", "strategist": "Стратег", "adaptive": "Адаптивный"}


def make_bot(kind: str, side: Side = "vector", params: BotSpec | None = None) -> BotV0:
    return BOT_CLASSES[kind](side, params)
