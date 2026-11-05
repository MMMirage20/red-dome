"""Замер точности жестов (заготовка цели SMART из ЛР8 — 85 % распознаваний):
python -m tools.gesture_bench [--trials 20] [--camera N] [--swap-hands] [--timeout 6] [--demo].

Открывает камеру без игры и окно с заданием: «Покажите: ладонь, левая рука (3/20)». Каждый жест
из таблицы ФТ-13 просится --trials раз; жесты «любой рукой» — попеременно левой и правой.
Попытка засчитана, если маппер с порогами из balance.json выдал нужную команду той рукой,
которую просили. Задержка — от первого кадра с нужным жестом до срабатывания.

Превью в окне только показывается: кадры камеры никуда не сохраняются. В CSV
ml/data/gesture_bench_ГГГГММДД_ЧЧММСС.csv — только названия жестов, руки и числа.
Esc — закончить досрочно, пробел — пропустить попытку.

--demo — без камеры: синтетический источник «показывает» нужный жест. Это проверка самого
инструмента, а не замер; так и пишется в отчёте.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

import pygame

from reddome.config.balance import load_balance
from reddome.config.camera import CameraSettings
from reddome.input.gestures import (
    COMMAND_TITLES,
    GESTURE_BINDINGS,
    GESTURE_TITLES,
    HAND_TITLES,
    GestureFrame,
    GestureMapper,
    GestureSource,
    Hand,
    SourceResult,
    SourceStatus,
)
from reddome.input.service import LOG_DIR
from reddome.ui import theme
from reddome.ui.icons import GESTURE_ICONS, icon

WINDOW = (960, 600)
REST_MS = 600
COLUMNS = ("trial", "expected_gesture", "expected_hand", "expected_command", "fired_command", "fired_hand",
           "fired_gesture", "score", "latency_ms", "result")


@dataclass
class Trial:
    gesture: str
    hand: Hand
    command: str
    fired_command: str = ""
    fired_hand: str = ""
    fired_gesture: str = ""
    score: float = 0.0
    latency_ms: float | None = None
    result: str = "timeout"


def plan_trials(count: int) -> list[Trial]:
    trials = []
    for (gesture, hand), command in GESTURE_BINDINGS.items():
        for i in range(count):
            actual: Hand = ("left" if i % 2 == 0 else "right") if hand == "any" else hand  # type: ignore[assignment]
            trials.append(Trial(gesture, actual, command))
    return trials


class DemoSource:
    """Синтетические кадры: через 0,3 с после задания «показывает» нужный жест нужной рукой."""

    name = "demo"

    def __init__(self) -> None:
        self.wanted: tuple[str, Hand] | None = None
        self.since = 0.0

    def ask(self, wanted: tuple[str, Hand] | None) -> None:
        self.wanted = wanted
        self.since = time.monotonic()

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def poll(self) -> SourceResult | None:
        if self.wanted is None or time.monotonic() - self.since < 0.3:
            return SourceResult([])
        return SourceResult([GestureFrame(self.wanted[0], 0.93, 0.0, self.wanted[1])])

    @property
    def status(self) -> SourceStatus:
        return "running"

    @property
    def status_text(self) -> str:
        return "демо без камеры"

    @property
    def fps(self) -> float:
        return 0.0


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trials", type=int, default=20, help="попыток на каждый жест (по умолчанию 20)")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--swap-hands", action="store_true")
    parser.add_argument("--timeout", type=float, default=6.0, help="секунд на попытку")
    parser.add_argument("--demo", action="store_true", help="без камеры, синтетические кадры (не замер)")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    balance = load_balance()
    settings = CameraSettings(index=args.camera, swap_hands=args.swap_hands)
    demo = DemoSource() if args.demo else None
    source: GestureSource
    if demo is not None:
        source = demo
    else:
        from reddome.input.camera import MediaPipeGestureSource

        source = MediaPipeGestureSource(settings)
    mapper = GestureMapper(balance.gestures, swap_hands=args.swap_hands)
    trials = plan_trials(args.trials)

    pygame.init()
    theme.reset_fonts()
    screen = pygame.display.set_mode(WINDOW)
    pygame.display.set_caption("Красный купол — замер жестов")
    clock = pygame.time.Clock()
    source.start()
    started = time.monotonic()

    index = 0
    phase = "rest"  # rest — ждём, пока рука опущена; ask — ждём жест
    phase_since = time.monotonic()
    first_seen: float | None = None
    frames: list[GestureFrame] = []
    preview = None
    aborted = False
    while index < len(trials):
        now = time.monotonic()
        now_ms = (now - started) * 1000
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                aborted = True
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE and phase == "ask":
                trials[index].result = "skipped"
                index, phase, phase_since = index + 1, "rest", now
        if aborted:
            break
        if index >= len(trials):
            break
        trial = trials[index]
        result = source.poll()
        if result is not None:
            frames = [replace(frame, time_ms=now_ms) for frame in result.frames]
            if result.preview is not None:
                preview = result.preview
            fired = mapper.feed(frames, now_ms)
            if phase == "rest":
                if frames:
                    phase_since = now
                elif now - phase_since >= REST_MS / 1000:
                    phase, phase_since, first_seen = "ask", now, None
                    mapper.reset()
                    if demo is not None:
                        demo.ask((trial.gesture, trial.hand))
            elif phase == "ask":
                if first_seen is None and any(f.gesture == trial.gesture for f in frames):
                    first_seen = now
                if fired is not None:
                    trial.fired_command, trial.fired_hand = fired.command, fired.hand
                    trial.fired_gesture, trial.score = fired.gesture, fired.score
                    if first_seen is not None:
                        trial.latency_ms = (now - first_seen) * 1000
                    ok_command = fired.command == trial.command
                    ok_hand = fired.hand == trial.hand
                    trial.result = "ok" if ok_command and ok_hand else "wrong_hand" if ok_command else "wrong_gesture"
                    index, phase, phase_since = index + 1, "rest", now
                    if demo is not None:
                        demo.ask(None)
        if phase == "ask" and now - phase_since > args.timeout:
            trial.result = "timeout"
            index, phase, phase_since = index + 1, "rest", now
            if demo is not None:
                demo.ask(None)
        if source.status in ("no_camera", "no_mediapipe", "no_model", "error"):
            print("Камера недоступна:", source.status_text)
            aborted = True
            break
        draw(screen, trials, index, phase, frames, preview, source)
        pygame.display.flip()
        clock.tick(60)
    source.stop()
    pygame.quit()
    report(trials[:index], args, aborted)


def draw(screen: pygame.Surface, trials: list[Trial], index: int, phase: str, frames: list[GestureFrame],
         preview: object, source: GestureSource) -> None:
    screen.fill(theme.PANEL)
    if index < len(trials):
        trial = trials[index]
        done = sum(1 for t in trials[:index] if t.gesture == trial.gesture and t.hand == trial.hand) + 1
        total = sum(1 for t in trials if t.gesture == trial.gesture and t.hand == trial.hand)
        if phase == "rest":
            theme.draw_text(screen, "Опустите руку", (40, 40), 40, theme.TEXT_QUIET, kind="title")
        else:
            theme.draw_text(screen, "Покажите:", (40, 30), 24, theme.TEXT_QUIET)
            screen.blit(icon(GESTURE_ICONS[trial.gesture], 96), (40, 70))
            theme.draw_text(screen, GESTURE_TITLES[trial.gesture], (150, 80), 40, theme.SAND, kind="title")
            theme.draw_text(screen, f"{HAND_TITLES[trial.hand]} рука", (150, 130), 30, theme.WARNING, kind="title")
            theme.draw_text(screen, f"команда: {COMMAND_TITLES[trial.command]}", (150, 172), 18, theme.TEXT_QUIET)
        theme.draw_text(screen, f"Попытка {done} из {total} · всего {index + 1} / {len(trials)}", (40, 220), 18, theme.TEXT)
    ok = sum(1 for t in trials[:index] if t.result == "ok")
    theme.draw_text(screen, f"Засчитано: {ok} из {index}", (40, 250), 18, theme.SUCCESS)
    for i, frame in enumerate(frames):
        text = f"{HAND_TITLES[frame.hand]}: {GESTURE_TITLES.get(frame.gesture, frame.gesture)} {frame.score:.2f}"
        theme.draw_text(screen, text, (40, 300 + i * 26), 20, theme.TEXT)
    theme.draw_text(screen, f"Источник: {source.status_text} · {source.fps:.0f} к/с", (40, WINDOW[1] - 60), 15,
                    theme.TEXT_QUIET)
    theme.draw_text(screen, "Esc — закончить, пробел — пропустить попытку", (40, WINDOW[1] - 34), 15, theme.TEXT_QUIET)
    view = pygame.Rect(WINDOW[0] - 360, 40, 320, 240)
    pygame.draw.rect(screen, (6, 10, 16), view)
    if preview is not None:
        array = preview  # numpy RGB 120 × 160 из потока камеры; только показ
        image = pygame.image.frombuffer(array.tobytes(), (array.shape[1], array.shape[0]), "RGB")  # type: ignore[attr-defined]
        screen.blit(pygame.transform.scale(image, view.size), view)
    pygame.draw.rect(screen, theme.PANEL_EDGE, view, 1)


def report(trials: list[Trial], args: argparse.Namespace, aborted: bool) -> None:
    if args.demo:
        print("ДЕМО: синтетические кадры без камеры — это проверка инструмента, а не замер точности.")
    if not trials:
        print("Попыток нет.")
        return
    out = args.out or LOG_DIR / f"gesture_bench_{datetime.now():%Y%m%d_%H%M%S}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(COLUMNS)
        for i, t in enumerate(trials, 1):
            writer.writerow((i, t.gesture, t.hand, t.command, t.fired_command, t.fired_hand, t.fired_gesture,
                             f"{t.score:.3f}", "" if t.latency_ms is None else round(t.latency_ms), t.result))
    print(f"CSV: {out}" + (" (замер прерван)" if aborted else ""))
    print(f"{'Жест':<14}{'Рука':<8}{'Верно':>7}{'Попыток':>9}{'Точность':>10}{'Чужая рука':>12}")
    keys = sorted({(t.gesture, t.hand) for t in trials}, key=lambda k: (list(GESTURE_TITLES).index(k[0]), k[1]))
    for gesture, hand in keys:
        group = [t for t in trials if t.gesture == gesture and t.hand == hand and t.result != "skipped"]
        if not group:
            continue
        ok = sum(1 for t in group if t.result == "ok")
        wrong_hand = sum(1 for t in group if t.result == "wrong_hand")
        print(f"{gesture:<14}{hand:<8}{ok:>7}{len(group):>9}{ok / len(group):>10.0%}{wrong_hand:>12}")
    counted = [t for t in trials if t.result != "skipped"]
    ok = sum(1 for t in counted if t.result == "ok")
    print(f"Всего: {ok} из {len(counted)} — {ok / max(1, len(counted)):.0%}")
    latencies = [t.latency_ms for t in counted if t.result == "ok" and t.latency_ms is not None]
    if latencies:
        print(f"Задержка от начала удержания до срабатывания: медиана {statistics.median(latencies):.0f} мс, "
              f"среднее {statistics.fmean(latencies):.0f} мс")


if __name__ == "__main__":
    main()
