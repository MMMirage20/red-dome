"""Команды жестов в игре через App.step (SDL dummy, без камеры и без mediapipe): фейковый источник
кладёт кадры, App прогоняет их через маппер и отдаёт команду сцене — как в настоящей игре."""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import math  # noqa: E402
from collections.abc import Iterator  # noqa: E402

import pygame  # noqa: E402
import pytest  # noqa: E402

from reddome.app import App  # noqa: E402
from reddome.input.gestures import GestureFrame, Hand, SourceResult, SourceStatus  # noqa: E402
from reddome.scenes.game import CAMERA_WARNING, GameScene  # noqa: E402
from reddome.scenes.pause import PauseScene  # noqa: E402
from reddome.sim.state import add_unit, chebyshev, find_free_tile_near  # noqa: E402
from tests.helpers import add_rovers  # noqa: E402

FRAME_MS = 1000 / 60


class FakeSource:
    """Источник с камеры без камеры: тест сам кладёт результаты в «слот»."""

    name = "camera"

    def __init__(self, status: SourceStatus = "running") -> None:
        self._status = status
        self.pending: list[SourceResult] = []

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def poll(self) -> SourceResult | None:
        return self.pending.pop(0) if self.pending else None

    @property
    def status(self) -> SourceStatus:
        return self._status

    @property
    def status_text(self) -> str:
        return "фейковый источник"

    @property
    def fps(self) -> float:
        return 30.0


@pytest.fixture(scope="module")
def app() -> Iterator[App]:
    application = App(window_flags=0)
    yield application
    pygame.quit()


@pytest.fixture
def source(app: App) -> FakeSource:
    fake = FakeSource()
    app.gestures.use_source(fake)
    app.gestures.mapper.reset()
    return fake


@pytest.fixture
def scene(app: App, source: FakeSource, monkeypatch: pytest.MonkeyPatch) -> GameScene:
    monkeypatch.setattr(pygame.mouse, "get_focused", lambda: False)
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (640, 300))
    app.start("game")
    app.step(FRAME_MS, [])
    game = app.top
    assert isinstance(game, GameScene)
    return game


def show(app: App, source: FakeSource, gesture: str, hand: Hand, hold_ms: float) -> None:
    """Держать жест hold_ms (плюс кадр запаса), затем опустить руку и переждать cooldown."""
    frames = math.ceil(hold_ms / FRAME_MS) + 2
    for _ in range(frames):
        source.pending.append(SourceResult([GestureFrame(gesture, 0.95, 0.0, hand)]))
        app.step(FRAME_MS, [])
    source.pending.append(SourceResult([]))
    app.step(FRAME_MS, [])
    for _ in range(int(app.balance.gestures.cooldown_ms / FRAME_MS) + 2):
        app.step(FRAME_MS, [])


def drones(scene: GameScene) -> list[int]:
    return [u.id for u in scene.player_units("drone")]


def test_left_palm_selects_one_drone_and_next_on_repeat(app: App, source: FakeSource, scene: GameScene) -> None:
    hold = app.balance.gestures.hold_ms
    show(app, source, "Open_Palm", "left", hold)
    first = list(scene.selected)
    assert len(first) == 1 and first[0] in drones(scene)
    show(app, source, "Open_Palm", "left", hold)
    second = list(scene.selected)
    assert len(second) == 1 and second[0] in drones(scene) and second != first
    assert scene.commander_action_until > scene.time_ms - 1000  # Аян отдаёт приказ


def test_right_palm_selects_all_rovers(app: App, source: FakeSource, scene: GameScene) -> None:
    rovers = add_rovers(scene.sim, "player", 3)
    show(app, source, "Open_Palm", "right", app.balance.gestures.hold_ms)
    assert sorted(scene.selected) == sorted(r.id for r in rovers)


def test_right_palm_and_thumb_down_include_rocket_rovers(app: App, source: FakeSource, scene: GameScene) -> None:
    """Миссии 2–3: «все роверы» и «отступить» — это и ракетные роверы, а не только охранные."""
    guards = add_rovers(scene.sim, "player", 2)
    base = scene.sim.state.map.bases["player"]
    rocket = add_unit(scene.sim.state, scene.sim.balance, "player", "rocket_rover", find_free_tile_near(scene.sim.state, base))
    show(app, source, "Open_Palm", "right", app.balance.gestures.hold_ms)
    assert sorted(scene.selected) == sorted([*(r.id for r in guards), rocket.id])
    scene.select([])
    rocket.x += 8
    show(app, source, "Thumb_Down", "right", app.balance.gestures.hold_ms)
    assert rocket.task == "moving"


