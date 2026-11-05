"""Замер FPS (НФТ-02): python -m tools.bench_fps [--units 60] [--frames 300] [--low] [--window]
[--gestures off|keys|camera] [--camera N].

Партия «бот против бота» прокручивается на минуту, затем на карту добавляются юниты до --units,
и меряется время полного кадра App.step (логика + отрисовка всех слоёв). Без --window окно
не открывается (SDL dummy) — замер тогда без вывода на экран и без vsync.

--gestures keys — весь замер зажата F3 (палец вверх) и включён оверлей F9: работают маппер,
индикатор и оверлей. --gestures camera — распознавание с камеры в своём потоке (кадры никуда
не сохраняются); замер начинается, когда камера заработала или стало ясно, что её нет.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--units", type=int, default=60)
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--low", action="store_true", help="пресет слабого ноутбука")
    parser.add_argument("--window", action="store_true", help="настоящее окно с pygame.display.flip()")
    parser.add_argument("--gestures", choices=("off", "keys", "camera"), default="off", help="жесты во время замера")
    parser.add_argument("--camera", type=int, default=0, help="номер камеры для --gestures camera")
    args = parser.parse_args(argv)
    if not args.window:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    import pygame

    from reddome.app import App
    from reddome.config.camera import CameraSettings
    from reddome.config.graphics import GraphicsSettings
    from reddome.scenes.game import GameScene
    from reddome.sim.state import add_unit, find_free_tile_near
    from reddome.sim.types import SIDES, Point

    pygame.mouse.get_focused = lambda: False  # type: ignore[assignment]
    pygame.mouse.get_pos = lambda: (640, 300)  # type: ignore[assignment]
    graphics = GraphicsSettings.low() if args.low else GraphicsSettings()
    camera = CameraSettings(enabled=args.gestures == "camera", index=args.camera, keys=args.gestures == "keys")
    app = App(graphics=graphics, camera=camera, window_flags=pygame.SCALED if args.window else 0)
    app.gestures.log = None  # замер FPS не пишет лог жестов
    if args.gestures == "camera":
        deadline = time.monotonic() + 20
        while app.gestures.status == "starting" and time.monotonic() < deadline:
            app.step(16, pygame.event.get() if args.window else [])
            time.sleep(0.05)
        print(f"Камера: {app.gestures.status} — {app.gestures.status_text}")
    app.start("game", autoplay=True)
    app.step(16, [])
    scene = app.top
    assert isinstance(scene, GameScene)
    sim = scene.sim
    sim.update(60_000)
    scene.world.handle_events(sim.drain_events())

    # Добавляем юнитов поровну сторонам, в центре карты — там их видно камерой.
    center = Point(sim.state.map.width // 2, sim.state.map.height // 2)
    i = 0
    while len(sim.state.units) < args.units:
        side = SIDES[i % 2]
        spot = find_free_tile_near(sim.state, Point(center.x - 4 + i % 9, center.y - 3 + (i // 9) % 7), max_radius=8)
        if spot is None:
            break
        add_unit(sim.state, sim.balance, side, "guard_rover" if i % 3 else "drone", spot)
        i += 1
    scene.center_camera(center.x, center.y)
    scene.select([u.id for u in sim.state.units if u.side == "player"])

    units_at_start = len(sim.state.units)
    if args.gestures != "off":
        app.gestures.overlay = True
    if args.gestures == "keys":
        app.step(1000 / 60, [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F3, mod=0)])
    times: list[float] = []
    for _ in range(args.frames):
        start = time.perf_counter()
        app.step(1000 / 60, pygame.event.get() if args.window else [])
        if args.window:
            pygame.display.flip()
        times.append((time.perf_counter() - start) * 1000)
    recognition_fps = app.gestures.fps
    app.gestures.stop()
    pygame.quit()

    mean = statistics.fmean(times)
    worst = sorted(times)[int(len(times) * 0.95)]
    print(f"Юнитов на карте: {units_at_start} в начале замера, {len(sim.state.units)} в конце; зданий: {len(sim.state.buildings)}, "
          f"частиц: {len(scene.world.effects.particles)}")
    print(f"Режим: {'окно' if args.window else 'без окна'}, графика: {'low' if args.low else 'полная'}, "
          f"жесты: {args.gestures}" + (f", распознавание {recognition_fps:.0f} к/с" if args.gestures == "camera" else ""))
    print(f"Кадр: в среднем {mean:.1f} мс → {1000 / mean:.0f} FPS; 95-й перцентиль {worst:.1f} мс → {1000 / worst:.0f} FPS")


if __name__ == "__main__":
    main()
