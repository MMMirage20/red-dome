"""Бот «ВЕКТОР» «Адаптивный» — противник миссии 3 «Последний купол» (этап 3, ФТ-30).

Играет как «Стратег» (bot/strategist.py) и в дополнение:
- с bot.classify_from_sec раз в сол относит соперника к одному из стилей (bot/style.py) — моделью
  из style_model.json или, если её нет, правилами;
- включает контрстратегию из устава (docs/charter.md, раздел 4):
    раш       — турели у базы, армия ждёт дома и контратакует после отбитой волны;
    черепаха  — ракетные роверы осаждают турели, ледяные поля занимаются раньше;
    экономист — ранние набеги на буры и переработчики;
    техно     — быстрая атака всем, что готово, пока реактор не окупился (bot.tech_window_sec);
- с bot.great_dome_from_sec строит Большой купол (экономическая победа) и отправляет на него дронов.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from reddome.bot.strategist import BotStrategist
from reddome.bot.style import StyleClassifier, StyleMemory, army_near_base, features, load_model
from reddome.sim.state import distance, find_free_tile_near
from reddome.sim.types import Point, Side, opponent_of

if TYPE_CHECKING:
    from reddome.config.balance import BotSpec
    from reddome.sim.simulation import Simulation

#: Сколько турелей у базы ставить против раша.
RUSH_TURRETS = 2
#: Сколько дронов отправлять строить Большой купол.
GREAT_DOME_BUILDERS = 2


class BotAdaptive(BotStrategist):
    def __init__(self, side: Side = "vector", params: BotSpec | None = None,
                 classifier: StyleClassifier | None = None) -> None:
        super().__init__(side, params)
        self.classifier = classifier if classifier is not None else StyleClassifier(load_model())
        self.memory = StyleMemory()
        #: Текущая догадка о стиле соперника и все смены догадок: (время партии, мс; стиль).
        self.style: str | None = None
        self.guesses: list[tuple[int, str]] = []
        self._last_sol = -1
        self._enemy_was_near = False

    # --- Решения ------------------------------------------------------------------

    def think(self, sim: Simulation) -> None:
        state = sim.state
        opponent = opponent_of(self.side)
        self.memory.observe(state, opponent)
        spec = self.spec(sim)
        if state.elapsed_ms >= spec.classify_from_sec * 1000 and state.sol != self._last_sol:
            self._last_sol = state.sol
            guess = self.classifier.predict(features(state, opponent, self.memory))
            if guess != self.style:
                self.style = guess
                self.guesses.append((state.elapsed_ms, guess))
        self._counter(sim)
        super().think(sim)
        self._great_dome(sim)

    def _counter(self, sim: Simulation) -> None:
        state = sim.state
        near = army_near_base(state, opponent_of(self.side)) > 0
        repelled = self._enemy_was_near and not near
        self._enemy_was_near = near
        # Черепаха сидит у базы — ледяные поля можно занимать сразу.
        self.early_fields = self.style == "turtle"
        if self.style == "rush":
            turrets = [b for b in state.buildings if b.side == self.side and b.type == "turret"
                       and distance(b.x, b.y, *self._base(sim)) <= 5]
            if len(turrets) < RUSH_TURRETS and not self._building_now(sim, "turret"):
                self._try_build(sim, "turret", "base")
            if repelled:
                self._launch(sim, self._ready_fighters(sim), min_size=2)
        elif self.style == "tech" and self._reactor_is_new(sim):
            self._launch(sim, self._ready_fighters(sim), min_size=self.spec(sim).tech_attack_size)
        elif self.style == "economy" and self.next_wave_ms is not None:
            # Ранние набеги: таймер волны не дальше bot.economy_raid_sec.
            raid_ms = round(self.spec(sim).economy_raid_sec * 1000)
            self.next_wave_ms = min(self.next_wave_ms, state.elapsed_ms + raid_ms)

    def _reactor_is_new(self, sim: Simulation) -> bool:
        """Реактор соперника ещё «не окупился»: прошло меньше bot.tech_window_sec с тех пор, как бот его увидел.
        Реактора не видели — тоже True: стиль «техно» угадан по ракетным роверам и стоит бить сразу."""
        seen = self.memory.reactor_sec
        return seen is None or sim.state.elapsed_ms / 1000 - seen < self.spec(sim).tech_window_sec

    def _base(self, sim: Simulation) -> tuple[int, int]:
        base = sim.state.map.bases[self.side]
        return base.x, base.y

    def _building_now(self, sim: Simulation, type_: str) -> bool:
        return any(b.side == self.side and b.type == type_ and not b.complete for b in sim.state.buildings)

    def _launch(self, sim: Simulation, fighters: list, min_size: int) -> None:
        """Внеочередная волна контрстратегии: не меньше min_size роверов и не больше обычной волны
        (но хотя бы min_size) — остальные остаются охранять базу, как у «Стратега»."""
        if len(fighters) < min_size:
            return
        target = self.wave_target(sim)
        if target is None:
            return
        size = max(min_size, self.spec(sim).wave_size(self.waves_sent))
        fighters = sorted(fighters, key=lambda u: (-u.hp, u.id))[:size]
        sim.attack_move(self.side, [u.id for u in fighters], target)
        self.waves.append((sim.state.elapsed_ms, len(fighters)))
        self.waves_sent += 1
        spec = self.spec(sim)
        self.next_wave_ms = sim.state.elapsed_ms + int(spec.wave_interval_sec * 1000)

    def _send_waves(self, sim: Simulation) -> None:
        if self.style == "rush":
            # Против раша армия ждёт дома, пока не наберётся на волну с запасом.
            ready = self._ready_fighters(sim)
            if len(ready) < self.spec(sim).wave_size(self.waves_sent) + 2:
                return
        super()._send_waves(sim)

    def train_rover(self, sim: Simulation) -> None:
        """Против черепахи — в основном ракетные роверы: они бьют дальше турелей."""
        if self.style == "turtle" and sim.train(self.side, "rocket_rover").ok:
            return
        super().train_rover(sim)

    def wave_target(self, sim: Simulation) -> Point | None:
        state = sim.state
        enemy = opponent_of(self.side)
        base = state.map.bases[self.side]
        wanted = {"turtle": ("turret",), "economy": ("ice_drill", "regolith")}.get(self.style or "", ())
        targets = [b for b in state.buildings if b.side == enemy and b.type in wanted]
        if targets:
            target = min(targets, key=lambda b: (distance(base.x, base.y, b.x, b.y), b.id))
            return find_free_tile_near(state, Point(target.x, target.y), 2)
        return super().wave_target(sim)

    # --- Большой купол ------------------------------------------------------------

    def _great_dome(self, sim: Simulation) -> None:
        state = sim.state
        if not sim.mission.allows_building("great_dome"):
            return
        if state.elapsed_ms < self.spec(sim).great_dome_from_sec * 1000:
            return
        site = next((b for b in state.buildings if b.side == self.side and b.type == "great_dome"), None)
        if site is None:
            self._try_build(sim, "great_dome")
            return
        if site.complete:
            return
        builders = [u for u in state.units if u.side == self.side and u.task in ("to_site", "building")
                    and u.target_id == site.id]
        if len(builders) >= GREAT_DOME_BUILDERS:
            return
        free = sorted((u for u in state.units if u.side == self.side and u.type == "drone"
                       and u.task not in ("to_site", "building")),
                      key=lambda u: (distance(u.x, u.y, site.x, site.y), u.id))
        need = GREAT_DOME_BUILDERS - len(builders)
        if free[:need]:
            sim.help_build(self.side, [u.id for u in free[:need]], site.id)
