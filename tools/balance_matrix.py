"""Матрица баланса кампании (S4): три миссии × уровни сложности × три «заменителя» игрока.

    python -m tools.balance_matrix --games 12 --difficulty easy normal hard
    python -m tools.balance_matrix --games 12 --difficulty normal --md

Живого новичка отчёт не заменяет, но показывает, насколько миссия прощает ошибки. За игрока играют:

- passive  — «новичок без армии»: экономика и буры на своём поле, без ангара, реактора, турелей и атак.
  Важно, сколько он продержится: столько времени у новичка есть, чтобы разобраться;
- defender — «осторожный новичок»: армия только защищает базу; в миссии 2 он ставит бур на центральное
  ледяное поле и отбивает его, в миссии 3 с 9-й минуты строит Большой купол;
- active   — «активный игрок»: зеркальный бот «Стратег» (в миссии 1 — без реактора), в миссии 3 ещё и
  Большой купол.

ВЕКТОР — бот миссии (balance.json → missions.N.bot) с правками миссии и множителями сложности.
Партии идут параллельно в нескольких процессах; каждая детерминирована по seed.
"""

from __future__ import annotations

import argparse
import io
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from typing import TYPE_CHECKING

from reddome.bot.bot_v0 import BotV0
from reddome.bot.factory import make_bot
from reddome.bot.strategist import BotStrategist
from reddome.config.balance import load_balance
from reddome.sim.objectives import field_owner
from reddome.sim.simulation import Simulation
from reddome.sim.types import DIFFICULTIES, MISSIONS, opponent_of

if TYPE_CHECKING:
    from reddome.sim.types import BuildingType

#: Когда «осторожный» и «активный» игроки начинают Большой купол в миссии 3, мс.
GREAT_DOME_FROM_MS = 540_000
#: Сколько дронов они держат на стройке Большого купола.
GREAT_DOME_BUILDERS = 2
#: С какой секунды «осторожный» игрок берёт центральное ледяное поле.
CENTER_FROM_MS = 200_000


class _Proxy(BotStrategist):
    """Общее для заменителей: пропускать то, что миссия не разрешает (иначе «Стратег» в миссии 1
    застрял бы на реакторе), и строить Большой купол."""

    skip: tuple[str, ...] = ()

    def _follow_build_order(self, sim: Simulation) -> None:
        while self.step < len(self.build_order):
            item = self.build_order[self.step]
            allowed = (sim.mission.allows_building(item.type) if item.kind == "building"
                       else sim.mission.allows_unit(item.type))
            if allowed and item.type not in self.skip:
                break
            self.step += 1
        if self.step < len(self.build_order):
            super()._follow_build_order(sim)

    def build_great_dome(self, sim: Simulation) -> None:
        state = sim.state
        if not sim.mission.allows_building("great_dome") or state.elapsed_ms < GREAT_DOME_FROM_MS:
            return
        site = next((b for b in state.buildings if b.side == self.side and b.type == "great_dome"), None)
        if site is None:
            self._try_build(sim, "great_dome")
            return
        if site.complete:
            return
        builders = [u for u in state.units if u.side == self.side and u.task in ("to_site", "building")
                    and u.target_id == site.id]
        free = [u for u in state.units if u.side == self.side and u.type == "drone"
                and u.task not in ("to_site", "building")]
        need = GREAT_DOME_BUILDERS - len(builders)
        if need > 0 and free:
            sim.help_build(self.side, [u.id for u in free[:need]], site.id)


class PassivePlayer(_Proxy):
    skip = ("hangar", "reactor")

    def _grow(self, sim: Simulation) -> None:
        BotV0._grow(self, sim)

    def train_rover(self, sim: Simulation) -> None:
        pass

    def _send_waves(self, sim: Simulation) -> None:
        pass

    def _defend(self, sim: Simulation) -> None:
        pass


