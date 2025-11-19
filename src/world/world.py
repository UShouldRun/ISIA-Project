from typing import Tuple, List
from math import sqrt

from settings import COLLISION_RADIUS

class WorldObject:
    """
    Basic world entity with a position.

    Attributes:
        id (str): Unique identifier for the object.
        pos (Tuple[float, float]): Physical coordinates of the object.
    """
    def __init__(self, id: str, pos: Tuple[float, float]) -> None:
        """
        Initialize a WorldObject.

        Args:
            id (str): Unique identifier.
            pos (Tuple[float, float]): Initial position.
        """
        self.id = id
        self.pos = pos

    def __repr__(self) -> str:
        """
        Return a string representation of the object.

        Returns:
            str: Representation in the format "id(pos=(x, y))".
        """
        return f"{self.id}(pos={self.pos})"

class World:
    """
    Global environment shared by agents.

    Attributes:
        objects (List[WorldObject]): List of objects currently in the world.
    """
    def __init__(self, objects: List[WorldObject] = None) -> None:
        """
        Initialize the World.

        Args:
            objects (List[WorldObject], optional): Initial list of objects. Defaults to empty list.
        """
        self.objects = objects or []

    def add_object(self, obj: WorldObject) -> None:
        """
        Add an object to the world.

        Args:
            obj (WorldObject): The object to add.
        """
        self.objects.append(obj)

    def remove_object(self, obj: WorldObject) -> None:
        """
        Remove an object from the world if it exists.

        Args:
            obj (WorldObject): The object to remove.
        """
        if obj in self.objects:
            self.objects.remove(obj)

    def collides(self, id: str, pos: Tuple[float, float]) -> bool:
        """
        Check if a given position collides with any other object in the world.

        Args:
            id (str): Identifier of the object being checked (ignored in collision with itself).
            pos (Tuple[float, float]): Position to check.

        Returns:
            bool: True if collision occurs with any object (excluding itself), False otherwise.
        """
        return [
            obj
            for obj in self.objects
            if sqrt((pos[0] - obj.pos[0]) ** 2 + (pos[1] - obj.pos[1]) ** 2) <= COLLISION_RADIUS and id != obj.id
        ]

    def __repr__(self) -> str:
        """
        Return a string representation of the world.

        Returns:
            str: Representation showing all objects in the world.
        """
        return f"World(objects={[repr(o) for o in self.objects]})"