def vector_dome_near(scene: GameScene, unit_id: int) -> bool:
    dome = next(b for b in scene.sim.state.buildings if b.side == "vector" and b.type == "dome")
    unit = next(u for u in scene.sim.state.units if u.id == unit_id)
    return unit.attack_point is not None and chebyshev(unit.attack_point.x, unit.attack_point.y, dome.x, dome.y) <= 2


def test_pointing_up_sends_selected_rovers_and_not_drones(app: App, source: FakeSource, scene: GameScene) -> None:
    rovers = add_rovers(scene.sim, "player", 3)
    drone = drones(scene)[0]
    scene.select([rovers[0].id, rovers[1].id, drone])
    show(app, source, "Pointing_Up", "right", app.balance.gestures.attack_hold_ms)
    for rover in rovers[:2]:
        assert rover.task == "attack_move" and vector_dome_near(scene, rover.id)
    assert rovers[2].task == "idle"
    assert next(u for u in scene.sim.state.units if u.id == drone).task == "idle"


def test_pointing_up_without_selected_rovers_sends_all_rovers(app: App, source: FakeSource, scene: GameScene) -> None:
    rovers = add_rovers(scene.sim, "player", 2)
    scene.select([])
    show(app, source, "Pointing_Up", "left", app.balance.gestures.attack_hold_ms)
    assert all(r.task == "attack_move" and vector_dome_near(scene, r.id) for r in rovers)


def test_pointing_up_needs_attack_hold(app: App, source: FakeSource, scene: GameScene) -> None:
    rovers = add_rovers(scene.sim, "player", 1)
    show(app, source, "Pointing_Up", "right", app.balance.gestures.hold_ms)  # короче attack_hold_ms
    assert rovers[0].task == "idle"


def test_thumb_up_sends_idle_drones_to_mine(app: App, source: FakeSource, scene: GameScene) -> None:
    show(app, source, "Thumb_Up", "right", app.balance.gestures.hold_ms)
    tasks = {u.task for u in scene.player_units("drone")}
    assert tasks <= {"to_resource", "gathering", "waiting"}
    assert scene.hint.startswith("Жест:")


def test_thumb_down_retreats_all_rovers(app: App, source: FakeSource, scene: GameScene) -> None:
    rovers = add_rovers(scene.sim, "player", 2)
    scene.select([])
    show(app, source, "Thumb_Down", "left", app.balance.gestures.hold_ms)
    assert all(r.task == "moving" for r in rovers)
    assert scene.hint.startswith("Жест:")


def test_victory_left_queues_drone_in_dome(app: App, source: FakeSource, scene: GameScene) -> None:
    metal = scene.sim.state.colonies["player"].resources["metal"]
    show(app, source, "Victory", "left", app.balance.gestures.hold_ms)
    dome = next(b for b in scene.sim.state.buildings if b.side == "player" and b.type == "dome")
    assert [item.type for item in dome.queue] == ["drone"]
    assert scene.sim.state.colonies["player"].resources["metal"] == metal - app.balance.units["drone"].cost


def test_victory_right_without_hangar_shows_reason_and_keeps_metal(app: App, source: FakeSource, scene: GameScene) -> None:
    metal = scene.sim.state.colonies["player"].resources["metal"]
    show(app, source, "Victory", "right", app.balance.gestures.hold_ms)
    assert scene.hint == "Нужен ангар"
    assert scene.sim.state.colonies["player"].resources["metal"] == metal


def test_ily_opens_and_closes_pause(app: App, source: FakeSource, scene: GameScene) -> None:
    pause_ms = app.balance.gestures.pause_hold_ms
    show(app, source, "ILoveYou", "right", pause_ms)
    assert isinstance(app.top, PauseScene)
    show(app, source, "ILoveYou", "left", pause_ms)
    assert app.top is scene


def test_right_fist_in_mission_one_only_explains(app: App, source: FakeSource, scene: GameScene) -> None:
    """Ракетного ровера в миссии 1 нет: кулак правой роверов не трогает, а объясняет почему."""
    rovers = add_rovers(scene.sim, "player", 1)
    show(app, source, "Closed_Fist", "right", 2000)
    assert rovers[0].task == "idle" and scene.selected == []
    assert "недоступен" in scene.hint


def test_unavailable_camera_keeps_game_running_with_warning(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pygame.mouse, "get_focused", lambda: False)
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (640, 300))
    app.gestures.use_source(FakeSource("no_camera"))
    app.start("game")
    for _ in range(30):
        app.step(FRAME_MS, [])
    game = app.top
    assert isinstance(game, GameScene)
    assert game.hint == CAMERA_WARNING
    assert game.sim.state.elapsed_ms > 0
