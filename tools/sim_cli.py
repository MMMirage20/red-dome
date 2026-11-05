"""Генератор датасета (ФТ-17): партии «бот против бота» без графики → CSV.

Одна строка CSV = одна сторона в один сол. Запуск из корня репозитория:
    python -m tools.sim_cli --games 200 --seed 1 --sols 60 --out ml/data/games_v0.csv

С флагом --report вместо CSV печатает отчёт баланса: итог партии и время до поражения, когда и
какого размера уходят волны, минимальное HP купола, металл к 180 с, роверы к первой волне
противника, ангар, первый ровер, истощение полей. С --md — то же в Markdown для docs/balance:
    python -m tools.sim_cli --games 20 --seed 1 --report --md --difficulty normal --player bot
--player economy ставит за игрока «новичка без армии», --difficulty — уровень сложности ВЕКТОРа.
"""

from __future__ import annotations

import argparse
import csv
import io
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

from reddome.bot.bot_v0 import BUILD_ORDER, BotV0
from reddome.config.balance import Balance, load_balance
from reddome.sim.economy import supply_cap, supply_used
from reddome.sim.simulation import Simulation
from reddome.sim.types import BUILDING_TYPES, DIFFICULTIES, RESOURCE_KEYS, SIDES, UNIT_TYPES, Side, opponent_of

#: Шаг прогона в отчёте: события получают время с точностью до секунды.
REPORT_STEP_MS = 1000
CHECKPOINT_MS = 180_000


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m tools.sim_cli", description=__doc__.splitlines()[0])
    parser.add_argument("--games", type=int, default=10, help="число партий")
    parser.add_argument("--seed", type=int, default=1, help="seed первой партии, дальше seed + номер")
    parser.add_argument("--sols", type=int, default=60, help="максимум солов в партии")
    parser.add_argument("--out", type=Path, default=Path("ml/data/games_v0.csv"), help="куда записать CSV")
    parser.add_argument("--report", action="store_true", help="напечатать отчёт баланса вместо CSV")
    parser.add_argument("--md", action="store_true", help="отчёт в Markdown (для docs/balance)")
    parser.add_argument("--player", choices=sorted(PLAYER_PROXIES), default="bot",
                        help="кто играет за игрока в отчёте: bot — бот v0, economy — без армии")
    parser.add_argument("--difficulty", choices=DIFFICULTIES, default=None,
                        help="сложность ВЕКТОРа: easy, normal, hard (по умолчанию — из balance.json)")
    return parser.parse_args(argv)


class EconomyOnlyBot(BotV0):
    """Замена новичку, который не строит армию: экономика по порядку стройки бота, но без ангара,
    роверов и атак. Отчёт с ним показывает, сколько времени волны ВЕКТОРа дают на оборону."""

    def _follow_build_order(self, sim: Simulation) -> None:
        while self.step < len(BUILD_ORDER) and BUILD_ORDER[self.step].type == "hangar":
            self.step += 1
        if self.step < len(BUILD_ORDER):
            super()._follow_build_order(sim)

    def _send_waves(self, sim: Simulation) -> None:
        pass


#: Кто играет за сторону игрока в отчёте: зеркальный бот или «новичок без армии».
PLAYER_PROXIES: dict[str, type[BotV0]] = {"bot": BotV0, "economy": EconomyOnlyBot}
PLAYER_PROXY_TITLES = {
    "bot": "за игрока играет тот же бот «ВЕКТОР» v0 (с форой игрока, без множителей сложности)",
    "economy": "за игрока — «новичок без армии»: экономика по порядку стройки бота, без ангара, роверов и атак",
}


def new_game(balance: Balance, seed: int) -> Simulation:
    sim = Simulation(balance, seed)
    for side in SIDES:
        sim.add_controller(BotV0(side))
    return sim


@dataclass
class SideRecord:
    """Что отчёт баланса знает об одной стороне в одной партии."""

    hangar_sec: float | None = None
    first_rover_sec: float | None = None
    metal_mined_at_checkpoint: int = 0
    depleted_sec: list[float] = field(default_factory=list)
    #: Волны этой стороны: (время отправки, с; сколько роверов ушло).
    waves: list[tuple[float, int]] = field(default_factory=list)
    dome_max_hp: float = 0.0
    #: Самое низкое HP своего купола за партию; 0 — купол разрушен.
    min_dome_hp: float = 0.0
    #: Сколько своих роверов было, когда противник отправил первую волну.
    rovers_at_enemy_first_wave: int | None = None


