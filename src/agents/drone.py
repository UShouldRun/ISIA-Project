import spade
import asyncio
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, CyclicBehaviour
from spade.message import Message
from spade.template import Template
from world.map import Map, MapPos, AStar
from world.world import World
from math import sqrt
from typing import Tuple, List

class Drone(Agent):
    def __init__(
            self, jid: str, password: str,
            position: Tuple[float, float] = (0, 0),
            base_position: Tuple[float, float] = (0, 0),
            energy: int = 10000,
            energy_consump_rate: int = 1
        ):
        super().__init__(jid, password)
        self.position = list(position)
        self.base_position = tuple(base_position)
        self.energy = energy
        self.max_energy = energy
        self.energy_consump_rate = energy_consump_rate
        self.goal = (0, 0)

    def energy_limit(self, curr_pos: Tuple[float, float], base_pos: Tuple[float, float]) -> int:
        """Minimum energy required to return to base."""
        return self.energy_consump_rate * int(sqrt((curr_pos[0] - base_pos[0]) ** 2 + (curr_pos[1] - base_pos[1]) ** 2))

    def get_dpos(self, curr: Tuple[float, float], goal: Tuple[float, float]) -> Tuple[int, int]:
        """Step direction toward goal."""
        return (
            1 if curr[0] < goal[0] else -1 if curr[0] > goal[0] else 0,
            1 if curr[1] < goal[1] else -1 if curr[1] > goal[1] else 0
        )

    async def send_message(self, to: str, msg_type: str, body: str):
        """Utility method for standardized communication."""
        msg = Message(to=to, metadata={"type": msg_type}, body=body)
        await self.send(msg)
        print(f"[{self.name}] → Sent to {to} ({msg_type}): {body}")

    # -------------------------------------------------------------------------
    # BEHAVIOURS
    # -------------------------------------------------------------------------
    class MapTerrain(CyclicBehaviour):
        async def on_start(self):
            print(f"[{self.agent.name}] Starting terrain mapping...")

        async def run(self):
            drone = self.agent
            # Example scanning logic
            scan_data = {"position": tuple(drone.position), "resource_sites": [], "danger_zones": []}
            print(f"[{drone.name}] Scanning area around {drone.position}")

            # Send map data to Base
            await drone.send_message("base@planet.local", "map_data", str(scan_data))

            await asyncio.sleep(3)

    class ReturnToBase(CyclicBehaviour):
        async def run(self):
            drone = self.agent

            dx, dy = drone.get_dpos(drone.position, drone.base_position)
            drone.position[0] += dx
            drone.position[1] += dy
            drone.energy -= drone.energy_consump_rate

            print(f"[{drone.name}] Returning to base... Pos: {tuple(drone.position)} | Energy: {drone.energy}%")

            await drone.send_message("base@planet.local", "status",
                                     f"Returning to base. Energy: {drone.energy}%")

            # If arrived
            if tuple(drone.position) == drone.base_position:
                print(f"[{drone.name}] Arrived at base. Charging...")
                while drone.energy < drone.max_energy:
                    drone.energy += drone.max_energy // 20
                    if drone.energy > drone.max_energy:
                        drone.energy = drone.max_energy
                    await asyncio.sleep(1)
                    print(f"[{drone.name}] Charging... {drone.energy}%")

                await drone.send_message("base@planet.local", "status",
                                         "Fully charged. Ready for next mission.")
                drone.add_behaviour(drone.ExploreTerrain())
                self.kill()

            await asyncio.sleep(1)

    class ExploreTerrain(CyclicBehaviour):
        async def run(self):
            drone = self.agent

            # Check if enough energy to continue
            if drone.energy <= drone.energy_limit(drone.position, drone.base_position):
                print(f"[{drone.name}] Low energy - returning to base.")
                drone.add_behaviour(drone.ReturnToBase())
                self.kill()
                return

            # Move one step toward goal
            dx, dy = drone.get_dpos(drone.position, drone.goal)
            drone.position[0] += dx
            drone.position[1] += dy
            drone.energy -= drone.energy_consump_rate

            print(f"[{drone.name}] Exploring... Pos: {tuple(drone.position)} | Energy: {drone.energy}%")

            # Broadcast to nearby rovers/drones
            await drone.send_message("rover@planet.local", "status",
                                     f"Current position: {tuple(drone.position)} | Energy: {drone.energy}%")

            # If goal reached
            if tuple(drone.position) == drone.goal:
                print(f"[{drone.name}] Arrived at goal. Starting terrain mapping...")
                drone.add_behaviour(drone.MapTerrain())
                self.kill()

            await asyncio.sleep(2)

    class Analyze(CyclicBehaviour):
        async def run(self):
            drone = self.agent
            # Simulate periodic system diagnostics
            diagnostics = {
                "energy": drone.energy,
                "position": tuple(drone.position),
                "status": "operational" if drone.energy > 0 else "offline"
            }
            await drone.send_message("mechanic@planet.local", "system_info", str(diagnostics))
            await asyncio.sleep(20)

    # -------------------------------------------------------------------------
    async def setup(self):
        print(f"[{self.name}] Drone online at position {self.position}")
        self.add_behaviour(self.ExploreTerrain())
        self.add_behaviour(self.Analyze())

