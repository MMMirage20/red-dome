"""Главный цикл игры и стек сцен."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pygame

from reddome.config.balance import Balance, load_balance
from reddome.config.camera import CameraSettings
from reddome.config.graphics import GraphicsSettings
from reddome.input.service import GestureService
from reddome.profile import Profile
from reddome.render.sprites import SpriteBank
from reddome.render.terrain import Terrain
from reddome.scenes.base import MENU_GESTURE_HINT, Scene
from reddome.scenes.boot import BootScene
from reddome.scenes.game import GameScene
from reddome.scenes.menu import MenuScene
from reddome.scenes.missions import MissionsScene
from reddome.scenes.pause import PauseScene
from reddome.scenes.result import ResultScene
from reddome.scenes.shop import ShopScene
from reddome.sim.state import create_initial_state
from reddome.sim.types import Difficulty
from reddome.ui import theme
from reddome.ui.cursor import CursorManager
from reddome.ui.gesture_hud import draw_overlay

SCENES: dict[str, type[Scene]] = {
    "boot": BootScene,
    "menu": MenuScene,
    "missions": MissionsScene,
    "game": GameScene,
    "pause": PauseScene,
    "result": ResultScene,
    "shop": ShopScene,
}


class App:
    """Стек сцен: события и обновление получает верхняя сцена, рисуются все снизу вверх.

    Переходы (start, push, pop) откладываются до конца кадра, чтобы сцена не менялась
    посреди обработки событий.
    """

    def __init__(
        self,
        *,
        debug: bool = False,
        seed: int = 1,
        balance: Balance | None = None,
        graphics: GraphicsSettings | None = None,
        camera: CameraSettings | None = None,
        window_flags: int = pygame.SCALED,
        profile: Profile | None = None,
    ) -> None:
        pygame.init()
        theme.reset_fonts()
        pygame.display.set_caption("Красный купол")
        self.screen = pygame.display.set_mode(theme.SCREEN_SIZE, window_flags)
        self.clock = pygame.time.Clock()
        self.debug = debug
        self.seed = seed
        self.balance = balance or load_balance()
        #: Сложность следующей партии: меняется в меню, «Ещё раз» на итогах играет на ней же.
        self.difficulty: Difficulty = self.balance.difficulty
        #: Миссия следующей партии (этап 3): выбирается на экране миссий, «Ещё раз» играет её же.
        self.mission = 1
        #: Профиль игрока (этап 3): покупки и результаты. Без файла — в памяти, так App создаётся в тестах.
        self.profile = profile or Profile()
        self.graphics = graphics or GraphicsSettings(show_fps=debug)
        self.sprites = SpriteBank()
        self.cursor = CursorManager()
        #: Вид курсора на этот кадр: сцена меняет его в update, App применяет после.
        self.cursor_kind = "normal"
        self.fps = 0.0
        #: Время от запуска по сумме dt кадров: по нему считаются удержания жестов и лог.
        self.time_ms = 0.0
        #: Жесты (W3-12). Без camera — выключены, так App создаётся в тестах.
        self.gestures = GestureService(self.balance.gestures, camera)
        self.gestures.start()
        self.stack: list[Scene] = []
        self.running = True
        self._pending: list[Callable[[], None]] = []
        self._terrains: dict[int, Terrain] = {}

    @property
    def top(self) -> Scene | None:
        return self.stack[-1] if self.stack else None

    # --- Общие ресурсы сцен -------------------------------------------------------

    def terrain_for(self, seed: int, build: bool = True) -> Terrain:
        """Карта для seed рисуется один раз (на экране загрузки) и переиспользуется между партиями."""
        terrain = self._terrains.get(seed)
        if terrain is None:
            state = create_initial_state(self.balance, seed)
            terrain = Terrain(state.map, state.deposits, seed)
            if build:
                terrain.build()
            self._terrains[seed] = terrain
        return terrain

    def snapshot(self) -> pygame.Surface:
        """Размытая и затемнённая копия текущего кадра — фон для паузы и итогов."""
        w, h = theme.SCREEN_SIZE
        small = pygame.transform.smoothscale(self.screen, (w // 4, h // 4))
        small = pygame.transform.gaussian_blur(small, 3)
        image = pygame.transform.smoothscale(small, (w, h))
        image.fill((150, 140, 140), special_flags=pygame.BLEND_MULT)
        return image

    # --- Сцены ------------------------------------------------------------------

    def _make(self, name: str, data: dict[str, Any]) -> Scene:
        scene = SCENES[name](self)
        scene.enter(**data)
        return scene

    def start(self, name: str, **data: Any) -> None:
        """Заменить все сцены одной, например меню → игра."""

        def operation() -> None:
            self.stack = [self._make(name, data)]

        self._pending.append(operation)

    def push(self, name: str, **data: Any) -> None:
        """Положить сцену поверх текущей, например паузу поверх игры."""
        self._pending.append(lambda: self.stack.append(self._make(name, data)))

    def pop(self) -> None:
        """Убрать верхнюю сцену и вернуться к предыдущей."""
        self._pending.append(lambda: self.stack.pop() if len(self.stack) > 1 else None)

    def quit(self) -> None:
        self.running = False

    def step(self, dt_ms: float, events: list[pygame.event.Event]) -> None:
        """Один кадр без вывода на экран — его можно вызывать из тестов и отладочных скриптов."""
        if dt_ms > 0:
            self.fps = self.fps * 0.9 + 1000 / dt_ms * 0.1 if self.fps else 1000 / dt_ms
        self.time_ms += dt_ms
        for event in events:
            if event.type == pygame.QUIT:
                self.running = False
            elif self.gestures.handle_event(event):
                continue
            elif self.top is not None:
                self.top.handle_event(event)
        # Жест применяется в игровом потоке между тиками — как щелчок мыши.
        fired = self.gestures.poll(self.time_ms)
        if fired is not None and self.top is not None:
            self.top.on_gesture(fired)
        self.cursor_kind = "normal"
        if self.top is not None:
            self.top.update(dt_ms)
        while self._pending:
            self._pending.pop(0)()
        self.cursor.set(self.cursor_kind)
        self.screen.fill(theme.PANEL)
        for scene in self._visible_scenes():
            scene.draw(self.screen)
        if self.gestures.overlay:
            draw_overlay(self.screen, self.gestures)
        if self.gestures.active and self.top is not None and self.top.menu_buttons():
            theme.draw_text(self.screen, MENU_GESTURE_HINT, (theme.SCREEN_SIZE[0] // 2, theme.SCREEN_SIZE[1] - 14), 14,
                            theme.TEXT_QUIET, anchor="center")
        if self.graphics.show_fps:
            theme.draw_text(self.screen, f"{self.fps:.0f} FPS", (theme.SCREEN_SIZE[0] - 110, 12), 15,
                            theme.SUCCESS if self.fps >= 30 else theme.ALARM, anchor="topright", kind="title")

    def _visible_scenes(self) -> list[Scene]:
        """Непрозрачная сцена (пауза и итоги рисуют свой размытый фон) скрывает нижние — их не рисуем."""
        for i in range(len(self.stack) - 1, -1, -1):
            if getattr(self.stack[i], "opaque", False):
                return self.stack[i:]
        return self.stack

    def run(self, first_scene: str = "boot") -> None:
        self.start(first_scene)
        try:
            while self.running:
                dt_ms = self.clock.tick(theme.FPS)
                self.step(dt_ms, pygame.event.get())
                pygame.display.flip()
        finally:
            self.gestures.stop()
            pygame.quit()
