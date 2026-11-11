"""Отрисовка игрового мира: карта, тени, здания, юниты, эффекты, освещение, полоски здоровья.

Порядок слоёв: карта → тени → кольца выделения → здания → юниты → пылевой вихрь → тонировка времени суток →
огни (BLEND_ADD) → эффекты → полоски → пыль → виньетка.
"""

from __future__ import annotations

import math

import pygame

from reddome.config.graphics import GraphicsSettings
from reddome.render import art
from reddome.render.draw import angle_index
from reddome.render.lighting import Lighting
from reddome.render.particles import Effects
from reddome.render.sprites import ANGLES, SHADOW_OFFSET, SpriteBank
from reddome.render.terrain import Terrain
from reddome.sim.simulation import Simulation
from reddome.sim.types import Building, DustDevil, SimEvent, Unit
from reddome.ui import theme
from reddome.ui.theme import Color

TILE = theme.TILE
GLOW_LEVELS = 8
#: HP считается дробно, после стройки может остаться 1499,9999 — такую полоску не показываем.
HP_EPSILON = 0.5


def tile_center(x: float, y: float) -> tuple[float, float]:
    return (x + 0.5) * TILE, (y + 0.5) * TILE


def health_color(fraction: float) -> Color:
    if fraction > 0.5:
        return theme.mix(theme.WARNING, theme.SUCCESS, (fraction - 0.5) * 2)
    return theme.mix(theme.ALARM, theme.WARNING, fraction * 2)


def draw_bar(surface: pygame.Surface, center_x: float, top: float, width: int, fraction: float,
             color: Color | None = None) -> None:
    fraction = max(0.0, min(1.0, fraction))
    outer = pygame.Rect(0, 0, width + 2, 6)
    outer.midtop = (center_x, top)
    pygame.draw.rect(surface, (12, 10, 10), outer, border_radius=2)
    inner = outer.inflate(-2, -2)
    inner.width = max(0, round(inner.width * fraction))
    pygame.draw.rect(surface, color or health_color(fraction), inner, border_radius=2)


