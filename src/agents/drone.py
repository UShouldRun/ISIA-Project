import spade

from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, CyclicBehaviour
from spade.message import Message
from spade.template import Template

from world.map import Map, MapPos, AStar
from world.world import World

from heapq import heapify, heappush, heappop

class Drone(Agent):
    def __init__(
            self, jid: int, password: str,
            position: Tuple[float, float] = (0, 0), base_position: Tuple[float, float] = (0, 0),
            energy: int = 10000, energy_consump_rate: int = 1
        ):
        super().__init__(jid, password)
        self.position = list(position)
        self.base_position = tuple(base_position)
        self.energy = energy
        self.energy_consump_rate = energy_consump_rate

    def energy_limit(self, curr_pos: Tuple[float, float], base_pos: Tuple[float, float]) -> int:
        return self.energy_consump_rate * int(sqrt((curr_pos[0] - base_pos[0]) ** 2 + (curr_pos[1] - base_pos[1]) ** 2))

    def get_dpos(curr: Tuple[float, float], goal: Tuple[float, float]) -> float:
        return (
            1 if curr[0] < goal[0] else -1 if curr[0] > goal[0] else 0,
            1 if curr[1] < goal[1] else -1 if curr[1] > goal[1] else 0
        )

    class MapTerrain(CyclicBehaviour): # Is this a cyclic behaviour? 
        async def on_start(self, map: Map, world: World):
            """Initial Scan"""
            map.add(world.objects)
 
        async def run(self, map: Map, goal: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
            """Moves to goal location"""
            return AStar.run(map, map.normalize(goal))

        async def on_end(self):
            """Stops to analyze"""
            pass

    class ReturnToBase():
        async def run(self):
            drone = self.agent

            drone.position += drone.get_dpos(drone.position, drone.base_position)
            drone.energy -= drone.enery_consump_energy
            print(f"[{drone.name}] Moved to: {tuple(drone.position)} | Energy: {drone.energy}%")

            if tuple(drone.position) == drone.base_position:
                print(f"[{drone.name}] Arrived at the base with {drone.energy}% of energy.")
                print(f"[{drone.name}] Starting charging...")

                while drone.energy < drone.max_energy:
                    drone.energy += drone.max_energy // 20
                    if drone.energy > drone.max_energy:
                        drone.energy = drone.max_energy

                    print(f"[{drone.name}] Charging... {drone.energy}%")
                    await asyncio.sleep(1)

                print(f"[{drone.name}] Fully charged battery.")

                msg = Message(
                    to="base@planet.local",
                    body="Battery charged. Ready for next mission.",
                    metadata={"type": "status"}
                )
                await self.send(msg)

                print(f"[{drone.name}] Status sent to the base.")
                drone.add_behaviour(drone.WaitForMission())

                return

            await asyncio.sleep(1)

    class ExploreTerrain(CyclicBehaviour):
        async def run(self):
            drone = self.agent
            if drone.energy <= drone.energy_limit(drone.position, drone.base_position):
                print(f"[{drone.name}] Depleted energy!")
                drone.add_behaviour(drone.ReturnToBase())
                return

            dx, dy = drone.get_dpos(drone.position, drone.goal)
            drone.position[0] += dx
            drone.position[1] += dy
            drone.energy -= drone.enery_consump_energy

            print(f"[{drone.name}] Moved to: {tuple(drone.position)} | Energy: {drone.energy}%")

            if tuple(drone.position) == drone.goal:
                print(f"[{drone.name}] Arrived at destination! Starting map terrain...")
                drone.add_behaviour(drone.MapTerrain())

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
        self.add_behaviour(self.ExploreTerrain())
