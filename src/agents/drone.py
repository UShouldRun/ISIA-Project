import spade
import asyncio
import random
from math import sqrt
from typing import Tuple, List, Dict, Optional

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message

from world.map import Map, AStar
from world.world import World

class Drone(Agent):
    def __init__(
        self,
        jid: str,
        password: str,
        world: World,
        map: Map,
        base_position: Tuple[float, float],
        assigned_rover: str,
        move_step: float = 10.0,
        energy_consump_rate: float = 0.5,
    ) -> None:
        super().__init__(jid, password)
        self.world = world
        self.map = map
        self.position = base_position
        self.base_position = base_position
        self.assigned_rover = assigned_rover
        self.move_step = move_step
        self.energy_consump_rate = energy_consump_rate

        self.energy = 100
        self.status = "idle"
        self.goal: Optional[Tuple[float, float]] = None

    # -------------------------------------------------------------------------
    # UTILITIES
    # -------------------------------------------------------------------------
    async def send_msg(self, to: str, performative: str, ontology: str, body: str):
        msg = Message(
            to=to,
            metadata={"performative": performative, "ontology": ontology},
            body=body,
        )
        await self.send(msg)
        print(f"[{self.name}] → {to} ({performative}/{ontology}): {body}")

    def energy_limit(self, curr_pos: Tuple[float, float]) -> int:
        """Minimum energy needed to return to base."""
        bx, by = self.base_position
        return int(self.energy_consump_rate * sqrt((curr_pos[0] - bx) ** 2 + (curr_pos[1] - by) ** 2))

    def get_dpos(self, curr: Tuple[float, float], goal: Tuple[float, float]) -> Tuple[int, int]:
        """Compute a one-step delta towards the goal."""
        return (
            1 if curr[0] < goal[0] else -1 if curr[0] > goal[0] else 0,
            1 if curr[1] < goal[1] else -1 if curr[1] > goal[1] else 0,
        )

    async def try_go_around(self, goal: Tuple[float, float]) -> Optional[Tuple[float, float]]:
        """Try a simple local detour around an obstacle."""
        for _ in range(5):
            offset_x = random.uniform(-15, 15)
            offset_y = random.uniform(-15, 15)
            candidate = (self.position[0] + offset_x, self.position[1] + offset_y)
            if not self.world.collides(self.jid, candidate):
                print(f"[{self.name}] Avoiding obstacle → {candidate}")
                return candidate
        return None

    # -------------------------------------------------------------------------
    # BEHAVIOURS
    # -------------------------------------------------------------------------
    class DroneControl(CyclicBehaviour):
        async def run(self):
            drone = self.agent
            msg = await self.receive(timeout=5)
            if not msg:
                await asyncio.sleep(1)
                return

            performative = msg.metadata.get("performative")
            ontology = msg.metadata.get("ontology")
            sender = str(msg.sender)

            # ---------------------------------------------------------
            # BASE → DRONE : mission request
            # ---------------------------------------------------------
            if performative == "request" and ontology == "assign_goal":
                data = eval(msg.body)
                goal = tuple(data["goal"])
                print(f"[{drone.name}] Received mission: navigate rover to {goal}")

                path = AStar.run(drone.map, start=drone.position, goal=goal)
                if path:
                    await drone.send_msg(
                        to=drone.assigned_rover,
                        performative="inform",
                        ontology="path_to_goal",
                        body=str(path),
                    )
                    drone.status = "assisting"
                else:
                    print(f"[{drone.name}] Could not find path to goal {goal}")

            # ---------------------------------------------------------
            # ROVER → DRONE : reroute request
            # ---------------------------------------------------------
            elif performative == "request" and ontology == "reroute":
                data = eval(msg.body)
                curr = tuple(data["current"])
                goal = tuple(data["goal"])
                print(f"[{drone.name}] Reroute requested by {sender} → from {curr} to {goal}")

                path = AStar.run(drone.map, start=curr, goal=goal)
                if path:
                    await drone.send_msg(
                        to=sender,
                        performative="inform",
                        ontology="path_to_goal",
                        body=str(path),
                    )
                    print(f"[{drone.name}] Sent new reroute path to {sender}")
                else:
                    print(f"[{drone.name}] Could not compute reroute path from {curr} to {goal}")

            # ---------------------------------------------------------
            # ROVER → DRONE : request return path to base
            # ---------------------------------------------------------
            elif performative == "request" and ontology == "return_path":
                data = eval(msg.body)
                curr = tuple(data["current"])
                base = drone.base_position
                print(f"[{drone.name}] Return-to-base path requested from {curr}")

                path = AStar.run(drone.map, start=curr, goal=base)
                if path:
                    await drone.send_msg(
                        to=sender,
                        performative="inform",
                        ontology="return_path_to_base",
                        body=str(path),
                    )
                    print(f"[{drone.name}] Sent return path to base for {sender}")
                else:
                    print(f"[{drone.name}] Could not compute return path from {curr} to {base}")

            await asyncio.sleep(1)

    # -------------------------------------------------------------------------
    # SETUP
    # -------------------------------------------------------------------------
    async def setup(self):
        print(f"[{self.name}] Drone initialized at {self.position}, waiting for missions.")
        self.add_behaviour(self.DroneControl())
