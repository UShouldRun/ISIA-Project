class WorldObject():
    def __init__(self, pos: Tuple[float, float, float]) -> None:
        self.pos = pos

class World():
    def __init__(self, objects: List[WorldObjects]) -> None:
        self.objects = objects
