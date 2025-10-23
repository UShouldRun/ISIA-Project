from math import sqrt

MapPos = Tuple[int, int]

class Map():
    def __init__(self, limit: Tuple[int, int]) -> None:
        self.graph:  int = 0
        self.length: int = limit[0]
        self.height: int = limit[1]

    def normalize(pos: Tuple[float, float]) -> Tuple[int, int]:
        return (int(pos[0] / self.height), int(pos[1] / self.length))

    def distance(self, pos1: Tuple[float, float], pos2: Tuple[float, float]) -> float:
        i1, j1 = self.normalize(pos1)
        i2, j2 = self.normalize(pos2)
        return sqrt((i1 - i2) ** 2 + (j1 - j2) ** 2)

    def in_map(self, pos: Tuple[int, int]) -> bool:
        return 0 <= pos[0] < self.length and 0 <= pos[1] < self.height

    def add(self, obstacles: List[WorldObject]) -> None:
        for obj in obstacles:
            pos: Tuple[int, int] = Map.normalize(obj.pos)
            self.graph |= 1 << (pos[0] * self.length + pos[1])

    def remove(self, obstables: List[WorldObject]) -> None:
        for obj in obstacles:
            pos: Tuple[int, int] = Map.normalize(obj.pos)
            self.graph &= (1 << (pos[0] * self.length + pos[1])) - 1

    def pos_is_blocked(self, pos: Tuple[float, float]) -> bool:
        i, j = Map.normalize(pos)
        return (self.graph >> (i * self.length + j)) & 1
