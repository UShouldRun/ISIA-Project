from heapq import heapify, heappop, heappush
from math import sqrt

from typing import Tuple, List
from heapq import *

from .world import WorldObject

MapPos = Tuple[int, int]

class Map():
    def __init__(self, limit: Tuple[float, float]) -> None:
        self.graph:  int   = 0
        self.rows:   int   = int(limit[0])
        self.colums: int   = int(limit[1])
        self.length: float = limit[0]
        self.height: float = limit[1]

    def normalize(self, pos: Tuple[float, float]) -> Tuple[int, int]:
        return (int(pos[0] * self.columns / self.length), int(pos[1] * self.rows / self.height))

    def rescale(self, pos: MapPos) -> Tuple[float, float]:
        return (pos[0] * self.length / self.columns, pos[1] * self.height / self.rows)

    def distance(self, pos1: Tuple[float, float], pos2: Tuple[float, float]) -> float:
        i1, j1 = self.normalize(pos1)
        i2, j2 = self.normalize(pos2)
        return sqrt((i1 - i2) ** 2 + (j1 - j2) ** 2)

    def in_map(self, pos: Tuple[int, int]) -> bool:
        return 0 <= pos[0] < self.columns and 0 <= pos[1] < self.rows

    def add(self, obstacles: List[WorldObject]) -> None:
        for obj in obstacles:
            pos: Tuple[int, int] = Map.normalize(obj.pos)
            self.graph |= 1 << (pos[0] * self.columns + pos[1])

    def remove(self, obstacles: List[WorldObject]) -> None:
        for obj in obstacles:
            pos: Tuple[int, int] = Map.normalize(obj.pos)
            self.graph &= (1 << (pos[0] * self.columns + pos[1])) - 1

    def pos_is_blocked(self, pos: Tuple[float, float]) -> bool:
        i, j = Map.normalize(pos)
        return (self.graph >> (i * self.columns + j)) & 1

class AStarNode():
    def __init__(self, pos: MapPos, score: float) -> None:
        self.pos   = pos
        self.score = score

    def __lt__(self, other) -> bool:
        return self.score < other.score

class AStar():
    @staticmethod
    def _reconstruct(map: Map, path: dict[MapPos, MapPos], start: MapPos, goal: MapPos) -> List[Tuple[float, float]]:
        node: MapPos = goal
        seq: List[MapPos] = []

        while node != start:
            seq.insert(0, map.rescale(node))
            node = path[node]

        return seq

    @staticmethod
    def run(map: Map, start: Tuple[float, float], goal: Tuple[float, float]) -> List[Tuple[float, float]]:
        s: MapPos = map.normalize(start)
        g: MapPos = map.normalize(goal)

        min_heap: List[MapPos] = []
        heapify(min_heap)

        path: dict[MapPos, MapPos] = {}

        gScore: dict[MapPos, float] = {
                (i, j): float("inf")
                for i in range(map.length)
                for j in range(map.height)
            }
        gScore[s] = 0
        heappush(min_heap, AStarNode(s, gScore[s]))

        fScore: dict[MapPos, float] = {
                (i, j): float("inf")
                for i in range(map.columns)
                for j in range(map.rows)
            }
        fScore[s] = map.distance(s, g)

        while min_heap != []:
            curr: MapPos = heappop(min_heap).pos
            if curr[0] == g[0] and curr[1] == g[1]:
                return AStar._reconstruct(map, path, s, g)

            neighbours: List[MapPos] = filter(
                    lambda pos: map.in_map(pos) and
                    [(curr[0] + dir_x, curr[1] + dir_y)
                     for dir_x, dir_y in [
                         (-1,-1), (0,-1), (1,-1), (1,0),
                         (1,1), (0,1), (-1,1), (-1,0)
                    ]]
                )
            for neighbour in neighbours:
                tentative_gScore: float = gScore[curr] + map.distance(curr, neighbour)

                if tentative_gScore < gScore[neighbour]:
                    path[neighbour]   = curr
                    gScore[neighbour] = tentative_gScore
                    fScore[neighbour] = tentative_gScore + map.distance(neighbour, g)

                    if neighbour not in min_heap:
                        heappush(min_heap, AStarNode(neighbour, gScore[neighbour]))

        return []
