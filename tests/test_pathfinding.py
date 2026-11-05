"""Карта и поиск пути A*."""

from __future__ import annotations

from reddome.sim.map import create_map, mirror, tile_at
from reddome.sim.pathfinding import find_path
from reddome.sim.types import GameMap, Point


def open_map(width: int, height: int) -> GameMap:
    return GameMap(
        width=width,
        height=height,
        tiles=["ground"] * (width * height),
        bases={"player": Point(0, 0), "vector": Point(width - 1, height - 1)},
    )


def test_same_seed_same_map_different_seed_different_map() -> None:
    assert create_map(7) == create_map(7)
    assert create_map(7).tiles != create_map(8).tiles


def test_map_is_mirrored_for_fair_start() -> None:
    game_map = create_map(3)
    for y in range(game_map.height):
        for x in range(game_map.width):
            m = mirror(game_map.width, game_map.height, Point(x, y))
            assert tile_at(game_map, x, y) == tile_at(game_map, m.x, m.y)
    assert "ice" in game_map.tiles
    assert "ore" in game_map.tiles
    assert tile_at(game_map, game_map.bases["player"].x, game_map.bases["player"].y) == "ground"


def test_path_between_bases_goes_through_free_neighbor_tiles() -> None:
    game_map = create_map(1)

    def blocked(x: int, y: int) -> bool:
        return tile_at(game_map, x, y) == "rock"

    start = Point(game_map.bases["player"].x + 1, game_map.bases["player"].y)
    goal = Point(game_map.bases["vector"].x - 1, game_map.bases["vector"].y)

    path = find_path(game_map, blocked, start, goal)

    assert path is not None
    previous = start
    for step in path:
        assert max(abs(step.x - previous.x), abs(step.y - previous.y)) == 1
        assert not blocked(step.x, step.y)
        previous = step
    assert previous == goal


def test_no_path_to_enclosed_goal() -> None:
    def wall(x: int, y: int) -> bool:
        return max(abs(x - 2), abs(y - 2)) == 1

    assert find_path(open_map(5, 5), wall, Point(0, 0), Point(2, 2)) is None


def test_no_diagonal_corner_cutting() -> None:
    def blocked(x: int, y: int) -> bool:
        return (x, y) in {(1, 0), (0, 1)}

    assert find_path(open_map(2, 2), blocked, Point(0, 0), Point(1, 1)) is None
