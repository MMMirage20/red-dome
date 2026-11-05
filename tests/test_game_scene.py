"""Ввод игровой сцены без окна (SDL dummy): рамка, приказы ПКМ, стройка по горячим клавишам,
группы, свободный дрон, очередь сборки, мини-карта и пауза."""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from collections.abc import Iterator  # noqa: E402

import pygame  # noqa: E402
import pytest  # noqa: E402

from reddome.app import App  # noqa: E402
from reddome.scenes.game import GameScene  # noqa: E402
from reddome.scenes.pause import PauseScene  # noqa: E402
from reddome.sim.types import Point  # noqa: E402
from reddome.ui import panel  # noqa: E402
from tests.helpers import open_spot  # noqa: E402

FRAME_MS = 1000 / 60


@pytest.fixture(scope="module")
def app() -> Iterator[App]:
    application = App(window_flags=0)
    yield application
    pygame.quit()


@pytest.fixture
def scene(app: App, monkeypatch: pytest.MonkeyPatch) -> GameScene:
    # Мышь без окна стоит в (0, 0): без подмены камера уезжала бы краем экрана.
    monkeypatch.setattr(pygame.mouse, "get_focused", lambda: False)
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (640, 300))
    app.start("game")
    app.step(FRAME_MS, [])
    game = app.top
    assert isinstance(game, GameScene)
    return game


def screen_of(scene: GameScene, x: float, y: float) -> tuple[int, int]:
    return (int((x + 0.5) * 32 - scene.camera.x), int((y + 0.5) * 32 - scene.camera.y))


def click(app: App, pos: tuple[int, int], button: int = 1) -> None:
    app.step(FRAME_MS, [
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button),
        pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button),
    ])


def key(app: App, k: int, mod: int = 0) -> None:
    app.step(FRAME_MS, [pygame.event.Event(pygame.KEYDOWN, key=k, mod=mod)])


def player_drones(scene: GameScene) -> list[int]:
    return [u.id for u in scene.sim.state.units if u.side == "player" and u.type == "drone"]


def box_select_drones(app: App, scene: GameScene) -> None:
    drones = [u for u in scene.sim.state.units if u.side == "player" and u.type == "drone"]
    xs = [screen_of(scene, u.x, u.y)[0] for u in drones]
    ys = [screen_of(scene, u.x, u.y)[1] for u in drones]
    start, end = (min(xs) - 20, min(ys) - 20), (max(xs) + 20, max(ys) + 20)
    app.step(FRAME_MS, [
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=start, button=1),
        pygame.event.Event(pygame.MOUSEBUTTONUP, pos=end, button=1),
    ])


def test_box_select_and_right_click_on_ore_starts_gathering(app: App, scene: GameScene) -> None:
    box_select_drones(app, scene)
    assert sorted(scene.selected) == sorted(player_drones(scene))
    ore = scene.sim.state.deposits[0].tiles[0]
    click(app, screen_of(scene, ore.x, ore.y), button=3)
    tasks = {u.task for u in scene.sim.state.units if u.id in scene.selected}
    assert tasks <= {"to_resource", "gathering", "waiting"}
    assert scene.markers, "после приказа должно появиться кольцо-маркер"


def test_build_hotkeys_place_construction_site(app: App, scene: GameScene) -> None:
    box_select_drones(app, scene)
    key(app, pygame.K_b)
    assert scene.menu == "build"
    key(app, pygame.K_p)
    assert scene.placing == "solar"
    base = scene.sim.state.map.bases["player"]
    spot = open_spot(scene.sim.state, Point(base.x + 3, base.y - 3))
    click(app, screen_of(scene, spot.x, spot.y))
    site = next(b for b in scene.sim.state.buildings if b.x == spot.x and b.y == spot.y)
    assert site.type == "solar" and not site.complete
    assert scene.placing is None


def test_groups_and_idle_drone_key(app: App, scene: GameScene) -> None:
    box_select_drones(app, scene)
    key(app, pygame.K_1, pygame.KMOD_LCTRL)
    key(app, pygame.K_ESCAPE)  # без режима — пауза; закрываем её
    key(app, pygame.K_ESCAPE)
    app.step(FRAME_MS, [])
    scene.select([])
    key(app, pygame.K_1)
    assert sorted(scene.selected) == sorted(player_drones(scene))
    scene.select([])
    key(app, pygame.K_PERIOD)
    assert len(scene.selected) == 1 and scene.selected[0] in player_drones(scene)


def test_dome_trains_drone_by_hotkey(app: App, scene: GameScene) -> None:
    dome = next(b for b in scene.sim.state.buildings if b.side == "player" and b.type == "dome")
    click(app, screen_of(scene, dome.x, dome.y))
    assert scene.selected == [dome.id]
    key(app, pygame.K_q)
    assert len(dome.queue) == 1
    queue_slot = panel.BottomPanel._queue_rect(0).center
    click(app, queue_slot)
    assert dome.queue == []


def test_minimap_click_moves_camera(app: App, scene: GameScene) -> None:
    before = pygame.Vector2(scene.camera)
    click(app, (panel.MINIMAP_RECT.right - 5, panel.MINIMAP_RECT.top + 5))  # правый верхний угол карты
    assert scene.camera != before


def test_escape_pauses_and_resumes(app: App, scene: GameScene) -> None:
    key(app, pygame.K_ESCAPE)
    assert isinstance(app.top, PauseScene)
    key(app, pygame.K_ESCAPE)
    app.step(FRAME_MS, [])
    assert app.top is scene
