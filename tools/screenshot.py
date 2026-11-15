"""Скриншоты без окна (B7): python -m tools.screenshot [--seed N] [--out docs/screenshots].

Окно не открывается (SDL dummy). За обе стороны играют боты, мышь подменяется, чтобы показать
рамку, подсказки и призрак здания. Снимки: загрузка, меню, старт, добыча и стройка, меню стройки,
ночь, бой, пауза, итоги и жесты (индикатор удержания, оверлей F9 без камеры, памятка в паузе).

Камера здесь не открывается никогда: жесты эмулируются клавишами F1–F8, а для оверлея
подставлен источник со статусом «нет камеры» — кадров с камеры на снимках быть не может.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from reddome.app import App  # noqa: E402
from reddome.config.camera import CameraSettings  # noqa: E402
from reddome.input.gestures import SourceResult, SourceStatus  # noqa: E402
from reddome.scenes.game import GameScene  # noqa: E402
from reddome.sim.types import SimEvent, Unit  # noqa: E402
from reddome.ui.panel import slot_rect  # noqa: E402

FRAME_MS = 1000 / 60
BATTLE_SHOTS = 12
#: Мышь без окна стоит в (0, 0) и двигала бы камеру краем экрана, поэтому подменяем её.
MOUSE = [(640, 300)]
pygame.mouse.get_focused = lambda: False  # type: ignore[assignment]
pygame.mouse.get_pos = lambda: MOUSE[0]  # type: ignore[assignment]


class NoCameraSource:
    """Источник «камера не открылась» — для снимка оверлея F9; камеру не трогает."""

    name = "camera"

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def poll(self) -> SourceResult | None:
        return None

    @property
    def status(self) -> SourceStatus:
        return "no_camera"

    @property
    def status_text(self) -> str:
        return "камера 0 не открылась"

    @property
    def fps(self) -> float:
        return 0.0


def frames(app: App, count: int, events: list[pygame.event.Event] | None = None) -> None:
    for i in range(count):
        app.step(FRAME_MS, list(events or []) if i == 0 else [])


def key_event(kind: int, key: int) -> pygame.event.Event:
    return pygame.event.Event(kind, key=key, mod=0)


def fast_forward(scene: GameScene, ms: int, battle: bool = False) -> SimEvent | None:
    """Прокрутка партии без отрисовки; эффекты получают события, чтобы не копились.

    battle=True — остановиться, когда за последние 2 с было не меньше BATTLE_SHOTS выстрелов.
    """
    elapsed = 0
    shots: list[tuple[int, SimEvent]] = []
    while elapsed < ms and scene.sim.state.outcome is None:
        scene.sim.update(100)
        events = scene.sim.drain_events()
        scene.world.handle_events(events)
        scene.world.update(100, scene.sim)
        scene.time_ms += 100
        elapsed += 100
        if battle:
            shots = [(t, e) for t, e in shots if elapsed - t < 2000]
            shots += [(elapsed, e) for e in events if e.kind == "shot"]
            if len(shots) >= BATTLE_SHOTS:
                return shots[-1][1]
    return None


def save(app: App, out: Path, name: str) -> None:
    path = out / f"{name}.png"
    pygame.image.save(app.screen, path)
    print("сохранено:", path)


def game_scene(app: App) -> GameScene:
    scene = app.top
    assert isinstance(scene, GameScene)
    return scene


def player_units(scene: GameScene, type_: str, task: str | None = None) -> list[Unit]:
    return [u for u in scene.sim.state.units if u.side == "player" and u.type == type_ and (task is None or u.task == task)]


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, default=Path("docs/screenshots"))
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    app = App(seed=args.seed, window_flags=0, camera=CameraSettings(enabled=False, keys=True))
    app.gestures.log = None  # служебные нажатия F1–F9 не должны попадать в лог жестов для недели 4
    app.start("boot")
    frames(app, 3)
    save(app, args.out, "01_boot")
    while app.top is not None and type(app.top).__name__ == "BootScene":
        frames(app, 1)
    MOUSE[0] = (1030, 365)  # наведение на «Играть»
    frames(app, 30)
    save(app, args.out, "02_menu")

    app.start("missions")
    MOUSE[0] = (270, 515)  # наведение на «Начать»
    frames(app, 10)
    save(app, args.out, "13_missions")

    app.start("game", autoplay=True)
    frames(app, 2)
    scene = game_scene(app)
    scene.select([u.id for u in player_units(scene, "drone")])
    MOUSE[0] = (700, 300)
    frames(app, 90)
    save(app, args.out, "03_start")

    # Добыча и стройка: ~2,5 минуты, выделен добывающий дрон.
    fast_forward(scene, 150_000)
    site = next((b for b in scene.sim.state.buildings if b.side == "player" and not b.complete), None)
    gathering = player_units(scene, "drone", "gathering") or player_units(scene, "drone")
    focus = site or gathering[0]
    scene.center_camera(focus.x, focus.y)
    scene.select([gathering[0].id])
    frames(app, 40)
    save(app, args.out, "04_economy")

    # Жесты клавишами: F1 (ладонь левой) срабатывает и даёт вспышку, F3 (палец вверх) держим наполовину.
    hold = app.balance.gestures
    frames(app, int(hold.hold_ms / FRAME_MS) + 3, [key_event(pygame.KEYDOWN, pygame.K_F1)])
    frames(app, 1, [key_event(pygame.KEYUP, pygame.K_F1)])
    frames(app, int(hold.attack_hold_ms * 0.55 / FRAME_MS), [key_event(pygame.KEYDOWN, pygame.K_F3)])
    save(app, args.out, "10_gesture_hold")
    frames(app, 1, [key_event(pygame.KEYUP, pygame.K_F3)])

    # Оверлей F9 без камеры.
    app.gestures.use_source(NoCameraSource())
    frames(app, 2, [key_event(pygame.KEYDOWN, pygame.K_F9)])
    save(app, args.out, "11_gesture_overlay")
    frames(app, 1, [key_event(pygame.KEYDOWN, pygame.K_F9)])

    # Памятка жестов в паузе.
    app.push("pause", background=app.snapshot())
    frames(app, 2, [])
    frames(app, 2, [key_event(pygame.KEYDOWN, pygame.K_TAB)])
    save(app, args.out, "12_pause_gestures")
    app.pop()
    frames(app, 1)

    # Меню стройки: подсказка у кнопки бура и призрак бура над льдом.
    drones = player_units(scene, "drone")
    scene.select([d.id for d in drones[:3]])
    scene.menu = "build"
    frames(app, 2)
    base = scene.sim.state.map.bases["player"]
    scene.center_camera(base.x + 7, base.y - 4)
    scene.placing = "ice_drill"
    ice = (13, 21)
    MOUSE[0] = (int(ice[0] * 32 + 16 - scene.camera.x), int(ice[1] * 32 + 16 - scene.camera.y))
    frames(app, 2)
    # Кадр с призраком под мышью, поверх — подсказка кнопки бура (мышь одна, поэтому подсказку дорисовываем).
    metal = scene.sim.state.colonies["player"].resources["metal"]
    scene.panel.draw_tooltips(app.screen, metal, slot_rect(1).center)
    save(app, args.out, "05_build_menu")
    scene.placing = None
    scene.menu = ""

    # Ночь: ждём тёмную фазу сола.
    sol_ms = scene.sim.balance.sol_seconds * 1000
    while scene.sim.state.sol_elapsed_ms / sol_ms < 0.78 and scene.sim.state.outcome is None:
        fast_forward(scene, 1000)
    scene.center_camera(base.x + 2, base.y - 2)
    scene.select([])
    MOUSE[0] = (640, 300)
    frames(app, 20)
    save(app, args.out, "06_night")

    # Бой: ждём перестрелку и смотрим туда.
    shot = fast_forward(scene, 600_000, battle=True)
    if shot is not None:
        scene.center_camera((shot.x + shot.tx) / 2, (shot.y + shot.ty) / 2)
        rovers = player_units(scene, "guard_rover")
        scene.select([r.id for r in rovers])
        frames(app, 20)
        save(app, args.out, "07_battle")
    else:
        print("боя не случилось — 07_battle пропущен")

    if scene.sim.state.outcome is None:
        app.push("pause", background=app.snapshot())
        frames(app, 2)
        save(app, args.out, "08_pause")
        app.pop()
        frames(app, 1)

    # Итоги: доигрываем партию ботами до конца.
    fast_forward(scene, 1_200_000)
    if scene.sim.state.outcome is None:
        dome = next(b for b in scene.sim.state.buildings if b.side == "vector" and b.type == "dome")
        scene.sim.damage_building(dome.id, dome.hp)
    while type(app.top).__name__ != "ResultScene":
        frames(app, 1)
    MOUSE[0] = (510, 564)  # наведение на «Ещё раз»
    frames(app, 5)
    save(app, args.out, "09_result")
    pygame.quit()


if __name__ == "__main__":
    main()
