"""Победа и поражение (ФТ-11)."""

from __future__ import annotations

from reddome.sim.types import SIDES, GameState, Outcome, opponent_of

#: Кислород на нуле дольше одного сола — поражение.
MAX_OXYGEN_DEFICIT_SOLS = 1


def check_outcome(state: GameState) -> Outcome | None:
    """Если проигрывают обе стороны сразу, первой проверяется сторона игрока."""
    for side in SIDES:
        dome_alive = any(b.side == side and b.type == "dome" and b.hp > 0 for b in state.buildings)
        if not dome_alive:
            return Outcome(winner=opponent_of(side), reason="dome_destroyed")
        if state.colonies[side].oxygen_deficit_sols > MAX_OXYGEN_DEFICIT_SOLS:
            return Outcome(winner=opponent_of(side), reason="oxygen")
    return None
