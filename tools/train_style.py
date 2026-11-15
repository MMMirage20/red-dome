"""Обучение классификатора стиля игрока (этап 3, ФТ-31, НФТ-14).

Партии миссии 3: за игрока — скрипт с известным стилем (tools/style_bots.py), за ВЕКТОРа — «Адаптивный»
на правилах. Каждый сол с --from-sec по --to-sec записываются признаки игрока (reddome/bot/style.py)
и правильный стиль. Выборка делится на обучающую и тестовую по партиям (seed % 5 == 0 — тест), а не по
строкам. Модель — логистическая регрессия scikit-learn; коэффициенты сохраняются в JSON, который игра
читает без scikit-learn. Запуск из корня репозитория (нужен requirements-ai.txt):

    python -m tools.train_style --games 60 --seed 1
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from reddome.bot.adaptive import BotAdaptive
from reddome.bot.style import FEATURES, MODEL_PATH, STYLE_NAMES, STYLES, StyleClassifier, StyleMemory, features, rule_based_style
from reddome.config.balance import load_balance
from reddome.sim.simulation import Simulation
from tools.style_bots import StyleBot

MISSION = 3
STEP_MS = 1000
REPORT_PATH = Path("docs/ml/style_classifier.md")
CSV_PATH = Path("ml/data/style_v1.csv")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m tools.train_style", description=__doc__.splitlines()[0])
    parser.add_argument("--games", type=int, default=60, help="партий на каждый стиль")
    parser.add_argument("--seed", type=int, default=1, help="seed первой партии")
    parser.add_argument("--from-sec", type=float, default=180, help="с какой секунды партии брать признаки")
    parser.add_argument("--to-sec", type=float, default=300, help="до какой секунды")
    parser.add_argument("--workers", type=int, default=4, help="процессов для прогона партий")
    parser.add_argument("--out", type=Path, default=MODEL_PATH, help="куда сохранить модель (JSON)")
    parser.add_argument("--report", type=Path, default=REPORT_PATH, help="отчёт в Markdown")
    parser.add_argument("--csv", type=Path, default=CSV_PATH, help="датасет признаков (в git не попадает)")
    return parser.parse_args(argv)


def play_style_game(job: tuple[str, int, float, float]) -> list[dict[str, float | str | int]]:
    """Одна партия: строки признаков игрока раз в сол в окне [from_sec, to_sec]."""
    style, seed, from_sec, to_sec = job
    balance = load_balance()
    sim = Simulation(balance, seed, "normal", MISSION)
    rng = random.Random(f"style:{seed}:{style}")
    sim.add_controller(StyleBot(style, "player", balance.side("player").bot, rng))
    sim.add_controller(BotAdaptive("vector", classifier=StyleClassifier(None)))
    memory = StyleMemory()
    rows: list[dict[str, float | str | int]] = []
    last_sol = -1
    while sim.state.outcome is None and sim.state.elapsed_ms < to_sec * 1000:
        sim.update(STEP_MS)
        memory.observe(sim.state, "player")
        if sim.state.sol != last_sol and sim.state.elapsed_ms >= from_sec * 1000:
            last_sol = sim.state.sol
            row: dict[str, float | str | int] = {"seed": seed, "style": style, "sec": sim.state.elapsed_ms // 1000}
            row.update(features(sim.state, "player", memory))
            rows.append(row)
    return rows


def confusion(true: list[str], pred: list[str]) -> list[list[int]]:
    counts = Counter(zip(true, pred, strict=True))
    return [[counts[(t, p)] for p in STYLES] for t in STYLES]


def accuracy(true: list[str], pred: list[str]) -> float:
    return sum(t == p for t, p in zip(true, pred, strict=True)) / max(1, len(true))


def render_report(args: argparse.Namespace, n_train: int, n_test: int, games: dict[str, int], acc: float,
                  rule_acc: float, matrix: list[list[int]], by_time: list[tuple[int, float, int]],
                  meta: dict[str, object]) -> str:
    names = [STYLE_NAMES[s] for s in STYLES]
    lines = [
        "# Классификатор стиля игрока",
        "",
        f"Отчёт создан командой `python -m tools.train_style --games {args.games} --seed {args.seed}` (этап 3, ФТ-31).",
        "",
        "## Данные",
        "",
        f"- Партии миссии 3: за игрока — скрипт с заданным стилем (`tools/style_bots.py`), за ВЕКТОРа — «Адаптивный» на правилах.",
        f"- По {args.games} партий на стиль, всего {sum(games.values())}; признаки раз в сол с {args.from_sec:g} по {args.to_sec:g} с партии.",
        f"- Деление по партиям: тест — партии с seed % 5 == 0. Строк: обучение {n_train}, тест {n_test}.",
        f"- Признаки: {', '.join(f'`{f}`' for f in FEATURES)}.",
        "",
        "## Результат на тестовых партиях",
        "",
        "| Модель | Accuracy |",
        "| --- | --- |",
        f"| Логистическая регрессия (scikit-learn {meta['sklearn']}) | **{acc:.3f}** |",
        f"| Правила из устава (`rule_based_style`, без обучения) | {rule_acc:.3f} |",
        "",
        f"Цель НФТ-14 — не ниже 0,75: {'выполнена' if acc >= 0.75 else 'не выполнена'}.",
        "",
        "Матрица ошибок (строки — настоящий стиль, столбцы — предсказанный):",
        "",
        "| | " + " | ".join(names) + " |",
        "| --- | " + " | ".join("---" for _ in names) + " |",
    ]
    for name, row in zip(names, matrix, strict=True):
        lines.append(f"| **{name}** | " + " | ".join(str(v) for v in row) + " |")
    lines += ["", "Точность по времени партии:", "", "| Секунда | Accuracy | Строк |", "| --- | --- | --- |"]
    lines += [f"| {sec} | {a:.3f} | {n} |" for sec, a, n in by_time]
    lines += [
        "",
        "## Ограничения",
        "",
        "- Стили играют скрипты, а не люди: на играх тестеров точность нужно перемерить (устав, раздел 4).",
        "- ВЕКТОР видит всю карту (тумана войны в игре пока нет), поэтому признаки — полные, а не разведанные.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    try:
        import sklearn
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        sys.exit("Нужен scikit-learn: pip install -r requirements-ai.txt")

    jobs = [(style, args.seed + i, args.from_sec, args.to_sec) for style in STYLES for i in range(args.games)]
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as pool:
        rows = [row for game in pool.map(play_style_game, jobs, chunksize=4) for row in game]
    if not rows:
        sys.exit("Партии не дали ни одной строки — проверьте --from-sec и --to-sec")
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["seed", "style", "sec", *FEATURES])
        writer.writeheader()
        writer.writerows(rows)

    train = [r for r in rows if int(r["seed"]) % 5 != 0]
    test = [r for r in rows if int(r["seed"]) % 5 == 0]

    def matrix_of(part: list[dict]) -> list[list[float]]:
        return [[float(r[f]) for f in FEATURES] for r in part]

    scaler = StandardScaler().fit(matrix_of(train))
    model = LogisticRegression(max_iter=5000, C=1.0)
    model.fit(scaler.transform(matrix_of(train)), [r["style"] for r in train])
    order = [list(model.classes_).index(s) for s in STYLES]
    meta = {
        "sklearn": sklearn.__version__,
        "games_per_style": args.games,
        "seed": args.seed,
        "window_sec": [args.from_sec, args.to_sec],
    }
    raw = {
        "features": list(FEATURES),
        "classes": list(STYLES),
        "mean": [float(v) for v in scaler.mean_],
        "scale": [float(v) for v in scaler.scale_],
        "coef": [[float(v) for v in model.coef_[i]] for i in order],
        "intercept": [float(model.intercept_[i]) for i in order],
    }
    # Проверяем модель тем же кодом, которым её читает игра.
    from reddome.bot.style import StyleModel

    game_model = StyleModel.from_dict({**raw, "meta": meta})
    true = [str(r["style"]) for r in test]
    pred = [game_model.predict({f: float(r[f]) for f in FEATURES}) for r in test]
    rule_pred = [rule_based_style({f: float(r[f]) for f in FEATURES}) for r in test]
    acc, rule_acc = accuracy(true, pred), accuracy(true, rule_pred)
    meta["test_accuracy"] = round(acc, 4)
    meta["rule_accuracy"] = round(rule_acc, 4)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({**raw, "meta": meta}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    by_time = []
    for sec in sorted({int(r["sec"]) for r in test}):
        idx = [i for i, r in enumerate(test) if int(r["sec"]) == sec]
        by_time.append((sec, accuracy([true[i] for i in idx], [pred[i] for i in idx]), len(idx)))
    games = Counter(str(r["style"]) for r in rows if int(r["sec"]) == min(int(x["sec"]) for x in rows))
    report = render_report(args, len(train), len(test), games, acc, rule_acc, confusion(true, pred), by_time, meta)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")
    print(f"Строк: обучение {len(train)}, тест {len(test)}")
    print(f"Accuracy на тесте: {acc:.3f} (правила: {rule_acc:.3f})")
    print("Матрица ошибок (строки — настоящий стиль):")
    for name, row in zip(STYLES, confusion(true, pred), strict=True):
        print(f"  {name:8s} {row}")
    print(f"Модель: {args.out}\nОтчёт: {args.report}")


if __name__ == "__main__":
    main()
