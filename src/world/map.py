import random
from heapq import heapify, heappop, heappush
from collections import defaultdict
from math import sqrt
from typing import Tuple, List, Optional

from .world import WorldObject
from settings import STORM_COST, RED, GREEN, MAGENTA, YELLOW, RESET

MapPos = Tuple[int, int]

class MapCell:
    """
    Represents a single cell in the map grid.

    Attributes:
        terrain (float): Terrain type of the cell (-1: depression, 0: normal, 1: elevated).
        cost (float): Base movement cost for this cell.
        dust_storm (bool): Whether the cell currently has a dust storm.
        x (int): X-coordinate in the grid.
        y (int): Y-coordinate in the grid.
    """
    def __init__(self, pos: MapPos, terrain: float):
        """
        Initialize a MapCell.

        Args:
            pos (MapPos): The (x, y) coordinates of the cell.
            terrain (float): Terrain type of the cell.
        """
        self.terrain = terrain
        self.cost = 0 if terrain == 0 else float('inf')
        self.dust_storm = False
        self.x = pos[0]
        self.y = pos[1]

    def get_cost(self) -> float:
        """
        Calculate the movement cost for this cell.

        Returns:
            float: The cost to traverse this cell. Returns infinity if impassable.
        """
        return self.cost if not self.dust_storm else STORM_COST

    def to_dict(self) -> dict:
        """
        Convert the MapCell to a dictionary for serialization.

        Returns:
            dict: JSON-serializable representation of the cell.
        """
        return {
            "x": self.x,
            "y": self.y,
            "terrain": float(self.terrain),
            "dust_storm": bool(self.dust_storm)
        }


