class Map():
    def __init__(self, limit: Tuple[int, int]) -> None:
        self.graph:  int = 0
        self.length: int = limit[0]
        self.height: int = limit[1]

    def normalize(self, pos: Tuple[float, float]) -> Tuple[int, int]:
        return (int(pos[0] / self.height), int(pos[1] / self.length))

    def add(self, obstacles: List[WorldObject]) -> None:
        for obj in obstacles:
            pos: Tuple[int, int] = self.normalize(obj.pos)
            self.graph |= 1 << (pos[0] * self.length + pos[1])

    def remove(self, obstables: List[WorldObject]) -> None:
        for obj in obstacles:
            pos: Tuple[int, int] = self.normalize(obj.pos)
            self.graph &= (1 << (pos[0] * self.length + pos[1])) - 1
