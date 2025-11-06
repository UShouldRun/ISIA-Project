import spade
import asyncio
import random

from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, CyclicBehaviour
from spade.message import Message

from math import sqrt
from typing import Tuple, List

class Rover(Agent):
    def __init__(
        self, jid: int, password: str,
        position: Tuple[float, float] = (0, 0), base_position: Tuple[float, float] = (0, 0),
        max_energy: int = 10000, energy_consump_rate: int = 1
    ) -> None:
        super().__init__(jid, password)
        self.position = list(position)
        self.base_position = tuple(base_position)
        self.energy = max_energy
        self.max_energy = max_energy
        self.energy_consump_rate = energy_consump_rate
        self.goal = None
        self.detected_resources = []

    def energy_limit(self, curr_pos: Tuple[float, float], base_pos: Tuple[float, float]) -> int:
        return self.energy_consump_rate * int(sqrt((curr_pos[0] - base_pos[0]) ** 2 + (curr_pos[1] - base_pos[1]) ** 2))

    def get_dpos(self, curr: Tuple[float, float], goal: Tuple[float, float]) -> float:
        return (
            1 if curr[0] < goal[0] else -1 if curr[0] > goal[0] else 0,
            1 if curr[1] < goal[1] else -1 if curr[1] > goal[1] else 0
        )

    class WaitForMission(CyclicBehaviour):
        async def run(self):
            print(f"[{self.agent.name}] Awaiting mission...")
            msg = await self.receive(timeout=15)

            if msg and msg.metadata.get("type") == "mission":
                self.agent.goal = eval(msg.body)  # Example: body = "(5, 10)"
                print(f"[{self.agent.name}] New destination received: {self.agent.goal}")

                if self.agent.energy < 30:
                    print(f"[{self.agent.name}] Insufficient energy ({self.agent.energy}%). Charging...")
                    await asyncio.sleep(5)
                    return

                self.agent.add_behaviour(self.agent.ExploreTerrain())

            else:
                print(f"[{self.agent.name}] No mission received. Continuing on standby...")
                await asyncio.sleep(5)

    class ExploreTerrain(CyclicBehaviour): # Is this a cyclic behaviour
        async def on_start(self):
            print(f"[{self.agent.name}] Starting exploration to {self.agent.goal}...")

        async def run(self):
            """Moves to goal location"""
            rover = self.agent
            if rover.energy <= rover.energy_limit(rover.position, rover.base_position):
                print(f"[{rover.name}] Depleted energy!")
                rover.add_behaviour(rover.ReturnToBase())
                return

            dx, dy = rover.get_dpos(rover.position, rover.goal)
            rover.position[0] += dx
            rover.position[1] += dy
            rover.energy -= rover.energy_consump_rate

            print(f"[{rover.name}] Moved to: {tuple(rover.position)} | Energy: {rover.energy}%")

            if tuple(rover.position) == rover.goal:
                print(f"[{rover.name}] Arrived at destination! Starting analysis...")
                self.agent.add_behaviour(rover.AnalyzeSoil())

            await asyncio.sleep(2)

        async def on_end(self):
            """Stops to analyze"""
            print(f"[{self.agent.name}] Exploration completed.")

    class AnalyzeSoil(OneShotBehaviour): # Is this an one shot behaviour
        async def run(self):
            rover = self.agent
            print(f"[{rover.name}] To analyze soil in {tuple(rover.position)}...")

            await asyncio.sleep(1)
            found = random.random() < 0.3

            if found:
                resource = {"pos": tuple(rover.position), "type": random.choice(["H2O", "Fe", "Si"])}
                rover.detected_resources.append(resource)

                print(f"[{rover.name}] Resource found: {resource}")
                msg = Message(to="base@planet.local", body=str(resource), metadata={"performative": "inform", "type": "resource"})

                await self.send(msg)

    class DetectResources(CyclicBehaviour):
        async def run(self):
            rover = self.agent
            if random.random() < 0.1:
                print(f"[{rover.name}] Anomalous detection in the sensor!")
            await asyncio.sleep(3)

    class Communicate(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=5)
            if msg:
                print(f"[{self.agent.name}] Menssage received from {msg.sender}: {msg.body}")
            await asyncio.sleep(1)

    class ReturnToBase(CyclicBehaviour):
        async def on_start(self):
            print(f"[{self.agent.name}] Return to base {self.agent.base_position}...")

        async def run(self):
            rover = self.agent

            dx, dy = rover.get_dpos(rover.position, rover.goarover.position, rover.goall)
            rover.position[0] += dx
            rover.position[1] += dy

            print(f"[{rover.name}] Returning... position: {tuple(rover.position)}")

            if tuple(rover.position) == rover.base_position:
                print(f"[{rover.name}] Arrived at the base with {rover.energy}% of energy.")
                print(f"[{rover.name}] Starting charging...")

                while rover.energy < rover.max_energy:
                    rover.energy += rover.max_energy // 20
                    if rover.energy > rover.max_energy:
                        rover.energy = rover.max_energy

                    print(f"[{rover.name}] Charging... {rover.energy}%")
                    await asyncio.sleep(1)

                print(f"[{rover.name}] Fully charged battery.")

                msg = Message(
                    to="base@planet.local",
                    body="Battery charged. Ready for next mission.",
                    metadata={"type": "status"}
                )
                await self.send(msg)

                print(f"[{rover.name}] Status sent to the base.")
                rover.add_behaviour(rover.WaitForMission())

                return

            await asyncio.sleep(1)

    async def setup(self):
        print(f"[{self.name}] Started in position {self.position}")
        self.add_behaviour(self.Communicate())
        self.add_behaviour(self.WaitForMission())
        self.add_behaviour(self.DetectResources())