class Map:
    """
    Represents the navigable map grid for the rover.

    Attributes:
        rows (int): Number of rows in the map.
        columns (int): Number of columns in the map.
        length (float): Physical length of the map.
        height (float): Physical height of the map.
        grid (List[List[MapCell]]): 2D list of MapCells.
        graph (int): Bitmask representing obstacle positions.
        visited (int): Bitmask representing visited positions.
    """
    def __init__(self, limit: Tuple[float, float]) -> None:
        """
        Initialize the Map.

        Args:
            limit (Tuple[float, float]): (length, height) of the map.
        """
        self.graph: int = 0
        self.visited: int = 0
        self.rows: int = int(limit[0])
        self.columns: int = int(limit[1])
        self.length: float = limit[0]
        self.height: float = limit[1]
        self.grid: List[List[MapCell]] = self._initialize_grid()

    def _initialize_grid(self) -> List[List[MapCell]]:
        """
        Populate the map grid with randomly generated terrain.

        Returns:
            List[List[MapCell]]: A 2D grid of MapCells.
        """
        grid = []
        terrain_choices = [-1, 0, 1]
        weights = [0.05, 0.90, 0.05]

        for i in range(self.columns):
            column = []
            for j in range(self.rows):
                initial_terrain = random.choices(terrain_choices, weights=weights, k=1)[0]
                cell = MapCell(pos=(i, j), terrain=initial_terrain)
                column.append(cell)
            grid.append(column)
        return grid

    def normalize(self, pos: Tuple[float, float]) -> Tuple[int, int]:
        """
        Convert physical coordinates to grid coordinates.

        Args:
            pos (Tuple[float, float]): Physical coordinates (x, y).

        Returns:
            Tuple[int, int]: Normalized grid coordinates.
        """
        return (int(pos[0] * self.columns / self.length), int(pos[1] * self.rows / self.height))

    def rescale(self, pos: MapPos) -> Tuple[float, float]:
        """
        Convert grid coordinates back to physical coordinates.

        Args:
            pos (MapPos): Grid coordinates (x, y).

        Returns:
            Tuple[float, float]: Physical coordinates.
        """
        return (pos[0] * self.length / self.columns, pos[1] * self.height / self.rows)

    def distance(self, pos1: Tuple[float, float], pos2: Tuple[float, float]) -> float:
        """
        Compute Euclidean distance between two positions on the map.

        Args:
            pos1 (Tuple[float, float]): First position.
            pos2 (Tuple[float, float]): Second position.

        Returns:
            float: Euclidean distance between normalized grid positions.
        """
        i1, j1 = self.normalize(pos1)
        i2, j2 = self.normalize(pos2)
        return sqrt((i1 - i2) ** 2 + (j1 - j2) ** 2)

    def in_map(self, pos: Tuple[int, int]) -> bool:
        """
        Check if a position is within map boundaries.

        Args:
            pos (Tuple[int, int]): Grid coordinates.

        Returns:
            bool: True if position is valid, False otherwise.
        """
        return 0 <= pos[0] < self.columns and 0 <= pos[1] < self.rows

    def add(self, obstacles: List[WorldObject]) -> None:
        """
        Mark positions occupied by obstacles in the map bitmask.

        Args:
            obstacles (List[WorldObject]): List of obstacles.
        """
        for obj in obstacles:
            pos: Tuple[int, int] = self.normalize(obj.pos)
            self.graph |= 1 << (pos[0] * self.columns + pos[1])

    def remove(self, obstacles: List[WorldObject]) -> None:
        """
        Remove obstacles from the map bitmask.

        Args:
            obstacles (List[WorldObject]): List of obstacles to remove.
        """
        for obj in obstacles:
            pos: Tuple[int, int] = self.normalize(obj.pos)
            self.graph &= (1 << (pos[0] * self.columns + pos[1])) - 1

    def pos_is_blocked(self, pos: Tuple[float, float]) -> bool:
        """
        Check if a grid position is blocked by an obstacle.

        Args:
            pos (Tuple[float, float]): Physical position.

        Returns:
            bool: True if blocked, False otherwise.
        """
        i, j = self.normalize(pos)
        return (self.graph >> (i * self.columns + j)) & 1

    def visit(self, pos: MapPos) -> None:
        """
        Mark a position as visited in the bitmask.

        Args:
            pos (MapPos): Grid coordinates.
        """
        self.visited |= 1 << (pos[0] * self.columns + pos[1])

    def is_visited(self, pos: MapPos) -> bool:
        """
        Check if a grid position has been visited.

        Args:
            pos (MapPos): Grid coordinates.

        Returns:
            bool: True if visited, False otherwise.
        """
        return (self.visited >> (pos[0] * self.columns + pos[1])) & 0b1

    def clear_visited(self) -> None:
        """Reset all visited positions."""
        self.visited = 0

    def count_visited(self) -> int:
        """
        Count the number of visited cells.

        Returns:
            int: Total visited cells.
        """
        count: int = 0
        for i in range(self.rows):
            for j in range(self.columns):
                count += self.is_visited((i, j))
        return count

    def get_cell(self, x: int, y: int) -> Optional[MapCell]:
        """
        Access a cell at given coordinates.

        Args:
            x (int): X-coordinate.
            y (int): Y-coordinate.

        Returns:
            Optional[MapCell]: The MapCell object or None if out of bounds.
        """
        if self.in_map((x, y)):
            return self.grid[x][y]
        return None

    def make_dust_cell(self, x: int, y: int):
        """
        Set a dust storm on a specific cell.

        Args:
            x (int): X-coordinate.
            y (int): Y-coordinate.
        """
        if self.in_map((x, y)):
            self.grid[x][y].dust_storm = True

    def clear_dust_cell(self, x: int, y: int):
        """
        Remove a dust storm from a specific cell.

        Args:
            x (int): X-coordinate.
            y (int): Y-coordinate.
        """
        if self.in_map((x, y)):
            self.grid[x][y].dust_storm = False

    def print(self, start: Optional[MapPos], goal: Optional[MapPos]) -> None:
        """
        Print a textual representation of the map with visited cells and start/goal.

        Args:
            start (Optional[MapPos]): Starting position.
            goal (Optional[MapPos]): Goal position.
        """
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