class WorldRenderer:
    def __init__(self, sprites: SpriteBank, graphics: GraphicsSettings, sim: Simulation,
                 terrain: Terrain | None = None) -> None:
        self.sprites = sprites
        self.graphics = graphics
        state = sim.state
        self.terrain = terrain or Terrain(state.map, state.deposits, state.seed).build()
        self.lighting = Lighting(theme.SCREEN_SIZE, state.seed)
        self.effects = Effects(graphics.particles, seed=state.seed)
        self.time_ms = 0.0
        self._glows: dict[tuple[int, Color, int], pygame.Surface] = {}
        self._last_pos: dict[int, tuple[float, float]] = {}
        self._spark_ms = 0.0

    # --- Свет ---------------------------------------------------------------------

    def glow(self, radius: int, color: Color, strength: float) -> pygame.Surface:
        level = max(1, min(GLOW_LEVELS, round(strength * GLOW_LEVELS)))
        key = (radius, color, level)
        image = self._glows.get(key)
        if image is None:
            image = self.sprites.glow(radius, color).copy()
            v = int(255 * level / GLOW_LEVELS)
            image.fill((v, v, v), special_flags=pygame.BLEND_MULT)
            self._glows[key] = image
        return image

    # --- События и анимация -------------------------------------------------------------

    def handle_events(self, events: list[SimEvent]) -> None:
        for e in events:
            x, y = tile_center(e.x, e.y)
            if e.kind == "dropoff":
                color = theme.SUCCESS if e.side == "player" else theme.TEAM_VECTOR
                self.effects.popup(f"+{e.value}", x, y - 18, color)
            elif e.kind == "shot":
                tx, ty = tile_center(e.tx, e.ty)
                self.effects.shot(x, y, tx, ty, theme.team_color(e.side))
            elif e.kind == "unit_destroyed":
                self.effects.explosion(x, y)
            elif e.kind == "building_destroyed":
                self.effects.explosion(x, y, big=True)
            elif e.kind == "construction_complete":
                self.effects.sparks(x, y, 14)
            elif e.kind == "deposit_depleted":
                self.effects.dust(x, y, 12)
            elif e.kind == "panel_dusted":
                self.effects.dust(x, y, 8)

    def update(self, dt_ms: float, sim: Simulation) -> None:
        self.time_ms += dt_ms
        self.effects.update(dt_ms)
        self.lighting.update_dust(dt_ms)
        self._spark_ms += dt_ms
        weld = self._spark_ms >= 220
        if weld:
            self._spark_ms = 0
        devil = sim.state.dust_devil
        if devil is not None and self.effects.rng.random() < 0.6:
            x, y = tile_center(devil.x, devil.y)
            a = self.effects.rng.random() * math.tau
            self.effects.dust(x + math.cos(a) * 14, y + 10 + math.sin(a) * 6)
        seen: dict[int, tuple[float, float]] = {}
        for unit in sim.state.units:
            seen[unit.id] = (unit.x, unit.y)
            last = self._last_pos.get(unit.id)
            moving = last is not None and (abs(last[0] - unit.x) + abs(last[1] - unit.y)) > 0.001
            if unit.type == "guard_rover" and moving and self.effects.rng.random() < 0.35:
                x, y = tile_center(unit.x, unit.y)
                self.effects.dust(x - math.cos(unit.facing) * 10, y - math.sin(unit.facing) * 10)
            if weld and unit.task == "building":
                site = next((b for b in sim.state.buildings if b.id == unit.target_id), None)
                if site is not None:
                    ux, uy = tile_center(unit.x, unit.y)
                    sx, sy = tile_center(site.x, site.y)
                    self.effects.sparks((ux + sx) / 2, (uy + sy) / 2, 3)
        self._last_pos = seen

    # --- Кадр -------------------------------------------------------------------------

    def draw(self, surface: pygame.Surface, sim: Simulation, camera: tuple[float, float],
             selected: set[int], hovered: int | None = None, rally_of: Building | None = None) -> None:
        state, balance = sim.state, sim.balance
        cx, cy = camera
        self.terrain.draw(surface, camera, state.deposits)

        if self.graphics.shadows:
            for b in state.buildings:
                if b.complete:
                    shadow = self.sprites.get_sprite(b.type, b.side, "shadow")
                    x, y = tile_center(b.x, b.y)
                    surface.blit(shadow, (x - cx - shadow.get_width() / 2 + SHADOW_OFFSET[0],
                                          y - cy - shadow.get_height() / 2 + SHADOW_OFFSET[1]))
            for u in state.units:
                shadow = self.sprites.get_sprite(u.type, u.side, "shadow")
                x, y = tile_center(u.x, u.y)
                lift = 9 if u.type == "drone" else 4
                surface.blit(shadow, (x - cx - shadow.get_width() / 2 + 3, y - cy - shadow.get_height() / 2 + lift))

        for entity in [*state.buildings, *state.units]:
            if entity.id in selected or entity.id == hovered:
                self._draw_selection(surface, entity, camera, entity.id in selected)

        for b in state.buildings:
            self._draw_building(surface, b, camera)
        for u in state.units:
            self._draw_unit(surface, u, camera)
        if state.dust_devil is not None:
            self._draw_dust_devil(surface, state.dust_devil, camera, balance.dust_devil.lifetime_sec * 1000)

        lights = 0.35
        if self.graphics.day_night:
            phase = state.sol_elapsed_ms / (balance.sol_seconds * 1000)
            lights = self.lighting.apply_tint(surface, phase)
        self._draw_lights(surface, state.buildings, camera, lights)
        self.effects.draw(surface, camera, self.glow)

        for b in state.buildings:
            x, y = tile_center(b.x, b.y)
            top = y - cy - (40 if b.type == "dome" else 24)
            if not b.complete:
                draw_bar(surface, x - cx, top, 34, b.build_progress, theme.ACCENT)
            elif b.id in selected or b.hp < balance.max_hp(b.side, b.type) - HP_EPSILON:
                draw_bar(surface, x - cx, top, 34, b.hp / balance.max_hp(b.side, b.type))
        for u in state.units:
            if u.id in selected or u.hp < balance.units[u.type].hp - HP_EPSILON:
                x, y = tile_center(u.x, u.y)
                draw_bar(surface, x - cx, y - cy - 20, 24, u.hp / balance.units[u.type].hp)

        if rally_of is not None and rally_of.rally is not None:
            self._draw_rally(surface, rally_of, camera)

        if self.graphics.particles:
            self.lighting.draw_dust(surface)
        self.lighting.draw_vignette(surface)

    def _draw_selection(self, surface: pygame.Surface, entity: Building | Unit, camera: tuple[float, float],
                        selected: bool) -> None:
        x, y = tile_center(entity.x, entity.y)
        if isinstance(entity, Building):
            w, h = (64, 30) if entity.type == "dome" else (40, 20)
            y += 12 if entity.type != "dome" else 18
        else:
            w, h = (22, 11) if entity.type == "drone" else (30, 15)
            y += 6
        color = theme.team_color(entity.side) if entity.side == "player" else theme.ALARM
        if not selected:
            color = theme.mix(color, (255, 255, 255), 0.5)
        rect = pygame.Rect(0, 0, w, h)
        rect.center = (x - camera[0], y - camera[1])
        pygame.draw.ellipse(surface, color, rect, 2 if selected else 1)

    def _draw_building(self, surface: pygame.Surface, b: Building, camera: tuple[float, float]) -> None:
        x, y = tile_center(b.x, b.y)
        sprite = self.sprites.get_sprite(b.type, b.side, "on" if b.powered or not b.complete else "off")
        w, h = sprite.get_size()
        left, top = x - camera[0] - w / 2, y - camera[1] - h / 2
        if b.complete:
            surface.blit(sprite, (left, top))
            if b.type == "solar" and b.dust_ms > 0:
                dust = pygame.Surface((w, h), pygame.SRCALPHA)
                pygame.draw.ellipse(dust, (*theme.SAND, 120), dust.get_rect().inflate(-w * 0.2, -h * 0.35))
                surface.blit(dust, (left, top))
            if b.type == "ice_drill" and b.powered:
                frame = int(self.time_ms / 60) % ANGLES
                rotor = self.sprites.get_sprite("drill_rotor", b.side, "spin", frame)
                # Головка вращается над скважиной у основания вышки.
                surface.blit(rotor, rotor.get_rect(center=(x - camera[0], top + 31)))
            return
        cut = int(h * b.build_progress)
        if cut > 0:
            surface.blit(sprite, (left, top + h - cut), pygame.Rect(0, h - cut, w, cut))
        surface.blit(self.sprites.get_sprite(b.type, b.side, "scaffold"), (left, top))

    def _draw_dust_devil(self, surface: pygame.Surface, devil: DustDevil, camera: tuple[float, float],
                         lifetime_ms: float) -> None:
        """Рыжая воронка: кольца пыли шире кверху, крутятся; в начале и конце жизни вихрь прозрачнее."""
        x, y = tile_center(devil.x, devil.y)
        x, y = x - camera[0], y - camera[1]
        fade = min(1.0, devil.age_ms / 1500, (lifetime_ms - devil.age_ms) / 1500)
        if fade <= 0:
            return
        layer = pygame.Surface((120, 150), pygame.SRCALPHA)
        spin = self.time_ms / 140
        rings = 12
        for i in range(rings):
            k = i / (rings - 1)  # 0 — у земли, 1 — вверху
            width = 12 + 84 * k ** 1.3
            height = 6 + 18 * k
            sway = math.sin(spin * 0.35 + k * 3) * 8 * k
            cy = 140 - k * 122
            color = theme.mix((120, 62, 30), theme.SAND, k * 0.6)
            rect = pygame.Rect(0, 0, width, height)
            rect.center = (60 + sway, cy)
            pygame.draw.ellipse(layer, (*color, int(70 * fade)), rect)
            pygame.draw.ellipse(layer, (*theme.mix(color, (255, 230, 190), 0.3), int((220 - 90 * k) * fade)), rect,
                                max(2, int(5 - 3 * k)))
            # Яркие «пряди» на кольце показывают вращение.
            for j in range(2):
                a = spin * (1.4 - k * 0.6) + i * 0.9 + j * math.pi
                px, py = rect.centerx + math.cos(a) * width / 2, rect.centery + math.sin(a) * height / 2
                pygame.draw.circle(layer, (*theme.SAND, int(230 * fade)), (px, py), 3 if k > 0.4 else 2)
        surface.blit(layer, (x - 60, y - 130))

    def _draw_unit(self, surface: pygame.Surface, u: Unit, camera: tuple[float, float]) -> None:
        x, y = tile_center(u.x, u.y)
        x, y = x - camera[0], y - camera[1]
        if u.type == "drone":
            bob = math.sin(self.time_ms / 260 + u.id) * 1.5
            state = "carry" if u.carry > 0 else "idle"
            body = self.sprites.get_sprite("drone", u.side, state, angle_index(u.facing, ANGLES))
            surface.blit(body, body.get_rect(center=(x, y - 5 + bob)))
        else:
            chassis = self.sprites.get_sprite("guard_rover", u.side, "body", angle_index(u.facing, ANGLES))
            turret = self.sprites.get_sprite("guard_rover", u.side, "turret", angle_index(u.aim, ANGLES))
            surface.blit(chassis, chassis.get_rect(center=(x, y)))
            surface.blit(turret, turret.get_rect(center=(x, y)))

    def _draw_lights(self, surface: pygame.Surface, buildings: list[Building], camera: tuple[float, float],
                     strength: float) -> None:
        blink = (self.time_ms // 500) % 2 == 0
        for b in buildings:
            if not b.complete:
                continue
            x, y = tile_center(b.x, b.y)
            if not b.powered:
                if blink:
                    image = self.glow(10, theme.ALARM, 0.9)
                    surface.blit(image, (x - camera[0] - 10, y - camera[1] - 18), special_flags=pygame.BLEND_ADD)
                continue
            color = art.building_light_color(b.type, b.side)
            pulse = 1.0
            if b.type == "dome":
                pulse = 0.8 + 0.2 * math.sin(self.time_ms / 700)
            for dx, dy, radius in art.BUILDING_LIGHTS[b.type]:
                image = self.glow(radius, color, strength * pulse)
                surface.blit(image, (x + dx - camera[0] - radius, y + dy - camera[1] - radius),
                             special_flags=pygame.BLEND_ADD)

    def _draw_rally(self, surface: pygame.Surface, b: Building, camera: tuple[float, float]) -> None:
        assert b.rally is not None
        bx, by = tile_center(b.x, b.y)
        rx, ry = tile_center(b.rally.x, b.rally.y)
        start = (bx - camera[0], by - camera[1])
        end = (rx - camera[0], ry - camera[1])
        pygame.draw.line(surface, theme.ACCENT, start, end, 1)
        pygame.draw.line(surface, theme.TEXT, end, (end[0], end[1] - 16), 2)
        pygame.draw.polygon(surface, theme.team_color(b.side), [(end[0], end[1] - 16), (end[0] + 10, end[1] - 12), (end[0], end[1] - 8)])

