"""Очки миссии (ФТ-11, ФТ-12, W3-10) по формуле из ГКД (docs/charter.md, раздел 5):

    очки = win · победа + killed_unit · уничтоженные юниты + population · население
         + green_sol · солы в зелёной зоне + lost_colonist · погибшие колонисты

Веса — в balance.json → score. Достижения появятся вместе с профилем игрока (SQLite), пока их нет.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from reddome.sim.types import GameState, Side

if TYPE_CHECKING:
    from reddome.config.balance import Balance


@dataclass(frozen=True)
class ScoreLine:
    """Строка расшифровки очков: что считаем, сколько и вес из balance.score."""

    key: str
    label: str
    count: int
    weight: int

    @property
    def points(self) -> int:
        return self.count * self.weight


@dataclass(frozen=True)
class Score:
    lines: tuple[ScoreLine, ...]

    @property
    def total(self) -> int:
        return sum(line.points for line in self.lines)


def compute_score(state: GameState, balance: Balance, side: Side = "player") -> Score:
    """Очки стороны в текущем состоянии. Обычно считается после конца партии.

    Население — колонисты, живые к концу партии. Колонисты живут в куполе: если купол разрушен,
    они считаются погибшими.
    """
    weights = balance.score
    colony = state.colonies[side]
    start_colonists = balance.side(side).start.colonists
    dome_alive = any(b.side == side and b.type == "dome" and b.hp > 0 for b in state.buildings)
    population = colony.colonists if dome_alive else 0
    lost = max(0, start_colonists - population)
    won = state.outcome is not None and state.outcome.winner == side
    lines = (
        ScoreLine("win", "Победа", int(won), weights.win),
        ScoreLine("killed_unit", "Враги", state.stats[side].enemy_units_killed, weights.killed_unit),
        ScoreLine("population", "Население", population, weights.population),
        ScoreLine("green_sol", "Зелёные солы", colony.green_sols, weights.green_sol),
        ScoreLine("lost_colonist", "Погибшие колонисты", lost, weights.lost_colonist),
    )
    return Score(lines)