@dataclass
class GameRecord:
    seed: int
    sides: dict[Side, SideRecord]
    winner: Side | None
    reason: str | None
    end_sec: float


def _dome_hp(sim: Simulation, side: Side) -> float:
    dome = next((b for b in sim.state.buildings if b.side == side and b.type == "dome"), None)
    return dome.hp if dome is not None else 0.0


def _rovers(sim: Simulation, side: Side) -> int:
    return sum(1 for u in sim.state.units if u.side == side and u.type == "guard_rover" and u.hp > 0)


def play_report_game(balance: Balance, seed: int, sols: int, player: str = "bot") -> GameRecord:
    """Одна партия с замерами для отчёта: ВЕКТОР — бот v0, игрок — см. PLAYER_PROXIES. Детерминирована по seed."""
    sim = Simulation(balance, seed)
    bots: dict[Side, BotV0] = {"player": PLAYER_PROXIES[player]("player"), "vector": BotV0("vector")}
    for bot in bots.values():
        sim.add_controller(bot)
    records = {side: SideRecord() for side in SIDES}
    for side, record in records.items():
        record.dome_max_hp = record.min_dome_hp = _dome_hp(sim, side)
    limit_ms = sols * balance.sol_seconds * 1000
    while sim.state.elapsed_ms < limit_ms and sim.state.outcome is None:
        sim.update(REPORT_STEP_MS)
        now = sim.state.elapsed_ms / 1000
        for event in sim.drain_events():
            record = records[event.side]
            if event.kind == "construction_complete" and event.subject == "hangar" and record.hangar_sec is None:
                record.hangar_sec = now
            elif event.kind == "unit_trained" and event.subject == "guard_rover" and record.first_rover_sec is None:
                record.first_rover_sec = now
            elif event.kind == "deposit_depleted":
                record.depleted_sec.append(now)
        for side, record in records.items():
            record.min_dome_hp = min(record.min_dome_hp, _dome_hp(sim, side))
            sent = bots[side].waves
            if len(record.waves) < len(sent) and not record.waves:
                records[opponent_of(side)].rovers_at_enemy_first_wave = _rovers(sim, opponent_of(side))
            record.waves = [(ms / 1000, size) for ms, size in sent]
        if sim.state.elapsed_ms == CHECKPOINT_MS:
            for side, record in records.items():
                record.metal_mined_at_checkpoint = sim.state.stats[side].metal_mined
    outcome = sim.state.outcome
    return GameRecord(
        seed=seed,
        sides=records,
        winner=outcome.winner if outcome else None,
        reason=outcome.reason if outcome else None,
        end_sec=sim.state.elapsed_ms / 1000,
    )


def describe(values: list[float], unit: str = " с") -> str:
    """«медиана (мин–макс), n» или «не случилось»."""
    if not values:
        return "не случилось"
    return f"{statistics.median(values):.0f}{unit} ({min(values):.0f}–{max(values):.0f}), n={len(values)}"


SIDE_TITLES: dict[Side, str] = {"player": "Игрок", "vector": "ВЕКТОР"}
REASON_TITLES = {"dome_destroyed": "купол", "oxygen": "кислород"}
WAVES_IN_SUMMARY = 3


def summary_rows(games: list[GameRecord], side: Side) -> list[tuple[str, str]]:
    """Сводка по стороне: (показатель, значение)."""
    recs = [g.sides[side] for g in games]
    wins = sum(g.winner == side for g in games)
    losses = [g.end_sec for g in games if g.winner == opponent_of(side)]
    rows = [
        ("Побед", f"{wins} из {len(games)}"),
        ("Время до поражения", describe(losses)),
    ]
    for n in range(WAVES_IN_SUMMARY):
        waves = [r.waves[n] for r in recs if len(r.waves) > n]
        rows.append((f"Своя волна {n + 1}: отправлена", describe([t for t, _ in waves])))
        rows.append((f"Своя волна {n + 1}: роверов", describe([s for _, s in waves], unit="")))
    hp = [100 * r.min_dome_hp / r.dome_max_hp for r in recs]
    rows += [
        ("Мин. HP своего купола, % от полного", describe(hp, unit=" %")),
        ("Металл добыт к 180 с", describe([r.metal_mined_at_checkpoint for r in recs], unit="")),
        ("Роверов к первой волне противника", describe([r.rovers_at_enemy_first_wave for r in recs if r.rovers_at_enemy_first_wave is not None], unit="")),
        ("Ангар достроен", describe([r.hangar_sec for r in recs if r.hangar_sec is not None])),
        ("Первый ровер", describe([r.first_rover_sec for r in recs if r.first_rover_sec is not None])),
        ("Первое истощённое поле", describe([r.depleted_sec[0] for r in recs if r.depleted_sec])),
    ]
    return rows


