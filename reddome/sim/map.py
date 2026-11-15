"""Карта кратера 48 × 32, зеркальная для двух сторон."""

from __future__ import annotations

import random

from reddome.sim.types import GameMap, Point, Side, TileKind

MAP_WIDTH = 48
MAP_HEIGHT = 32

PLAYER_BASE = Point(4, 27)
ICE_FIELDS = (Point(13, 21), Point(24, 16))
#: Ближнее поле у базы и дальнее ближе к центру — за него идёт борьба. ВЕКТОР получает зеркальные.
ORE_FIELDS = (Point(8, 21), Point(17, 13))
ROCK_CHANCE = 0.06
CLEAR_RADIUS_AROUND_BASE = 3


def tile_index(game_map: GameMap, x: int, y: int) -> int:
    return y * game_map.width + x


def in_bounds(game_map: GameMap, x: int, y: int) -> bool:
    return 0 <= x < game_map.width and 0 <= y < game_map.height


def tile_at(game_map: GameMap, x: int, y: int) -> TileKind | None:
    return game_map.tiles[tile_index(game_map, x, y)] if in_bounds(game_map, x, y) else None


def mirror(width: int, height: int, p: Point) -> Point:
    """Точка, симметричная относительно центра карты."""
    return Point(width - 1 - p.x, height - 1 - p.y)


def create_map(seed: int) -> GameMap:
    """Базы в противоположных углах, ледяные поля и рудные выходы зеркальны,
    поэтому у сторон одинаковые стартовые условия. Скалы расставляются по seed."""
    width, height = MAP_WIDTH, MAP_HEIGHT
    tiles: list[TileKind] = ["ground"] * (width * height)
    bases: dict[Side, Point] = {"player": PLAYER_BASE, "vector": mirror(width, height, PLAYER_BASE)}
    game_map = GameMap(width=width, height=height, tiles=tiles, bases=bases)
    rng = random.Random(seed)

    def put(p: Point, kind: TileKind) -> None:
        if in_bounds(game_map, p.x, p.y):
            tiles[tile_index(game_map, p.x, p.y)] = kind

    def put_mirrored(p: Point, kind: TileKind) -> None:
        put(p, kind)
        put(mirror(width, height, p), kind)

    # Скалы: обходим половину карты и ставим зеркальную пару.
    for i in range(width * height // 2):
        if rng.random() < ROCK_CHANCE:
            put_mirrored(Point(i % width, i // width), "rock")

    def paint_disc(center: Point, radius: int, kind: TileKind) -> list[Point]:
        """Рисует круг и его зеркальную копию; возвращает клетки исходного круга."""
        painted = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy <= radius * radius:
                    p = Point(center.x + dx, center.y + dy)
                    put_mirrored(p, kind)
                    if in_bounds(game_map, p.x, p.y):
                        painted.append(p)
        return painted

    paint_disc(PLAYER_BASE, CLEAR_RADIUS_AROUND_BASE, "ground")
    for field in ICE_FIELDS:
        paint_disc(field, 2, "ice")
    player_fields = [paint_disc(field, 1, "ore") for field in ORE_FIELDS]
    vector_fields = [[mirror(width, height, p) for p in tiles] for tiles in player_fields]
    game_map.ore_fields = player_fields + vector_fields
    game_map.ice_fields = find_ice_fields(game_map)

    return game_map


def find_ice_fields(game_map: GameMap) -> list[list[Point]]:
    """Связные (по сторонам клетки) группы льда, от ближней к базе игрока к ближней к ВЕКТОРу.

    На зеркальной карте их три: поле игрока, центральное (два слившихся круга) и поле ВЕКТОРа.
    """
    seen: set[Point] = set()
    fields: list[list[Point]] = []
    for i, kind in enumerate(game_map.tiles):
        start = Point(i % game_map.width, i // game_map.width)
        if kind != "ice" or start in seen:
            continue
        seen.add(start)
        group, stack = [], [start]
        while stack:
            p = stack.pop()
            group.append(p)
            for q in (Point(p.x + 1, p.y), Point(p.x - 1, p.y), Point(p.x, p.y + 1), Point(p.x, p.y - 1)):
                if q not in seen and tile_at(game_map, q.x, q.y) == "ice":
                    seen.add(q)
                    stack.append(q)
        fields.append(sorted(group, key=lambda p: (p.y, p.x)))
    base = game_map.bases["player"]

    def distance_to_base(group: list[Point]) -> float:
        cx = sum(p.x for p in group) / len(group)
        cy = sum(p.y for p in group) / len(group)
        return (cx - base.x) ** 2 + (cy - base.y) ** 2

    return sorted(fields, key=distance_to_base)
