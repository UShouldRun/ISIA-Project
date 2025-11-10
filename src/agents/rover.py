import spade
import asyncio
import random

from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, CyclicBehaviour
from spade.message import Message
from math import sqrt
from typing import Tuple, List

from settings import *

class Rover(Agent):
    def __init__(
        self, jid: int, password: str,
        position: Tuple[float, float] = (0, 0),
        base_position: Tuple[float, float] = (0, 0),
        max_energy: int = 10000, energy_consump_rate: int = 1
    ) -> None:
        super().__init__(jid, password)
        self.position = list(position)
        self.base_position = tuple(base_position)
        self.energy = MAX_ROVER_CHARGE
        self.max_energy = MAX_ROVER_CHARGE
        self.energy_consump_rate = energy_consump_rate
        self.goal = None
        self.detected_resources = []

    def energy_limit(self, curr_pos: Tuple[float, float], base_pos: Tuple[float, float]) -> int:
        return self.energy_consump_rate * int(
            sqrt((curr_pos[0] - base_pos[0]) ** 2 + (curr_pos[1] - base_pos[1]) ** 2)
        )

    def get_dpos(self, curr: Tuple[float, float], goal: Tuple[float, float]) -> Tuple[int, int]:
        return (
            1 if curr[0] < goal[0] else -1 if curr[0] > goal[0] else 0,
            1 if curr[1] < goal[1] else -1 if curr[1] > goal[1] else 0
        )

    async def send_message(self, to: str, msg_type: str, body: str):
        """Unified communication function for all rover behaviours."""
        msg = Message(to=to, metadata={"type": msg_type}, body=body)
        await self.send(msg)
        print(f"[{self.name}] → Sent to {to} ({msg_type}): {body}")

    # -------------------------------------------------------------------------
    # BEHAVIOURS
    # -------------------------------------------------------------------------
    class WaitForMission(CyclicBehaviour):
        async def run(self):
            print(f"[{self.agent.name}] Awaiting mission...")
            msg = await self.receive(timeout=15)

            if msg and msg.metadata.get("type") == "mission":
                rover = self.agent
                rover.goal = eval(msg.body)
                print(f"[{rover.name}] New destination received: {rover.goal}")

                await rover.send_message("satellite@planet.local", "ack",
                                         f"Mission received: {rover.goal}")

                if rover.energy < 30:
                    print(f"[{rover.name}] Insufficient energy ({rover.energy}%). Charging...")
                    await rover.send_message("base@planet.local", "status",
                                             "Insufficient energy to start mission.")
                    await asyncio.sleep(5)
                    return

                rover.add_behaviour(rover.ExploreTerrain())
            else:
                print(f"[{self.agent.name}] No mission received. Continuing on standby...")
                await asyncio.sleep(5)

    class ExploreTerrain(CyclicBehaviour):
        async def on_start(self):
            print(f"[{self.agent.name}] Starting exploration to {self.agent.goal}...")

        async def run(self):
            rover = self.agent

            if rover.energy <= rover.energy_limit(rover.position, rover.base_position):
                print(f"[{rover.name}] Low energy detected. Returning to base.")
                await rover.send_message("base@planet.local", "status", "Energy low, returning to base.")
                rover.add_behaviour(rover.ReturnToBase())
                self.kill()
                return

            dx, dy = rover.get_dpos(rover.position, rover.goal)
            rover.position[0] += dx
            rover.position[1] += dy
            rover.energy -= rover.energy_consump_rate

            print(f"[{rover.name}] Moved to: {tuple(rover.position)} | Energy: {rover.energy}%")

            # Send update to nearby Drone (coordination)
            await rover.send_message("drone@planet.local", "status",
                                     f"Position: {tuple(rover.position)}, Energy: {rover.energy}%")

            if tuple(rover.position) == rover.goal:
                print(f"[{rover.name}] Arrived at destination! Starting analysis...")
                rover.add_behaviour(rover.AnalyzeSoil())
                self.kill()

            await asyncio.sleep(2)

        async def on_end(self):
            print(f"[{self.agent.name}] Exploration completed.")

    class AnalyzeSoil(OneShotBehaviour):
        async def run(self):
            rover = self.agent
            print(f"[{rover.name}] Analyzing soil at {tuple(rover.position)}...")

            await asyncio.sleep(1)
            found = random.random() < 0.3

            if found:
                resource = {"pos": tuple(rover.position), "type": random.choice(["H2O", "Fe", "Si"])}
                rover.detected_resources.append(resource)
                print(f"[{rover.name}] Resource found: {resource}")

                await rover.send_message("base@planet.local", "resource", str(resource))
            else:
                await rover.send_message("drone@planet.local", "status",
                                         f"No resource found at {tuple(rover.position)}")

    class DetectResources(CyclicBehaviour):
        async def run(self):
            rover = self.agent
            if random.random() < 0.1:
                print(f"[{rover.name}] Sensor anomaly detected.")
                await rover.send_message("mechanic@planet.local", "alert",
                                         "Sensor anomaly detected.")
            await asyncio.sleep(3)

    class ReturnToBase(CyclicBehaviour):
        async def on_start(self):
            print(f"[{self.agent.name}] Returning to base at {self.agent.base_position}...")

        async def run(self):
            rover = self.agent
            dx, dy = rover.get_dpos(rover.position, rover.base_position)
            rover.position[0] += dx
            rover.position[1] += dy
            rover.energy -= rover.energy_consump_rate

            print(f"[{rover.name}] Returning... position: {tuple(rover.position)}, energy: {rover.energy}%")

            await rover.send_message("base@planet.local", "status",
                                     f"Returning to base. Current position: {tuple(rover.position)}")

            if tuple(rover.position) == rover.base_position:
                print(f"[{rover.name}] Arrived at base with {rover.energy}% energy. Charging...")
                await rover.send_message("base@planet.local", "status",
                                         f"Arrived at base with {rover.energy}% energy. Starting recharge.")

                while rover.energy < rover.max_energy:
                    rover.energy += rover.max_energy // 20
                    if rover.energy > rover.max_energy:
                        rover.energy = rover.max_energy
                    print(f"[{rover.name}] Charging... {rover.energy}%")
                    await asyncio.sleep(1)

                print(f"[{rover.name}] Fully charged and ready.")
                await rover.send_message("base@planet.local", "status",
                                         "Fully charged. Ready for new mission.")

                rover.add_behaviour(rover.WaitForMission())
                self.kill()
            await asyncio.sleep(1)

    # -------------------------------------------------------------------------
    # SETUP
    # -------------------------------------------------------------------------
    async def setup(self):
        print(f"[{self.name}] Rover online at position {self.position}")
        self.add_behaviour(self.WaitForMission())
        self.add_behaviour(self.DetectResources())
