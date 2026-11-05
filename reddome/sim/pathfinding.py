"""A* по сетке в 8 направлениях без срезания углов."""

from __future__ import annotations

import heapq
import math
from collections.abc import Callable

from reddome.sim.map import in_bounds
from reddome.sim.types import GameMap, Point

DIRECTIONS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))


def octile(a: Point, b: Point) -> float:
    dx, dy = abs(a.x - b.x), abs(a.y - b.y)
    return max(dx, dy) + (math.sqrt(2) - 1) * min(dx, dy)


def find_path(
    game_map: GameMap,
    is_blocked: Callable[[int, int], bool],
    start: Point,
    goal: Point,
) -> list[Point] | None:
    """Путь без стартовой клетки; [] если старт совпадает с целью; None если пути нет.

    Синхронный и детерминированный: при равной оценке берётся узел, добавленный раньше.
    """
    if not in_bounds(game_map, goal.x, goal.y) or is_blocked(goal.x, goal.y):
        return None
    if start == goal:
        return []

    counter = 0
    open_heap: list[tuple[float, float, int, Point]] = [(octile(start, goal), octile(start, goal), counter, start)]
    best_g: dict[Point, float] = {start: 0.0}
    came_from: dict[Point, Point] = {}
    closed: set[Point] = set()

    while open_heap:
        _, _, _, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        closed.add(current)

        if current == goal:
            path = [current]
            while path[-1] in came_from and came_from[path[-1]] != start:
                path.append(came_from[path[-1]])
            return list(reversed(path))

        for dx, dy in DIRECTIONS:
            nx, ny = current.x + dx, current.y + dy
            if not in_bounds(game_map, nx, ny) or is_blocked(nx, ny):
                continue
            diagonal = dx != 0 and dy != 0
            if diagonal and (is_blocked(current.x + dx, current.y) or is_blocked(current.x, current.y + dy)):
                continue
            neighbor = Point(nx, ny)
            if neighbor in closed:
                continue
            g = best_g[current] + (math.sqrt(2) if diagonal else 1.0)
            if neighbor in best_g and best_g[neighbor] <= g:
                continue
            best_g[neighbor] = g
            came_from[neighbor] = current
            h = octile(neighbor, goal)
            counter += 1
            heapq.heappush(open_heap, (g + h, h, counter, neighbor))

    return None
