"""Интерфейс бота."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from reddome.sim.simulation import Simulation
    from reddome.sim.types import Side


class Bot(Protocol):
    """Бот управляет своей стороной только через команды Simulation (build, train, gather, attack_move…),
    то есть по тем же правилам и ценам, что и игрок, без бонусов.

    Бот подключается через Simulation.add_controller и вызывается внутри фиксированного тика,
    поэтому партия с ботом детерминирована при любом FPS.
    """

    side: Side

    def on_tick(self, sim: Simulation) -> None: ...
