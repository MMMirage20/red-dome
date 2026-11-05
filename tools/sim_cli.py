"""Генератор датасета (ФТ-17): партии «бот против бота» без графики → CSV.

Одна строка CSV = одна сторона в один сол. Запуск из корня репозитория:
    python -m tools.sim_cli --games 200 --seed 1 --sols 60 --out ml/data/games_v0.csv

С флагом --report вместо CSV печатает тайминги для проверки баланса: когда достроен ангар,
когда собран первый ровер, сколько металла добыто к 3:00, когда истощаются рудные поля.
"""

from __future__ import annotations

import argparse
import csv
import io
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

from reddome.bot.bot_v0 import BotV0
from reddome.config.balance import Balance, load_balance
from reddome.sim.economy import supply_cap, supply_used
from reddome.sim.simulation import Simulation
from reddome.sim.types import BUILDING_TYPES, RESOURCE_KEYS, SIDES, UNIT_TYPES, Side

#: Шаг прогона в отчёте: события получают время с точностью до секунды.
REPORT_STEP_MS = 1000
CHECKPOINT_MS = 180_000


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m tools.sim_cli", description=__doc__.splitlines()[0])
    parser.add_argument("--games", type=int, default=10, help="число партий")
    parser.add_argument("--seed", type=int, default=1, help="seed первой партии, дальше seed + номер")
    parser.add_argument("--sols", type=int, default=60, help="максимум солов в партии")
    parser.add_argument("--out", type=Path, default=Path("ml/data/games_v0.csv"), help="куда записать CSV")
    parser.add_argument("--report", action="store_true", help="напечатать тайминги баланса вместо CSV")
    return parser.parse_args(argv)


def new_game(balance: Balance, seed: int) -> Simulation:
    sim = Simulation(balance, seed)
    for side in SIDES:
        sim.add_controller(BotV0(side))
    return sim


@dataclass
class SideTimings:
    hangar_sec: float | None = None
    first_rover_sec: float | None = None
    metal_mined_at_checkpoint: int = 0
    depleted_sec: list[float] = field(default_factory=list)


def run_report(balance: Balance, args: argparse.Namespace) -> None:
    timings: list[SideTimings] = []
    endings: list[str] = []
    for game_id in range(args.games):
        sim = new_game(balance, args.seed + game_id)
        per_side: dict[Side, SideTimings] = {side: SideTimings() for side in SIDES}
        limit_ms = args.sols * balance.sol_seconds * 1000
        while sim.state.elapsed_ms < limit_ms and sim.state.outcome is None:
            sim.update(REPORT_STEP_MS)
            now = sim.state.elapsed_ms / 1000
            for event in sim.drain_events():
                t = per_side[event.side]
                if event.kind == "construction_complete" and event.subject == "hangar" and t.hangar_sec is None:
                    t.hangar_sec = now
                elif event.kind == "unit_trained" and event.subject == "guard_rover" and t.first_rover_sec is None:
                    t.first_rover_sec = now
                elif event.kind == "deposit_depleted":
                    t.depleted_sec.append(now)
            if sim.state.elapsed_ms == CHECKPOINT_MS:
                for side in SIDES:
                    per_side[side].metal_mined_at_checkpoint = sim.state.stats[side].metal_mined
        timings.extend(per_side.values())
        outcome = sim.state.outcome
        endings.append(
            f"партия {game_id}: {outcome.winner} ({outcome.reason}) на {sim.state.elapsed_ms // 1000} с"
            if outcome
            else f"партия {game_id}: без победителя за {sim.state.elapsed_ms // 1000} с"
        )

    def describe(values: list[float]) -> str:
        if not values:
            return "не случилось"
        return f"медиана {statistics.median(values):.0f} с (мин {min(values):.0f}, макс {max(values):.0f}), n={len(values)}"

    print(f"Партий: {args.games}, сторон с ботом: {len(timings)}")
    print("Ангар достроен:", describe([t.hangar_sec for t in timings if t.hangar_sec is not None]))
    print("Первый ровер:", describe([t.first_rover_sec for t in timings if t.first_rover_sec is not None]))
    mined = [t.metal_mined_at_checkpoint for t in timings]
    print(f"Добыто металла к 3:00: медиана {statistics.median(mined):.0f} (мин {min(mined)}, макс {max(mined)})")
    print("Первое истощённое поле:", describe([t.depleted_sec[0] for t in timings if t.depleted_sec]))
    for line in endings:
        print(line)


def run_csv(balance: Balance, args: argparse.Namespace) -> None:
    header = [
        "game_id",
        "seed",
        "sol",
        "side",
        *RESOURCE_KEYS,
        "colonists",
        "supply_used",
        "supply_cap",
        "metal_mined",
        *(f"n_{t}" for t in BUILDING_TYPES),
        *(f"n_{t}" for t in UNIT_TYPES),
        "winner",
    ]
    rows_written = 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        for game_id in range(args.games):
            seed = args.seed + game_id
            sim = new_game(balance, seed)
            rows: list[list[object]] = []
            for _ in range(args.sols):
                if sim.state.outcome is not None:
                    break
                sim.update(balance.sol_seconds * 1000)
                sim.drain_events()
                state = sim.state
                for side in SIDES:
                    colony = state.colonies[side]
                    rows.append(
                        [
                            game_id,
                            seed,
                            state.sol,
                            side,
                            *(colony.resources[key] for key in RESOURCE_KEYS),
                            colony.colonists,
                            supply_used(state, balance, side),
                            supply_cap(state, balance, side),
                            state.stats[side].metal_mined,
                            *(sum(b.side == side and b.type == t for b in state.buildings) for t in BUILDING_TYPES),
                            *(sum(u.side == side and u.type == t for u in state.units) for t in UNIT_TYPES),
                        ]
                    )
            winner = sim.state.outcome.winner if sim.state.outcome else ""
            writer.writerows(row + [winner] for row in rows)
            rows_written += len(rows)
    print(f"Партий: {args.games}, строк: {rows_written}, файл: {args.out.resolve()}")


def main(argv: list[str] | None = None) -> None:
    # В Windows вывод в канал (например, в Git Bash) идёт в cp1251, и кириллица ломается.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv)
    balance = load_balance()
    if args.report:
        run_report(balance, args)
    else:
        run_csv(balance, args)


if __name__ == "__main__":
    main()
