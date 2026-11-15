"""Профиль игрока в SQLite (этап 3, ФТ-32, НФТ-13): покупки, результаты миссий, воронка магазина.

Файл лежит вне папки игры: %APPDATA%\\RedDome\\profile.sqlite3 на Windows, ~/.reddome/profile.sqlite3
на Linux и macOS; путь можно задать флагом --profile или переменной REDDOME_PROFILE. Без пути профиль
живёт в памяти — так App создаётся в тестах. Оплата демонстрационная: деньги не списываются, в базу
пишется только факт покупки (устав, раздел «Коммерциализация», шаги 3–6).
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

#: Разовая покупка: миссии 2–3 (и «Схватка» в будущем). Цена — из устава.
FULL_EXPEDITION = "full_expedition"


@dataclass(frozen=True)
class Product:
    id: str
    title: str
    description: str
    price_kzt: int


PRODUCTS: dict[str, Product] = {
    FULL_EXPEDITION: Product(FULL_EXPEDITION, "Полная экспедиция", "Миссии 2–3 и режим «Схватка»", 1490),
}
#: Миссии, открытые без покупки.
FREE_MISSIONS = (1,)
#: События воронки для ЛР14: открыл магазин → увидел предложение → нажал «Купить» → купил.
FUNNEL_EVENTS = ("shop_open", "offer_view", "purchase_click", "purchase_done")

SCHEMA = """
CREATE TABLE IF NOT EXISTS purchases (
    product TEXT PRIMARY KEY,
    price_kzt INTEGER NOT NULL,
    payment TEXT NOT NULL,
    purchased_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS results (
    mission INTEGER PRIMARY KEY,
    plays INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    best_score INTEGER
);
CREATE TABLE IF NOT EXISTS funnel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event TEXT NOT NULL,
    product TEXT NOT NULL DEFAULT '',
    at TEXT NOT NULL
);
"""


def default_profile_path() -> Path:
    env = os.environ.get("REDDOME_PROFILE")
    if env:
        return Path(env)
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) / "RedDome" if appdata else Path.home() / ".reddome"
    return base / "profile.sqlite3"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Profile:
    def __init__(self, path: Path | str | None = None) -> None:
        if path is None:
            target = ":memory:"
        else:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            target = str(path)
        self.path = target
        self.db = sqlite3.connect(target)
        self.db.executescript(SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # --- Покупки ------------------------------------------------------------------

    def owns(self, product: str) -> bool:
        return self.db.execute("SELECT 1 FROM purchases WHERE product = ?", (product,)).fetchone() is not None

    def purchase_demo(self, product: str) -> bool:
        """Демо-оплата: записывает покупку без списания денег. False — уже куплено."""
        if product not in PRODUCTS:
            raise ValueError(f"Неизвестный товар {product!r}")
        if self.owns(product):
            return False
        self.db.execute(
            "INSERT INTO purchases (product, price_kzt, payment, purchased_at) VALUES (?, ?, 'demo', ?)",
            (product, PRODUCTS[product].price_kzt, _now()),
        )
        self.log("purchase_done", product, commit=False)
        self.db.commit()
        return True

    def mission_unlocked(self, mission: int) -> bool:
        return mission in FREE_MISSIONS or self.owns(FULL_EXPEDITION)

    # --- Результаты ---------------------------------------------------------------

    def record_result(self, mission: int, won: bool, score: int) -> None:
        self.db.execute(
            """INSERT INTO results (mission, plays, wins, best_score) VALUES (?, 1, ?, ?)
               ON CONFLICT(mission) DO UPDATE SET
                   plays = plays + 1,
                   wins = wins + excluded.wins,
                   best_score = MAX(COALESCE(best_score, excluded.best_score), excluded.best_score)""",
            (mission, int(won), score),
        )
        self.db.commit()

    def best_score(self, mission: int) -> int | None:
        row = self.db.execute("SELECT best_score FROM results WHERE mission = ?", (mission,)).fetchone()
        return None if row is None else row[0]

    def wins(self, mission: int) -> int:
        row = self.db.execute("SELECT wins FROM results WHERE mission = ?", (mission,)).fetchone()
        return 0 if row is None else row[0]

    # --- Воронка ------------------------------------------------------------------

    def log(self, event: str, product: str = "", commit: bool = True) -> None:
        if event not in FUNNEL_EVENTS:
            raise ValueError(f"Неизвестное событие воронки {event!r}")
        self.db.execute("INSERT INTO funnel (event, product, at) VALUES (?, ?, ?)", (event, product, _now()))
        if commit:
            self.db.commit()

    def funnel_counts(self) -> dict[str, int]:
        counts = dict.fromkeys(FUNNEL_EVENTS, 0)
        for event, n in self.db.execute("SELECT event, COUNT(*) FROM funnel GROUP BY event"):
            counts[event] = n
        return counts