class AStarNode:
    """
    Node used in the A* algorithm priority queue.

    Attributes:
        pos (MapPos): Grid position of the node.
        score (float): Current fScore of the node.
    """
    def __init__(self, pos: MapPos, score: float) -> None:
        """
        Initialize an AStarNode.

        Args:
            pos (MapPos): Grid coordinates.
            score (float): fScore of the node.
        """
        self.pos = pos
        self.score = score

    def __lt__(self, other) -> bool:
        """
        Compare nodes for priority queue.

        Args:
            other (AStarNode): Another node to compare.

        Returns:
            bool: True if self has lower score.
        """
        return self.score < other.score


class AStar:
    """Static class implementing the A* pathfinding algorithm."""

    @staticmethod
    def _reconstruct(map: Map, path: dict[MapPos, MapPos], start: MapPos, goal: MapPos) -> List[Tuple[float, float]]:
        """
        Reconstruct the path from start to goal.

        Args:
            map (Map): The map object.
            path (dict): Parent pointers for each node.
            start (MapPos): Start node.
            goal (MapPos): Goal node.

        Returns:
            List[Tuple[float, float]]: List of physical coordinates representing the path.
        """
        node: MapPos = goal
        seq: List[MapPos] = []

        while node != start:
            seq.insert(0, map.rescale(node))
            node = path[node]

        return seq

    @staticmethod
    def _gScore(map: Map, curr: MapPos, neighbour: MapPos) -> float:
        """
        Compute the cost to move from curr to neighbour.

        Args:
            map (Map): Map object.
            curr (MapPos): Current node.
            neighbour (MapPos): Neighbour node.

        Returns:
            float: Movement cost.
        """
        return map.distance(curr, neighbour) + map.grid[neighbour[0]][neighbour[1]].get_cost()

    @staticmethod
    def _heuristicScore(map: Map, curr: MapPos, goal: MapPos) -> float:
        """
        Heuristic estimate from curr to goal.

        Args:
            map (Map): Map object.
            curr (MapPos): Current node.
            goal (MapPos): Goal node.

        Returns:
            float: Heuristic cost.
        """
        return map.distance(curr, goal)

    @staticmethod
    def run(map: Map, start: Tuple[float, float], goal: Tuple[float, float]) -> List[Tuple[float, float]]:
        """
        Run the A* algorithm to find a path from start to goal.

        Args:
            map (Map): Map object.
            start (Tuple[float, float]): Start coordinates.
            goal (Tuple[float, float]): Goal coordinates.

        Returns:
            List[Tuple[float, float]]: List of physical coordinates representing the path.
        """
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
        while min_heap:
            curr: MapPos = heappop(min_heap).pos
            if map.is_visited(curr):
                continue
            map.visit(curr)
            count += 1

            if curr == g:
                print(f"{YELLOW}AStar[FINISHING]: reconstructing path{RESET}")
                map.clear_visited()
                return AStar._reconstruct(map, path, s, g)

            neighbours: List[MapPos] = filter(
                lambda pos: map.in_map(pos) and not map.is_visited(pos),
                [(curr[0] + dx, curr[1] + dy)
                 for dx, dy in [(-1, -1), (0, -1), (1, -1), (1, 0),
                                 (1, 1), (0, 1), (-1, 1), (-1, 0)]]
            )

            for neighbour in neighbours:
                tentative_gScore: float = gScore[curr] + AStar._gScore(map, curr, neighbour)

                if tentative_gScore < gScore[neighbour]:
                    path[neighbour] = curr
                    gScore[neighbour] = tentative_gScore
                    fScore[neighbour] = tentative_gScore + AStar._heuristicScore(map, neighbour, g)
                    heappush(min_heap, AStarNode(neighbour, fScore[neighbour]))

        print(f"{YELLOW}AStar[FINISHING]: did not find path{RESET}")
        map.clear_visited()
        return []

