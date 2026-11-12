"""Победа и поражение (ФТ-11) и цели миссий этапа 3 (sim/objectives.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from reddome.sim.objectives import mission_winner
from reddome.sim.types import SIDES, GameState, Outcome, opponent_of

if TYPE_CHECKING:
    from reddome.config.balance import Balance

#: Кислород на нуле дольше одного сола — поражение.
MAX_OXYGEN_DEFICIT_SOLS = 1


def check_outcome(state: GameState, balance: Balance | None = None) -> Outcome | None:
    """Если проигрывают обе стороны сразу, первой проверяется сторона игрока.

    С balance проверяется и цель миссии: ледяные поля (миссия 2) или Большой купол (миссия 3).
    """
    for side in SIDES:
        dome_alive = any(b.side == side and b.type == "dome" and b.hp > 0 for b in state.buildings)
        if not dome_alive:
            return Outcome(winner=opponent_of(side), reason="dome_destroyed")
        if state.colonies[side].oxygen_deficit_sols > MAX_OXYGEN_DEFICIT_SOLS:
            return Outcome(winner=opponent_of(side), reason="oxygen")
    if balance is not None:
        won = mission_winner(state, balance)
        if won is not None:
            return Outcome(winner=won[0], reason=won[1])
    return None
