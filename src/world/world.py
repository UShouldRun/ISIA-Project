from typing import Tuple, List, Union
from math import sqrt

from .setting import COLLISION_RADIUS

class WorldObject:
    """Basic world entity with a position."""
    def __init__(self, id: str, pos: Tuple[float, float]) -> None:
        self.id = id
        self.pos = pos

    def __repr__(self):
        return f"{self.id}(pos={self.pos})"

class World:
    """Global environment shared by agents."""
    def __init__(self, objects: List[WorldObject] = None) -> None:
        self.objects = objects or []

    def add_object(self, obj: WorldObject) -> None:
        self.objects.append(obj)

    def remove_object(self, obj: WorldObject) -> None:
        if obj in self.objects:
            self.objects.remove(obj)

    def collides(self, id: int, pos: Tuple[float, float]) -> bool:
        return any(
            sqrt((pos[0] - obj.pos[0]) ** 2 + (pos[1] - obj.pos[1]) ** 2) <= COLLISION_RADIUS and id != obj.id
            for obj in self.objects
        )

    def __repr__(self):
        return f"World(objects={[repr(o) for o in self.objects]})"
