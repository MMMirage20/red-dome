"""Прогон миссии через интерфейс (S3-09): игра без окна, «игрок» действует только мышью и клавишами.

    python -m tools.ui_playtest --mission 1
    python -m tools.ui_playtest --mission 3 --seed 2 --difficulty hard --out playtest_out

Проходит цепочку загрузка → меню → «Играть» → выбор миссии → (для миссий 2–3) магазин и демо-покупка →
партия → итоги → «Следующая миссия». В партии — рамка выделения, ПКМ по руде, B + клавиша здания + щелчок
по карте, щелчок по куполу или ангару + Q/Z, F + щелчок для атаки, Esc и «Продолжить», Ctrl+1.
Решения — раз в 2 секунды игрового времени по тому, что видно на экране и в подсказках игры.
Экономику «игрок» ведёт заметно хуже бота, поэтому это ближе к новичку, но не заменяет живых людей.

В папку --out пишутся лог (подсказки игры, стройка, атаки, ресурсы раз в 2 минуты) и снимки экрана.
Профиль — во временном файле, настоящий профиль игрока не трогается. Код выхода 1 — сценарий упал.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame  # noqa: E402

MOUSE = [(640, 300)]
MODS = [0]
pygame.mouse.get_focused = lambda: False  # type: ignore[assignment]
pygame.mouse.get_pos = lambda: MOUSE[0]  # type: ignore[assignment]
pygame.key.get_mods = lambda: MODS[0]  # type: ignore[assignment]

from reddome.app import App  # noqa: E402
from reddome.profile import Profile  # noqa: E402
from reddome.scenes.game import GameScene  # noqa: E402
from reddome.sim.build import can_place  # noqa: E402
from reddome.sim.economy import supply_cap, supply_reserved, supply_used  # noqa: E402
from reddome.sim.state import distance  # noqa: E402
from reddome.sim.types import Point  # noqa: E402
from reddome.ui import theme  # noqa: E402
from reddome.ui.hud import HUD_HEIGHT  # noqa: E402
from reddome.ui.panel import PANEL_TOP  # noqa: E402

BUILD_KEY = {"solar": pygame.K_p, "ice_drill": pygame.K_i, "oxy_gen": pygame.K_o, "regolith": pygame.K_e,
             "hangar": pygame.K_h, "turret": pygame.K_t, "reactor": pygame.K_r, "great_dome": pygame.K_g}


class Fail(Exception):
    pass


class Human:
    def __init__(self, app: App, mission: int, out: Path, frame_ms: float, log) -> None:
        self.app, self.mission, self.out, self.dt, self.log = app, mission, out, frame_ms, log
        self.hints: list[tuple[float, str]] = []
        self.shot_n = 0
        self.paused_once = False
        self.grouped = False
        self.attack_sent_at = -1e9
        self.great_dome_helped = 0

    # --- ввод -----------------------------------------------------------------
    def step(self, events=None, dt=None):
        self.app.step(self.dt if dt is None else dt, list(events or []))

    def click(self, pos, button=1, mods=0):
        MOUSE[0] = (int(pos[0]), int(pos[1]))
        MODS[0] = mods
        self.step([pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=MOUSE[0], button=button)])
        self.step([pygame.event.Event(pygame.MOUSEBUTTONUP, pos=MOUSE[0], button=button)])
        MODS[0] = 0

    def key(self, k, mods=0):
        self.step([pygame.event.Event(pygame.KEYDOWN, key=k, mod=mods)])

    def drag(self, a, b):
        MOUSE[0] = a
        self.step([pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=a, button=1)])
        MOUSE[0] = b
        self.step([pygame.event.Event(pygame.MOUSEMOTION, pos=b, rel=(0, 0), buttons=(1, 0, 0))])
        self.step([pygame.event.Event(pygame.MOUSEBUTTONUP, pos=b, button=1)])

    def button(self, label: str):
        scene = self.app.top
        buttons = [b for b in scene.menu_buttons() if b.label == label and b.enabled]
        if not buttons:
            raise Fail(f"нет кнопки «{label}» на {type(scene).__name__}: "
                       f"{[b.label for b in scene.menu_buttons()]}")
        self.click(buttons[0].rect.center)
        self.step()

    # --- сцена ----------------------------------------------------------------
    @property
    def scene(self) -> GameScene:
        top = self.app.top
        if not isinstance(top, GameScene):
            raise Fail(f"ожидалась игра, а сверху {type(top).__name__}")
        return top

    @property
    def st(self):
        return self.scene.sim.state

    def now(self) -> float:
        return self.st.elapsed_ms / 1000

    def screen(self, x: float, y: float):
        self.scene.center_camera(x, y)
        return self.scene._screen_pos(x, y)

    def world_click(self, x, y, button=1, mods=0):
        pos = self.screen(x, y)
        if not (HUD_HEIGHT <= pos[1] < PANEL_TOP):
            self.log(f"  ! точка ({x},{y}) вне игрового поля на экране: {pos}")
        self.click(pos, button, mods)

    def shot(self, name: str):
        self.shot_n += 1
        path = self.out / f"m{self.mission}_{self.shot_n:02d}_{name}.png"
        pygame.image.save(self.app.screen, path)

    def watch_hints(self):
        scene = self.scene
        original = scene.show_hint

        def show_hint(message, color=theme.ALARM):
            t = scene.sim.state.elapsed_ms / 1000
            if not self.hints or self.hints[-1][1] != message:
                self.hints.append((t, message))
                self.log(f"  [{t:6.0f} с] подсказка: {message}")
            original(message, color)

        scene.show_hint = show_hint

    # --- данные ---------------------------------------------------------------
    def mine(self, type_=None, kind="units"):
        items = self.st.units if kind == "units" else self.st.buildings
        return [i for i in items if i.side == "player" and (type_ is None or i.type == type_)]

    def fighters(self, side="player"):
        return [u for u in self.st.units if u.side == side and self.scene.sim.is_fighter(u)]

    def metal(self):
        return self.st.colonies["player"].resources["metal"]

    def base(self):
        return self.st.map.bases["player"]

    def enemy_dome(self):
        return next((b for b in self.st.buildings if b.side == "vector" and b.type == "dome"), None)

    # --- действия как у человека ---------------------------------------------------
    def select_drone(self, prefer=("gathering", "to_resource", "returning", "idle")):
        drones = [u for u in self.mine("drone") if u.task in prefer]
        if not drones:
            return None
        drones.sort(key=lambda u: (prefer.index(u.task), u.id))
        d = drones[0]
        self.world_click(d.x, d.y)
        sel = self.scene.own_units()
        if not sel or sel[0].id != d.id:
            # Промахнулись (дрон уехал) — выберем свободного через «.»
            self.key(pygame.K_PERIOD)
            sel = self.scene.own_units()
        return sel[0] if sel else None

    def place_tile(self, type_, anchor: Point, radius=9):
        bal = self.scene.sim.balance
        needs = bal.buildings[type_].needs
        cands = []
        if needs == "ore":
            for d in self.st.deposits:
                if d.amount > 0:
                    cands += d.tiles
        elif needs == "ice":
            if isinstance(anchor, list):
                cands = list(anchor)
                anchor = cands[len(cands) // 2]
            else:
                w = self.st.map.width
                cands = [Point(i % w, i // w) for i, t in enumerate(self.st.map.tiles) if t == "ice"]
        else:
            cands = [Point(anchor.x + dx, anchor.y + dy) for dy in range(-radius, radius + 1)
                     for dx in range(-radius, radius + 1)]
        cands.sort(key=lambda p: (distance(anchor.x, anchor.y, p.x, p.y), p.y, p.x))
        for p in cands:
            if needs is None:
                # Человек оставляет проходы: не впритык к другим зданиям и не на руде.
                if any(max(abs(b.x - p.x), abs(b.y - p.y)) <= 1 for b in self.st.buildings):
                    continue
                if any(max(abs(t.x - p.x), abs(t.y - p.y)) <= 1 for d in self.st.deposits for t in d.tiles):
                    continue
            if can_place(self.st, bal, "player", type_, p.x, p.y).ok:
                return p
        return None

    def build(self, type_, anchor=None) -> bool:
        bal = self.scene.sim.balance
        if self.metal() < bal.buildings[type_].cost:
            return False
        tile = self.place_tile(type_, anchor if anchor is not None else self.base())
        if tile is None:
            self.log(f"  ! нет места для {type_}")
            return False
        drone = self.select_drone()
        if drone is None:
            return False
        before = len(self.mine(type_, "buildings"))
        self.key(pygame.K_b)
        if self.scene.menu != "build":
            self.log(f"  ! B не открыл меню стройки (выделено {[u.type for u in self.scene.own_units()]})")
            return False
        self.key(BUILD_KEY[type_])
        if self.scene.placing != type_:
            self.log(f"  ! клавиша здания {type_} не включила установку; команды: "
                     f"{[c.arg for c in self.scene.panel.commands]}")
            self.key(pygame.K_ESCAPE)
            return False
        self.world_click(tile.x, tile.y)
        ok = len(self.mine(type_, "buildings")) > before
        self.log(f"  {self.now():6.0f} с: стройка {type_} в ({tile.x},{tile.y}) — {'ок' if ok else 'НЕТ'}")
        if not ok:
            self.key(pygame.K_ESCAPE)
        return ok

    def train(self, producer_type, key) -> bool:
        producers = [b for b in self.mine(producer_type, "buildings") if b.complete]
        if not producers:
            return False
        b = min(producers, key=lambda b: (len(b.queue), b.id))
        if len(b.queue) >= 2:
            return False
        self.world_click(b.x, b.y)
        if self.scene.own_building() is None or self.scene.own_building().id != b.id:
            self.log(f"  ! щелчок не выбрал {producer_type} ({b.x},{b.y}); выбрано {self.scene.selected}")
            return False
        n = len(b.queue)
        self.key(key)
        return len(b.queue) > n

    def idle_to_work(self):
        for _ in range(4):
            idle = [u for u in self.mine("drone") if u.task == "idle"]
            if not idle:
                return
            self.key(pygame.K_PERIOD)
            sel = self.scene.own_units()
            if not sel:
                return
            d = sel[0]
            deps = [dp for dp in self.st.deposits if dp.amount > 0]
            if not deps:
                return
            dep = min(deps, key=lambda dp: min(distance(d.x, d.y, t.x, t.y) for t in dp.tiles))
            t = min(dep.tiles, key=lambda t: distance(d.x, d.y, t.x, t.y))
            self.world_click(t.x, t.y, button=3)

    def select_army(self) -> list:
        fs = self.fighters()
        if not fs:
            return []
        cx = sum(u.x for u in fs) / len(fs)
        cy = sum(u.y for u in fs) / len(fs)
        self.scene.center_camera(cx, cy)
        self.step()
        self.drag((4, HUD_HEIGHT + 4), (theme.SCREEN_SIZE[0] - 4, PANEL_TOP - 4))
        return [u for u in self.scene.own_units() if self.scene.sim.is_fighter(u)]

    def attack(self, x, y, what):
        army = self.select_army()
        if not army:
            return False
        self.key(pygame.K_f)
        if self.scene.targeting != "attack":
            self.log(f"  ! F не включил атаку; команды {[c.action for c in self.scene.panel.commands]}")
            return False
        self.world_click(x, y)
        self.log(f"  {self.now():6.0f} с: атака {len(army)} бойцами → {what} ({x},{y})")
        self.attack_sent_at = self.now()
        return True

    # --- партия ---------------------------------------------------------------------
    def think(self):
        st, sim = self.st, self.scene.sim
        t = self.now()
        bal = sim.balance
        self.idle_to_work()
        drones = len(self.mine("drone")) + sum(1 for b in self.mine(None, "buildings") for q in b.queue if q.type == "drone")
        have = {b.type for b in self.mine(None, "buildings")}
        count = lambda ty: len(self.mine(ty, "buildings"))
        colony = st.colonies["player"]
        # Экономика по порядку, как в подсказках README.
        plan = ["oxy_gen", "solar", "ice_drill", "regolith", "hangar", "solar"]
        if self.mission >= 2:
            plan += ["reactor", "oxy_gen"]
        building_now = any(not b.complete for b in self.mine(None, "buildings"))
        if drones < 7 and self.metal() >= 30 and t > 2:
            self.train("dome", pygame.K_q)
        for i, ty in enumerate(plan):
            need = plan[: i + 1].count(ty)
            if count(ty) < need:
                if not building_now or self.metal() > 200:
                    self.build(ty)
                break
        # Энергия и кислород «по ощущениям».
        if colony.resources["energy"] < 30 and colony.last_delta["energy"] < 0 and not building_now:
            self.build("reactor" if self.mission >= 2 and "reactor" not in have else "solar")
        if colony.resources["oxygen"] < 30 and colony.last_delta["oxygen"] < 0 and "oxy_gen" in have:
            self.build("oxy_gen")
        # Лимит армии: «Нужен генератор кислорода» — строим ещё генератор (и бур, если вода в минусе).
        used = supply_used(st, bal, "player") + supply_reserved(st, bal, "player")
        building_types = {b.type for b in self.mine(None, "buildings") if not b.complete}
        if used >= supply_cap(st, bal, "player") - 1 and "oxy_gen" not in building_types and t > 60:
            if colony.last_delta["water"] < 0 and "ice_drill" not in building_types:
                self.build("ice_drill")
            else:
                self.build("oxy_gen")
        if colony.last_delta["energy"] < 0 and colony.resources["energy"] < 80 and "solar" not in building_types:
            self.build("solar")
        # Армия (дроны важнее: если их мало, металл копим на дронов).
        if "hangar" in have and self.metal() >= 60 and (len(self.mine("drone")) >= 5 or self.metal() >= 90):
            rockets = len(self.mine("rocket_rover"))
            guards = len(self.mine("guard_rover"))
            if "reactor" in have and self.mission >= 2 and rockets * 2 < guards:
                self.train("hangar", pygame.K_z) or self.train("hangar", pygame.K_q)
            else:
                self.train("hangar", pygame.K_q)
        if self.mission == 2 and t > 200:
            self.ice_war()
        if self.mission == 3 and t > 420:
            self.great_dome()
        # Оборона и атака.
        enemy_near = [u for u in self.fighters("vector")
                      if any(distance(u.x, u.y, b.x, b.y) <= 7 for b in self.mine(None, "buildings"))]
        fs = self.fighters()
        if enemy_near and fs and t - self.attack_sent_at > 8:
            e = enemy_near[0]
            self.attack(round(e.x), round(e.y), "защита базы")
        elif (self.mission == 3 and fs and t - self.attack_sent_at > 30
              and any(b.side == "vector" and b.type == "great_dome" for b in self.st.buildings)):
            gd = next(b for b in self.st.buildings if b.side == "vector" and b.type == "great_dome")
            self.attack(gd.x, gd.y, "Большой купол ВЕКТОРа (по подсказке)")
        elif len(fs) >= (6 if self.mission == 1 else 7) and t - self.attack_sent_at > 60:
            target = self.attack_target()
            if target is not None:
                self.attack(target.x, target.y, target.type)
        # Группа и пауза — по разу.
        if not self.grouped and len(fs) >= 3:
            self.select_army()
            self.key(pygame.K_1, pygame.KMOD_CTRL)
            self.key(pygame.K_1)
            self.grouped = True
            self.log(f"  {t:6.0f} с: группа 1 = {len(self.scene.selected)}")
        if not self.paused_once and t > 90:
            self.key(pygame.K_ESCAPE)
            name = type(self.app.top).__name__
            self.shot("pause")
            self.button("Продолжить")
            self.paused_once = True
            self.log(f"  {t:6.0f} с: пауза ({name}) и продолжить")

    def attack_target(self):
        st = self.st
        if self.mission == 2:
            # Как советует подсказка: отбить поле — бур ВЕКТОРа на центральном поле, потом турель рядом.
            fields = st.map.ice_fields
            center = set(fields[len(fields) // 2])
            drills = [b for b in st.buildings if b.side == "vector" and b.type == "ice_drill" and Point(b.x, b.y) in center]
            if drills:
                return drills[0]
            turrets = [b for b in st.buildings if b.side == "vector" and b.type == "turret"
                       and any(distance(b.x, b.y, p.x, p.y) < 4 for p in center)]
            if turrets:
                return turrets[0]
            return None
        if self.mission == 3:
            gd = next((b for b in st.buildings if b.side == "vector" and b.type == "great_dome"), None)
            if gd is not None:
                return gd
        return self.enemy_dome()

    def ice_war(self):
        fields = self.st.map.ice_fields
        center = fields[len(fields) // 2]
        mine_on = lambda f: any(b.side == "player" and b.type == "ice_drill" and Point(b.x, b.y) in set(f)
                               for b in self.st.buildings)
        if not mine_on(center):
            self.build("ice_drill", center)
        elif not any(b.side == "player" and b.type == "turret" for b in self.st.buildings):
            c = center[len(center) // 2]
            self.build("turret", Point(c.x, c.y))

    def great_dome(self):
        site = next((b for b in self.mine("great_dome", "buildings")), None)
        if site is None:
            if self.build("great_dome"):
                self.shot("great_dome_site")
            return
        if site.complete or self.great_dome_helped >= 3:
            return
        drone = self.select_drone(("gathering", "to_resource", "idle"))
        if drone is not None:
            self.world_click(site.x, site.y, button=3)
            self.great_dome_helped += 1
            self.log(f"  {self.now():6.0f} с: дрон {drone.id} → Большой купол")

    def play(self, max_sec: float, think_every: float = 2.0):
        self.watch_hints()
        self.shot("start")
        next_think = 0.0
        next_shot = 60.0
        last_report = 0.0
        while self.scene.sim.state.outcome is None and self.now() < max_sec:
            if self.now() >= next_think:
                self.think()
                next_think = self.now() + think_every
            self.step()
            if self.now() >= next_shot:
                self.shot(f"t{int(self.now())}")
                next_shot += 180
            if self.now() - last_report >= 120:
                last_report = self.now()
                c = self.st.colonies["player"]
                self.log(f"  [{self.now():5.0f} с] металл {c.resources['metal']} E {c.resources['energy']} "
                         f"O2 {c.resources['oxygen']} H2O {c.resources['water']} дронов {len(self.mine('drone'))} "
                         f"бойцов {len(self.fighters())}/{len(self.fighters('vector'))} "
                         f"зданий {len(self.mine(None, 'buildings'))} hold {dict(self.st.ice_hold_sols)}")
        outcome = self.scene.sim.state.outcome
        self.shot("end")
        return outcome


def go_to_mission(h: Human, mission: int, difficulty: str | None):
    app = h.app
    app.start("boot")
    for _ in range(400):
        h.step()
        if type(app.top).__name__ == "MenuScene":
            break
    else:
        raise Fail(f"экран загрузки не сменился меню: {type(app.top).__name__}")
    h.shot("menu")
    h.button("Играть")
    if difficulty:
        scene = app.top
        while app.difficulty != difficulty:
            scene.change_difficulty(1)
    labels = [b.label for b in app.top.menu_buttons()]
    h.log(f"  миссии: {labels}")
    if mission > 1 and not app.profile.mission_unlocked(mission):
        h.click(app.top.lock_buttons[mission].rect.center)
        h.step()
        h.shot("shop")
        h.button("Купить (демо)")
        h.shot("shop_dialog")
        h.button("Оплатить (демо)")
        h.shot("shop_bought")
        back = [b.label for b in app.top.menu_buttons()]
        h.log(f"  магазин после покупки: {back}")
        h.click(app.top.back.rect.center)
        h.step()
    h.shot("missions")
    scene = app.top
    h.click(scene.play_buttons[mission].rect.center)
    h.step()
    if not isinstance(app.top, GameScene):
        raise Fail(f"«Начать» не запустил игру: {type(app.top).__name__}")
    if app.top.sim.state.mission != mission:
        raise Fail(f"запущена миссия {app.top.sim.state.mission} вместо {mission}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--mission", type=int, default=1)
    p.add_argument("--difficulty", default="normal")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--out", type=Path, default=Path("playtest_out"), help="папка для лога и снимков")
    p.add_argument("--max-sec", type=float, default=1500)
    p.add_argument("--frame-ms", type=float, default=66.7)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    logf = (a.out / f"m{a.mission}_{a.difficulty}_s{a.seed}.log").open("w", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    tmp = Path(tempfile.mkdtemp()) / "profile.sqlite"
    app = App(window_flags=0, seed=a.seed, profile=Profile(tmp))
    h = Human(app, a.mission, a.out, a.frame_ms, log)
    t0 = time.time()
    try:
        go_to_mission(h, a.mission, a.difficulty)
        log(f"миссия {a.mission}, сложность {a.difficulty}, seed {a.seed}")
        outcome = h.play(a.max_sec)
        log(f"ИТОГ: {outcome} на {h.now():.0f} с; подсказок {len(h.hints)}")
        # Экран итогов
        for _ in range(200):
            h.step()
            if type(app.top).__name__ == "ResultScene":
                break
        name = type(app.top).__name__
        log(f"после партии сцена: {name}; кнопки {[b.label for b in app.top.menu_buttons()] if name == 'ResultScene' else '-'}")
        if name == "ResultScene":
            h.shot("result")
            if outcome is not None and outcome.winner == "player" and a.mission < 3:
                h.button("Следующая миссия")
                top = app.top
                log(f"«Следующая миссия» → {type(top).__name__}, миссия {getattr(getattr(top, 'sim', None), 'state', None) and top.sim.state.mission}")
                h.step()
                h.shot("next_mission")
        log(f"профиль: есть результат миссий {[m for m in (1, 2, 3) if app.profile.best_score(m) is not None]}")
    except Exception:
        log("ОШИБКА:\n" + traceback.format_exc())
        try:
            h.shot("error")
        except Exception:
            pass
        failed = True
    else:
        failed = False
    log(f"время прогона {time.time() - t0:.0f} с")
    logf.close()
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