class DefenderPlayer(_Proxy):
    def _send_waves(self, sim: Simulation) -> None:
        pass

    def think(self, sim: Simulation) -> None:
        super().think(sim)
        self.build_great_dome(sim)

    def _contest_ice(self, sim: Simulation, building_now: set[str]) -> bool:
        if sim.mission.goal != "hold_ice" or "ice_drill" in building_now:
            return False
        field = self.ice_field(sim, "center")
        if not field or self._has_site_on(sim, field) or sim.state.elapsed_ms < CENTER_FROM_MS:
            return False
        if field_owner(sim.state, field) == opponent_of(self.side):
            idle = [u.id for u in self.fighters(sim) if u.task == "idle"]
            if len(idle) >= 3:
                sim.attack_move(self.side, idle, field[len(field) // 2])
            return False
        building: BuildingType = "ice_drill"
        return self._try_build(sim, building, "center")


class ActivePlayer(_Proxy):
    def think(self, sim: Simulation) -> None:
        super().think(sim)
        self.build_great_dome(sim)


PROXIES: dict[str, type[_Proxy]] = {"passive": PassivePlayer, "defender": DefenderPlayer, "active": ActivePlayer}
PROXY_TITLES = {"passive": "без армии", "defender": "осторожный", "active": "активный"}
REASONS = {"dome_destroyed": "купол", "oxygen": "кислород", "ice_held": "ледяные поля", "great_dome": "Большой купол"}


def play(difficulty: str, mission: int, proxy: str, seed: int, sols: int) -> tuple[str | None, str | None, float]:
    """Одна партия: (победитель, причина, конец в секундах). Без победителя — ничья по времени."""
    balance = load_balance(difficulty=difficulty)
    sim = Simulation(balance, seed, mission=mission)
    sim.add_controller(make_bot(sim.mission.bot, "vector"))
    sim.add_controller(PROXIES[proxy]("player"))
    limit_ms = sols * balance.sol_seconds * 1000
    while sim.state.elapsed_ms < limit_ms and sim.state.outcome is None:
        sim.update(1000)
        sim.drain_events()
    outcome = sim.state.outcome
    return (outcome.winner if outcome else None, outcome.reason if outcome else None, sim.state.elapsed_ms / 1000)


def _minutes(values: list[float]) -> str:
    if not values:
        return "—"
    return f"{statistics.median(values) / 60:.1f} ({min(values) / 60:.1f}–{max(values) / 60:.1f})"


def summarize(results: list[tuple[str | None, str | None, float]]) -> dict[str, str]:
    wins = [r for r in results if r[0] == "player"]
    losses = [r for r in results if r[0] == "vector"]
    reasons: dict[str, int] = {}
    for _, reason, _ in results:
        if reason:
            reasons[REASONS[reason]] = reasons.get(REASONS[reason], 0) + 1
    return {
        "score": f"{len(wins)} / {len(results) - len(wins) - len(losses)} / {len(losses)}",
        "win": _minutes([r[2] for r in wins]),
        "loss": _minutes([r[2] for r in losses]),
        "reasons": ", ".join(f"{k} {v}" for k, v in sorted(reasons.items())) or "—",
    }


def main(argv: list[str] | None = None) -> None:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="python -m tools.balance_matrix", description=__doc__.splitlines()[0])
    parser.add_argument("--games", type=int, default=12, help="партий на клетку матрицы (seed 1…N)")
    parser.add_argument("--mission", type=int, nargs="+", choices=MISSIONS, default=list(MISSIONS))
    parser.add_argument("--proxy", nargs="+", choices=list(PROXIES), default=list(PROXIES))
    parser.add_argument("--difficulty", nargs="+", choices=DIFFICULTIES, default=["normal"])
    parser.add_argument("--sols", type=int, default=60, help="лимит партии в солах (60 солов = 30 минут)")
    parser.add_argument("--md", action="store_true", help="таблица Markdown (для docs/balance)")
    args = parser.parse_args(argv)

    cells = [(d, m, p) for d in args.difficulty for m in args.mission for p in args.proxy]
    with ProcessPoolExecutor() as pool:
        futures = {cell: [pool.submit(play, *cell, seed, args.sols) for seed in range(1, args.games + 1)]
                   for cell in cells}
        rows = [(cell, summarize([f.result() for f in futures[cell]])) for cell in cells]

    if args.md:
        print("| Сложность | Миссия | Игрок | Победы / ничьи / поражения | Победа, мин | Поражение, мин | Чем кончилось |")
        print("| --- | --- | --- | --- | --- | --- | --- |")
        for (d, m, p), s in rows:
            print(f"| {d} | {m} | {PROXY_TITLES[p]} | {s['score']} | {s['win']} | {s['loss']} | {s['reasons']} |")
    else:
        for (d, m, p), s in rows:
            print(f"{d:6} миссия {m} {PROXY_TITLES[p]:10} П/Н/П {s['score']:10} победа {s['win']:17} "
                  f"поражение {s['loss']:17} {s['reasons']}")


if __name__ == "__main__":
    main()
