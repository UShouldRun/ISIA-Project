import spade
import asyncio
import random
from math import sqrt
from typing import Tuple, List, Dict, Optional

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message

from world.world import World, WorldObject

class Rover(Agent):
    def __init__(
        self,
        jid: str,
        password: str,
        position: Tuple[float, float],
        world: World,
        assigned_drone: str,
        base_jid: str,
        move_step: float = 5.0,
        obstacle_radius: float = 5.0,
    ) -> None:
        super().__init__(jid, password)
        self.position = position
        self.world = world
        self.assigned_drone = assigned_drone
        self.base_jid = base_jid

        self.energy = 100
        self.path: List[Tuple[float, float]] = []
        self.goal: Optional[Tuple[float, float]] = None
        self.status = "idle"

        self.move_step = move_step
        self.obstacle_radius = obstacle_radius

        # Resource detection probabilities
        self.resource_probs = {
            "iron": 0.3,        # 30% chance
            "silicon": 0.2,     # 20% chance
            "water_ice": 0.1,   # 10% chance
        }

    # -------------------------------------------------------------------------
    # UTILITIES
    # -------------------------------------------------------------------------
    async def send_msg(
        self,
        to: str,
        performative: str,
        ontology: str,
        body: str,
    ):
        """Unified FIPA-compliant message sending."""
        msg = Message(
            to=to,
            metadata={"performative": performative, "ontology": ontology},
            body=body,
        )
        await self.send(msg)
        print(f"[{self.name}] → {to} ({performative}/{ontology}): {body}")

    def get_dpos(self, curr: Tuple[float, float], goal: Tuple[float, float]) -> Tuple[int, int]:
        """Compute one-step delta toward goal."""
        return (
            1 if curr[0] < goal[0] else -1 if curr[0] > goal[0] else 0,
            1 if curr[1] < goal[1] else -1 if curr[1] > goal[1] else 0,
        )

    async def try_go_around(self, goal: Tuple[float, float]) -> Optional[Tuple[float, float]]:
        """Try simple local avoidance: random offset around the obstacle."""
        for _ in range(5):
            offset_x = random.uniform(-10, 10)
            offset_y = random.uniform(-10, 10)
            candidate = (self.position[0] + offset_x, self.position[1] + offset_y)
            if not self.world.collides(self.jid, candidate):
                print(f"[{self.name}] Avoiding obstacle locally → {candidate}")
                return candidate
        return None

    # -------------------------------------------------------------------------
    # BEHAVIOURS
    # -------------------------------------------------------------------------
    class ReceiveMessages(CyclicBehaviour):
        async def run(self):
            rover = self.agent
            msg = await self.receive(timeout=5)
            if not msg:
                await asyncio.sleep(1)
                return

            performative = msg.metadata.get("performative")
            ontology = msg.metadata.get("ontology")
            sender = str(msg.sender)

            # --------------------------
            # DRONE → ROVER : Path to Goal
            # --------------------------
            if performative == "inform" and ontology == "path_to_goal":
                rover.path = eval(msg.body)
                rover.goal = rover.path[-1] if rover.path else None
                rover.status = "moving"
                print(f"[{rover.name}] Received new path ({len(rover.path)} steps) to {rover.goal}")

            # --------------------------
            # DRONE → ROVER : Return Path to Base
            # --------------------------
            elif performative == "inform" and ontology == "return_path_to_base":
                rover.path = eval(msg.body)
                rover.goal = rover.path[-1] if rover.path else None
                rover.status = "returning"
                print(f"[{rover.name}] Received return path ({len(rover.path)} steps) to base.")

            await asyncio.sleep(1)

    class MoveAlongPath(CyclicBehaviour):
        async def run(self):
            rover = self.agent
            if rover.status not in ["moving", "returning"] or not rover.path:
                await asyncio.sleep(2)
                return

            next_step = rover.path[0]
            dx, dy = rover.get_dpos(rover.position, next_step)
            new_pos = (rover.position[0] + dx * rover.move_step, rover.position[1] + dy * rover.move_step)

            if rover.world.collides(self.jid, new_pos):
                print(f"[{rover.name}] Collision detected near {new_pos}")

                # Attempt local avoidance
                alt = await rover.try_go_around(next_step)
                if alt:
                    rover.position = alt
                    print(f"[{rover.name}] Avoided obstacle locally.")
                else:
                    # Request reroute from drone
                    print(f"[{rover.name}] Could not avoid locally, requesting reroute.")
                    await rover.send_msg(
                        to=rover.assigned_drone,
                        performative="request",
                        ontology="reroute",
                        body=str({"current": rover.position, "goal": rover.goal}),
                    )
                    rover.status = "waiting"
                    return
            else:
                rover.position = new_pos
                dist_to_next_step = sqrt((rover.position[0] - next_step[0]) ** 2 + (rover.position[1] - next_step[1]) ** 2)
                if dist_to_next_step < 5:
                    rover.path.pop(0)

                print(f"[{rover.name}] Moving... Position: {rover.position}")

                # Mission goal reached
                if not rover.path:
                    if rover.status == "moving":
                        rover.status = "arrived"
                        print(f"[{rover.name}] Arrived at mission goal {rover.goal}")
                        await rover.send_msg(
                            to=rover.base_jid,
                            performative="inform",
                            ontology="mission_complete",
                            body=str({"position": rover.position}),
                        )

                        # Trigger soil analysis after mission
                        rover.add_behaviour(rover.AnalyzeSoil())

                        # Request path back to base
                        await rover.send_msg(
                            to=rover.assigned_drone,
                            performative="request",
                            ontology="return_path",
                            body=str({"current": rover.position, "base": rover.base_jid}),
                        )
                        rover.status = "waiting_return"

                    elif rover.status == "returning":
                        rover.status = "idle"
                        print(f"[{rover.name}] Returned to base successfully at {rover.position}")
                        await rover.send_msg(
                            to=rover.base_jid,
                            performative="inform",
                            ontology="returned_to_base",
                            body=str({"position": rover.position}),
                        )

            await asyncio.sleep(2)

    # -------------------------------------------------------------------------
    # NEW BEHAVIOUR — ANALYZE SOIL
    # -------------------------------------------------------------------------
    class AnalyzeSoil(CyclicBehaviour):
        async def run(self):
            rover = self.agent
            found_resources = []

            for resource, prob in rover.resource_probs.items():
                if random.random() < prob:
                    found_resources.append(resource)

            if found_resources:
                await rover.send_msg(
                    to=rover.base_jid,
                    performative="inform",
                    ontology="resources_found",
                    body=str({"position": rover.position, "resources": found_resources}),
                )
                print(f"[{rover.name}] Resources found at {rover.position}: {found_resources}")
            else:
                print(f"[{rover.name}] No resources found at {rover.position}.")

            self.kill()  # one-time analysis
            await asyncio.sleep(1)

    # -------------------------------------------------------------------------
    # SETUP
    # -------------------------------------------------------------------------
    async def setup(self):
        print(f"[{self.name}] Rover initialized at {self.position}, waiting for path.")
        self.add_behaviour(self.ReceiveMessages())
        self.add_behaviour(self.MoveAlongPath())

