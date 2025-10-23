import spade

from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, CyclicBehaviour
from spade.message import Message
from spade.template import Template

from world.map import Map, MapPos
from world.world import World

from heapq import heapify, heappush, heappop

class Drone(Agent):
    class MapTerrain(CyclicBehaviour): # Is this a cyclic behaviour?
        class AStarNode():
            def __init__(self, pos: MapPos, score: float) -> None:
                self.pos   = pos
                self.score = score

            def __lt__(self, other) -> bool:
                return self.score < other.score

        def reconstruct(path: dict[MapPos, MapPos], start: MapPos, goal: MapPos) -> List[MapPos]:
            node: MapPos = goal
            seq: List[MapPos] = []
            while node != start:
                seq.insert(0, node)
                node = path[node]
            return seq

        def a_star(self, map: Map, start: Tuple[float, float], goal: Tuple[float, float]) -> List[Tuple[float, float]]:
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
                    for i in range(map.length)
                    for j in range(map.height)
                }
            fScore[s] = map.distance(s, g)

            while queue != []:
                curr: MapPos = heappop(min_heap).pos
                if curr[0] == g[0] and curr[1] == g[1]:
                    return reconstruct(path, s, g)

                neighbours: List[MapPos] = filter(
                        lambda pos: map.in_map(pos) and ,
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

        async def on_start(self, map: Map, world: World):
            """Initial Scan"""
            map.add(world.objects)
 
        async def run(self, map: Map, goal: MapPos) -> List[Tuple[float, float]]:
            """Moves to goal location"""
            return self.a_star(map, goal)

        async def on_end(self):
            """Stops to analyze"""
            pass

    class Analyze(CyclicBehaviour):
        def run(self, world_data, agents_msg):
            return

    class Communicate(OneShotBehaviour):
        def decide_receiver(self, data, agents):
            return

        def create_message_body(data):
            return

        async def send_msg(self, data, agents):
            receiver = self.decide_receiver(data, agents)
            msg = Message(to = receiver).set_metadata("performative", "inform")
            msg.body = self.create_message_body(data)

            await self.send(msg)

        async def run(self, world_data, agents, timeout):
            agents_msg = await self.receive(timeout = timeout)
            self.send(await self.analyze(world_data, agents_msg), agents)

    async def setup(self):
        self.add_behaviour(self.Communicate(), Template().set_metadata("performative", "inform"))
        self.add_behaviour(self.Analyze())
        self.add_behaviour(self.MapTerrain())
