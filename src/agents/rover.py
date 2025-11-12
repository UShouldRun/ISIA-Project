import spade
import asyncio
import random
from math import sqrt
from typing import Tuple, List, Dict, Optional

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message

from world.world import World, WorldObject

from settings import *

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

        # TODO: IMPLEMENT ENERGY CONSUMPTION
        self.energy = 100
        self.path: List[Tuple[float, float]] = []
        self.goal: Optional[Tuple[float, float]] = None
        self.status = "idle"
        self.is_locked_by_bid = False

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

    def calculate_distance(self, pos1: Tuple[float, float], pos2: Tuple[float, float]) -> float:
        return sqrt((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2)

    def calculate_pathfinding_cost(self, start_pos: Tuple[float, float], target_pos: Tuple[float, float]) -> float:
            """
            Slightly randomized Euclidean distance.
            """
            euclidean_dist = self.calculate_distance(start_pos, target_pos)
            # Simulate complexity by making the pathfinding distance 10-30% longer than straight-line
            return euclidean_dist * random.uniform(1.1, 1.3)

    def compute_mission_time(self, target_pos: Tuple[float, float]) -> float:
        current_energy = self.energy
        
        # 1. Calculate an approximation of the distance that the rover will have to go (2-way trip: Base -> Target -> Base)
        # We use the base position as the starting point.
        # We use eucledian distance for the approximation

        dist_to_target = self.calculate_pathfinding_cost(self.position, target_pos)
        dist_to_base_after = self.calculate_pathfinding_cost(target_pos, self.position)
        total_distance = dist_to_target + dist_to_base_after

        # 2. Calculate the energy required
        energy_required = total_distance * ENERGY_PER_DISTANCE_UNIT
        
        # 3. Calculate Time Needed (The Bid Cost)
        time_to_charge = 0.0

        if current_energy < energy_required:
            # Calculate time needed to charge the difference
            energy_needed_to_charge = energy_required - current_energy
            time_to_charge = energy_needed_to_charge / CHARGE_RATE_ENERGY_PER_SEC
            
        # Time to execute the mission (travel time)
        time_to_travel = total_distance / ROVER_SPEED_UNIT_PER_SEC
        
        # The total mission time (cost) includes charge time and travel time
        mission_time = time_to_charge + time_to_travel

        return mission_time

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
            # BASE → ROVER : Inform about internal stats
            # --------------------------
            if performative == "cfp" and ontology == "rover_bid_cfp":
                target_pos = eval(msg.body)
                print(f"[{rover.name}] Received Bid request from Base for {target_pos}")

                # Check if rover is free
                if rover.is_locked_by_bid or rover.status != "idle":
                    # Already committed → refuse
                    reply = Message(to=str(msg.sender))
                    reply.set_metadata("performative", "refuse")
                    reply.set_metadata("ontology", "rover_bid_cfp")
                    reply.body = str({"reason": "busy or locked"})
                    await rover.send(reply)
                    print(f"[{rover.name}] REFUSING mission at {target_pos} (busy/locked)")
                else:
                    # Rover is available → propose
                    rover.is_locked_by_bid = True  # lock it for this bid
                    estimated_mission_time = rover.compute_mission_time(target_pos)
                    proposal = {"cost": estimated_mission_time, "rover": str(rover.jid)}
                    reply = Message(to=str(msg.sender))
                    reply.set_metadata("performative", "propose")
                    reply.set_metadata("ontology", "rover_bid_cfp")
                    reply.body = str(proposal)
                    await rover.send(reply)
                    print(f"[{rover.name}] PROPOSING mission at {target_pos} with cost {estimated_mission_time:.2f}")

            # Go to target
            elif performative == "accept_proposal" and ontology == "rover_bid_cfp":
                rover.status = "moving"
                rover.goal = eval(msg.body)["target"]
                print(f"[{rover.name}] ACCEPTED mission to {rover.goal}")

            # Reject proposal → stay idle
            elif performative == "reject_proposal" and ontology == "rover_bid_cfp":
                print(f"[{rover.name}] REJECTED for mission at {eval(msg.body)['target']}")

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
