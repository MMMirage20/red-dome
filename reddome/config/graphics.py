"""Настройки графики (B6): на слабом ноутбуке на защите эффекты можно выключить флагами запуска."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GraphicsSettings:
    particles: bool = True
    shadows: bool = True
    day_night: bool = True
    #: Показывать FPS в углу (включается вместе с --debug).
    show_fps: bool = False

    @staticmethod
    def low() -> GraphicsSettings:
        """Пресет для слабого ноутбука: без частиц, теней и смены дня и ночи."""
        return GraphicsSettings(particles=False, shadows=False, day_night=False)