def game_row(game: GameRecord) -> list[str]:
    """Строка таблицы партий с точки зрения игрока."""
    player, vector = game.sides["player"], game.sides["vector"]
    if game.winner is None:
        result = "ничья по времени"
    else:
        result = f"{'победа' if game.winner == 'player' else 'поражение'} ({REASON_TITLES[game.reason or '']})"
    waves = ", ".join(f"{t:.0f} с × {size}" for t, size in vector.waves[:WAVES_IN_SUMMARY]) or "—"
    rovers = "—" if player.rovers_at_enemy_first_wave is None else str(player.rovers_at_enemy_first_wave)
    return [
        str(game.seed),
        result,
        f"{game.end_sec:.0f} с",
        waves,
        f"{player.min_dome_hp:.0f} / {player.dome_max_hp:.0f}",
        str(player.metal_mined_at_checkpoint),
        rovers,
    ]


GAME_HEADER = ["seed", "итог для игрока", "конец", "волны ВЕКТОРа (отправка × роверов)", "мин. HP купола игрока", "металл игрока к 180 с", "роверов игрока к 1-й волне"]


def _md_table(header: list[str], rows: list[list[str]]) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + " --- |" * len(header), *("| " + " | ".join(r) + " |" for r in rows)]


def render_markdown(games: list[GameRecord], args: argparse.Namespace, balance: Balance) -> str:
    seeds = f"{games[0].seed}–{games[-1].seed}" if games else "—"
    lines = [
        f"Команда: `python -m tools.sim_cli --games {args.games} --seed {args.seed} --sols {args.sols} "
        f"--difficulty {balance.difficulty} --player {args.player} --report --md`",
        "",
        f"Сложность: {balance.difficulty}. "
        f"Партий: {len(games)} (seed {seeds}), лимит {args.sols} солов ({args.sols * balance.sol_seconds:.0f} с). "
        f"ВЕКТОР — бот v0, {PLAYER_PROXY_TITLES[args.player]}; это замена новичку, а не живой игрок. "
        "Время волн — момент отправки, а не прихода к базе. Значения: медиана (мин–макс), n — сколько раз случилось.",
        "",
        "### Сводка",
        "",
    ]
    player, vector = summary_rows(games, "player"), summary_rows(games, "vector")
    lines += _md_table(["Показатель", SIDE_TITLES["player"], SIDE_TITLES["vector"]],
                       [[name, p, v] for (name, p), (_, v) in zip(player, vector)])
    lines += ["", "### Партии", ""]
    lines += _md_table(GAME_HEADER, [game_row(g) for g in games])
    return "\n".join(lines) + "\n"


def render_text(games: list[GameRecord], balance: Balance) -> str:
    lines = [f"Сложность: {balance.difficulty}, партий: {len(games)}"]
    for side in SIDES:
        lines.append(f"-- {SIDE_TITLES[side]}")
        lines += [f"  {name}: {value}" for name, value in summary_rows(games, side)]
    lines.append("-- Партии (" + "; ".join(GAME_HEADER) + ")")
    lines += ["  " + "; ".join(game_row(g)) for g in games]
    return "\n".join(lines) + "\n"


def run_report(balance: Balance, args: argparse.Namespace) -> None:
    games = [play_report_game(balance, args.seed + game_id, args.sols, args.player) for game_id in range(args.games)]
    print(render_markdown(games, args, balance) if args.md else render_text(games, balance), end="")


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
    balance = load_balance(difficulty=args.difficulty)
    if args.report:
        run_report(balance, args)
    else:
        run_csv(balance, args)


if __name__ == "__main__":
    main()
