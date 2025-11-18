import random

from heapq import heapify, heappop, heappush
from collections import defaultdict
from math import sqrt

from typing import Tuple, List, Optional
from heapq import *

from .world import WorldObject
from settings import RED, GREEN, MAGENTA, YELLOW, RESET

MapPos = Tuple[int, int]

class MapCell():
    def __init__(self, pos: MapPos, terrain: float):
        # terrain
        ## 1 for elevated (rover can't pass)
        ## 0 for normal
        ## -1 for depression (rover will fall)
        self.terrain = terrain 
        self.cost = 0 if terrain == 0 else float('inf')

        self.has_dust_storm = False

        self.dust_storm = False
        self.x = pos[0]
        self.y = pos[1]

    def get_cost(self) -> float:
        """
        Returns the cost to go over this MapCell
        """
        # If blocked
        if self.cost == float('inf'):
            return float('inf')

        # Start with the static base cost
        total_cost = self.cost
        
        # Apply penalty if a dust storm is active
        if self.dust_storm:
            # Multiply by a factor (e.g., 10x the base cost) to make the area highly undesirable
            total_cost += 3
            
        return total_cost

    def to_dict(self):
            """Converts MapCell state to a JSON-serializable dictionary for the client."""
            return {
                "x": self.x,
                "y": self.y,
                "terrain": float(self.terrain), # <-- CAPTURING THE VALUE HERE
                "dust_storm": self.has_dust_storm
            }

class Map():
    def __init__(self, limit: Tuple[float, float]) -> None:
        self.graph:   int   = 0
        self.visited: int   = 0
        self.rows:    int   = int(limit[0])
        self.columns: int   = int(limit[1])
        self.length:  float = limit[0]
        self.height:  float = limit[1]

        self.grid: List[List[MapCell]] = self._initialize_grid()

    def _initialize_grid(self) -> List[List[MapCell]]:
        """Populates the grid with MapCell objects and assigns initial random terrain."""
        grid = []
        # Possible terrain types: -1, 0, 1
        terrain_choices = [-1, 0, 1]
        # Probability for each terrain type
        weights = [0.05, 0.90, 0.05]
        
        for i in range(self.columns):
            column = []
            for j in range(self.rows):
                # Randomly choose the initial terrain type
                initial_terrain = random.choices(terrain_choices, weights=weights, k=1)[0]
                
                # Create the MapCell at (i, j)
                cell = MapCell(pos=(i, j), terrain=initial_terrain)
                column.append(cell)
            grid.append(column)
        return grid

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
            pos: Tuple[int, int] = self.normalize(obj.pos)
            self.graph |= 1 << (pos[0] * self.columns + pos[1])

    def remove(self, obstacles: List[WorldObject]) -> None:
        for obj in obstacles:
            pos: Tuple[int, int] = self.normalize(obj.pos)
            self.graph &= (1 << (pos[0] * self.columns + pos[1])) - 1

    def pos_is_blocked(self, pos: Tuple[float, float]) -> bool:
        i, j = self.normalize(pos)
        return (self.graph >> (i * self.columns + j)) & 1

    def visit(self, pos: MapPos) -> None:
        self.visited |= 1 << (pos[0] * self.columns + pos[1])

    def is_visited(self, pos: MapPos) -> bool:
        return (self.visited >> (pos[0] * self.columns + pos[1])) & 0b1

    def clear_visited(self) -> None:
        self.visited = 0

    def count_visited(self) -> int:
        count: int = 0
        for i in range(self.rows):
            for j in range(self.columns):
                count += self.is_visited((i, j))
        return count

    def print(self, start: Optional[MapPos], goal: Optional[MapPos]) -> None:
        for i in range(self.rows):
            row: str = ""
            for j in range(self.columns):
                visited = 1 if self.is_visited((i, j)) else 0
                color = RED
                if (i, j) == start:
                    color = YELLOW
                elif (i, j) == goal:
                    color = MAGENTA
                elif self.is_visited((i, j)):
                    color = GREEN
                row += f"{color}{visited}"
            print(row + RESET)

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
    def _gScore(map: Map, curr: MapPos, neighbour: MapPos) -> float:
        return map.distance(curr, neighbour) + map.grid[neighbour[0]][neighbour[1]].get_cost()

    @staticmethod
    def _heuristicScore(map: Map, curr: MapPos, goal: MapPos) -> float:
        return map.distance(curr, goal) 

    @staticmethod
    def run(map: Map, start: Tuple[float, float], goal: Tuple[float, float]) -> List[Tuple[float, float]]:
        print(f"{YELLOW}AStar[STARTING]: start = {start}, goal = {goal}{RESET}")

        s: MapPos = map.normalize(start)
        g: MapPos = map.normalize(goal)

        min_heap: List[AStarNode] = []
        heapify(min_heap)

        path: dict[MapPos, MapPos] = {}

        gScore: dict[MapPos, float] = defaultdict(lambda: float('inf'))
        gScore[s] = 0
        heappush(min_heap, AStarNode(s, gScore[s]))

        fScore: dict[MapPos, float] = defaultdict(lambda: float('inf'))
        fScore[s] = AStar._heuristicScore(map, s, g)

        count: int = 0
        while min_heap != []:
            curr: MapPos = heappop(min_heap).pos
            if map.is_visited(curr):
                continue
            map.visit(curr)
            # map.print(s, g)
            count += 1

            print(f"{YELLOW}AStar[RUNNING]: visited = {count}, curr = {map.rescale(curr)}, gScore = {gScore[curr]}, fScore = {fScore[curr]}{RESET}")
            
            if curr == g:
                print(f"{YELLOW}AStar[FINISHING]: reconstructing path{RESET}")
                map.clear_visited()
                reconstructed_path = AStar._reconstruct(map, path, s, g)
                print(reconstructed_path)
                return reconstructed_path

            neighbours: List[MapPos] = filter(
                    lambda pos: map.in_map(pos) and not map.is_visited(pos),
                    [(curr[0] + dir_x, curr[1] + dir_y)
                     for dir_x, dir_y in [
                         (-1,-1), (0,-1), (1,-1), (1,0),
                         (1,1), (0,1), (-1,1), (-1,0)
                    ]]
                )
            for neighbour in neighbours:
                tentative_gScore: float = (
                    gScore[curr] +
                    AStar._gScore(map, curr, neighbour)
                )

                if tentative_gScore < gScore[neighbour]:
                    path[neighbour]   = curr
                    gScore[neighbour] = tentative_gScore
                    fScore[neighbour] = tentative_gScore + AStar._heuristicScore(map, neighbour, g)
                    heappush(min_heap, AStarNode(neighbour, fScore[neighbour]))

        print(f"{YELLOW}AStar[FINISHING]: did not find path{RESET}")
        map.clear_visited()
        return []
