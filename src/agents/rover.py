import spade
import asyncio
import random
from math import sqrt
from typing import Tuple, List, Dict, Optional

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message

from world.world import World, WorldObject
from world.map import Map, AStar

from settings import *

from agents.visualizator import VisualizationBehaviour, VisualizationMixin

class Rover(VisualizationMixin, Agent):
    """
    Rover agent responsible for pathfinding, movement, bidding for missions,
    and resource analysis on a simulated planetary surface.

    Attributes:
        position (Tuple[float, float]): Current rover position.
        world (World): Simulation world containing obstacles and agents.
        map (Map): Navigation map used for pathfinding.
        base_jid (str): JID of the base station.
        base_position (Tuple[float, float]): Initial rover position (base).
        energy (float): Current battery level.
        path (List[Tuple[float, float]]): Computed movement path.
        goal (Optional[Tuple[float, float]]): Mission destination.
        status (str): Current rover state.
        is_locked_by_bid (bool): Whether rover is locked due to bidding.
        is_on_base (bool): Whether rover is currently on base.
        move_step (float): Maximum distance rover can move per tick.
        obstacle_radius (float): Collision radius for obstacles.
        resource_probs (Dict[str, float]): Probabilities of discovering resources.
        viz_server: Visualization server reference.
    """

    def __init__(
        self,
        jid: str,
        password: str,
        position: Tuple[float, float],
        world: World,
        map: Map,
        base_jid: str,
        base_radius: float = 5.0,
        move_step: float = ROVER_SPEED_UNIT_PER_SEC,
        obstacle_radius: float = 1.0,
        viz_server = None
    ) -> None:
        """
        Initialize a Rover agent.

        Args:
            jid (str): Agent JID.
            password (str): Agent password.
            position (Tuple[float, float]): Starting position.
            world (World): Simulation world.
            map (Map): Navigation map.
            base_jid (str): Base station JID.
            base_radius (float): Base collision radius.
            move_step (float): Movement step size.
            obstacle_radius (float): Obstacle collision radius.
            viz_server: Optional visualization server.
        """
        super().__init__(jid, password)
        self.position = position
        self.world = world
        self.map = map
        self.base_jid = base_jid
        self.base_position = position

        self.energy = MAX_ROVER_CHARGE

        self.curr = 0
        self.path: List[Tuple[float, float]] = []
        self.goal: Optional[Tuple[float, float]] = None

        self.status = "idle"
        self.is_locked_by_bid = False
        self.is_on_base = True

        self.move_step = move_step
        self.obstacle_radius = obstacle_radius

        self.resource_probs = {
            "iron": 0.3,
            "silicon": 0.2,
            "water_ice": 0.1,
        }

        self.viz_server = viz_server
        if self.viz_server:
            self.setup_visualization(
                self.viz_server,
                agent_type="rover",
                agent_jid=jid,
                position=position,
                battery=self.energy,
                color="#00ffff"
            )

    # -------------------------------------------------------------------------
    # UTILITIES
    # -------------------------------------------------------------------------
    def get_dpos(self, curr: Tuple[float, float], next: Tuple[float, float]) -> Tuple[int, int]:
        """
        Compute the directional delta between two points.

        Args:
            curr (Tuple[float, float]): Current position.
            next (Tuple[float, float]): Target position.

        Returns:
            Tuple[int, int]: Delta vector.
        """
        return (next[0] - curr[0], next[1] - curr[1])

    async def try_go_around(self, goal: Tuple[float, float]) -> Optional[Tuple[float, float]]:
        """
        Attempt simple local obstacle avoidance using random offsets.

        Args:
            goal (Tuple[float, float]): Target waypoint.

        Returns:
            Optional[Tuple[float, float]]: New temporary position or None.
        """
        for _ in range(5):
            offset_x = random.uniform(-0.5 * ROVER_SPEED_UNIT_PER_SEC, 0.5 * ROVER_SPEED_UNIT_PER_SEC)
            offset_y = random.uniform(-0.5 * ROVER_SPEED_UNIT_PER_SEC, 0.5 * ROVER_SPEED_UNIT_PER_SEC)
            candidate = (self.position[0] + offset_x, self.position[1] + offset_y)
            if not self.world.collides(self.jid, candidate):
                print(f"{CYAN}[{self.name}] Avoiding obstacle locally → {candidate}{RESET}")
                return candidate
        return None

    async def find_path(self) -> str:
        """
        Compute an A* path to the current rover goal.

        Returns:
            str: Status code indicating result ("viable", "no_path", "not_enough_energy").
        """
        rover = self

        rover.path = AStar.run(rover.map, rover.position, rover.goal)
        if not rover.path:
            print(f"{CYAN}[{rover.name}] Did not find path to the goal, rejecting mission{RESET}")
            rover.status = "idle"
            rover.goal = None
            return "no_path"
        print(f"{CYAN}[{rover.name}] Found path to the goal{RESET}")

        distance = sum(
            rover.calculate_distance(rover.path[i - 1], rover.path[i])
            for i in range(1, len(rover.path))
        )
        if rover.energy < 1.10 * 2 * distance * ENERGY_PER_DISTANCE_UNIT:
            print(f"{CYAN}[{rover.name}] Low on energy; rejecting mission to {rover.goal}{RESET}")
            rover.status = "idle"
            rover.goal = None
            rover.path = []
            return "not_enough_energy"

        print(f"{CYAN}[{rover.name}] Found path to the goal and has enough energy; accepting mission to {rover.goal}{RESET}")
        rover.status = "moving"
        return "viable"

    def calculate_distance(self, pos1: Tuple[float, float], pos2: Tuple[float, float]) -> float:
        """
        Compute Euclidean distance between two points.

        Args:
            pos1 (Tuple[float, float]): First point.
            pos2 (Tuple[float, float]): Second point.

        Returns:
            float: Euclidean distance.
        """
        return sqrt((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2)

    def calculate_pathfinding_cost(self, start_pos: Tuple[float, float], target_pos: Tuple[float, float]) -> float:
        """
        Estimate pathfinding cost using randomized Euclidean distance.

        Args:
            start_pos (Tuple[float, float]): Starting point.
            target_pos (Tuple[float, float]): Target point.

        Returns:
            float: Cost estimate.
        """
        euclidean_dist = self.calculate_distance(start_pos, target_pos)
        return euclidean_dist * random.uniform(1.0, 1.1)

    def compute_mission_time(self, target_pos: Tuple[float, float]) -> float:
        """
        Compute estimated total mission time for bidding.

        Args:
            target_pos (Tuple[float, float]): Mission target.

        Returns:
            float: Estimated mission time in seconds.
        """
        current_energy = self.energy

        dist_to_target = self.calculate_pathfinding_cost(self.position, target_pos)
        dist_to_base_after = self.calculate_pathfinding_cost(target_pos, self.position)
        total_distance = dist_to_target + dist_to_base_after

        energy_required = total_distance * ENERGY_PER_DISTANCE_UNIT

        time_to_charge = 0.0
        if current_energy < energy_required:
            energy_needed_to_charge = energy_required - current_energy
            time_to_charge = energy_needed_to_charge / CHARGE_RATE_ENERGY_PER_SEC

        time_to_travel = total_distance / ROVER_SPEED_UNIT_PER_SEC

        mission_time = time_to_charge + time_to_travel

        return mission_time

    # -------------------------------------------------------------------------
    # BEHAVIOURS
    # -------------------------------------------------------------------------
    class Charge(CyclicBehaviour):
        """
        Behaviour handling rover battery charging when on base.
        """
        async def run(self):
            """
            Periodically charge the rover's battery while it is on base and
            publish status updates to the visualizer.

            This method runs as a cyclic behaviour and increments the rover's
            energy by CHARGE_RATE_ENERGY_PER_SEC every second until the
            battery reaches MAX_ROVER_CHARGE. It also prints textual status
            messages at several charge thresholds.
            """
            rover = self.agent

            if rover.is_on_base:
                if MAX_ROVER_CHARGE * 0.97 <= rover.energy <= MAX_ROVER_CHARGE * 0.99:
                    print(f"{CYAN}[{self.agent.name}] Rover Max charge reached - Current Charge: 100%{RESET}")

                elif MAX_ROVER_CHARGE * 0.75 <= rover.energy <= MAX_ROVER_CHARGE * 0.80 :
                    print(f"{CYAN}[{self.agent.name}] Rover Charging - Current Charge: 75%{RESET}")
                
                elif MAX_ROVER_CHARGE * 0.5 <= rover.energy <= MAX_ROVER_CHARGE * 0.55:
                    print(f"{CYAN}[{self.agent.name}] Rover Charging - Current Charge: 50%{RESET}")

                elif MAX_ROVER_CHARGE * 0.25 <= rover.energy <= MAX_ROVER_CHARGE * 0.30:
                    print(f"{CYAN}[{self.agent.name}] Rover Charging - Current Charge: 25%{RESET}")

                elif rover.energy == 0:
                    print(f"{CYAN}[{rover.name}] Rover Charging - Current Charge: 0%{RESET}")

                if rover.energy < MAX_ROVER_CHARGE:
                    rover.energy += CHARGE_RATE_ENERGY_PER_SEC

                if rover.energy >= MAX_ROVER_CHARGE:
                    rover.energy = MAX_ROVER_CHARGE

            await rover.viz_update_battery(100 * rover.energy / MAX_ROVER_CHARGE)
            await asyncio.sleep(1)
    
    class ReceiveMessages(CyclicBehaviour):
        """
        Behaviour responsible for receiving and handling incoming XMPP messages.

        The behaviour processes bid requests from the base, sends proposals or
        refusals, accepts/rejects mission confirmations, and updates rover
        state based on incoming informs. It communicates with the base using
        structured Message objects with metadata and a stringified body.
        """
        async def run(self):
            """
            Wait for messages with a short timeout and handle several
            performatives:

            - cfp / rover_bid_cfp: evaluate mission and send a proposal or refuse
            - accept_proposal: start moving toward the accepted target
            - reject_proposal: unlock and remain idle
            - inform (return_path_to_base): receive a return path and update state

            The method uses eval() to parse message bodies that were serialized
            with str(dict). It also forwards human-readable updates to the
            visualizer.
            """
            rover = self.agent
            msg = await self.receive(timeout=5)
            if not msg:
                await asyncio.sleep(1)
                return

            performative = msg.metadata.get("performative")
            msg_type = msg.metadata.get("type")
            sender = str(msg.sender)

            # --------------------------
            # BASE → ROVER : Bid Request
            # --------------------------
            if performative == "cfp" and msg_type == "rover_bid_cfp":
                target_pos = eval(msg.body)
                print(f"{CYAN}[{rover.name}] Received Bid request from Base for {target_pos}{RESET}")
                await rover.viz_send_message(f"Received mission bid request for {target_pos}")

                # Check if rover is free
                if rover.is_locked_by_bid or rover.status != "idle":
                    # Already committed → refuse
                    reply = Message(
                        to=sender,
                        metadata={"performative": "refuse", "type": "rover_bid_cfp"},
                        body=str({"reason": "busy or locked"})
                    )
                    await self.send(reply)
                    print(f"{CYAN}[{rover.name}] REFUSING mission at {target_pos} (busy/locked){RESET}")
                    await rover.viz_send_message(f"Refused mission at {target_pos} (busy/locked)")

                else:
                    # Rover is available → propose
                    rover.is_locked_by_bid = True  # lock it for this bid

                    rover.goal = target_pos
                    mission_status = await rover.find_path()
                    if mission_status != "viable":
                        rover.is_locked_by_bid = False
                        reply = Message(
                            to=sender,
                            metadata={"performative": "refuse", "type": "rover_bid_cfp"},
                            body=str({"reason": mission_status})
                        )
                        await self.send(reply)
                        print(f"{CYAN}[{rover.name}] REFUSING mission at {target_pos} ({mission_status}){RESET}")
                        await rover.viz_send_message(f"Refused mission at {target_pos} ({mission_status})")
                        return

                    estimated_mission_time = rover.compute_mission_time(target_pos)
                    proposal = {"cost": estimated_mission_time, "rover": str(rover.jid)}
                    reply = Message(
                        to=sender,
                        metadata={"performative": "propose", "type": "rover_bid_cfp"},
                        body=str(proposal)
                    )
                    await self.send(reply)
                    print(f"{CYAN}[{rover.name}] PROPOSING mission at {target_pos} with cost {estimated_mission_time:.2f}{RESET}")
                    await rover.viz_send_message(f"Submitted bid for {target_pos} (cost: {estimated_mission_time:.1f}s)")

            # Go to target
            elif performative == "accept_proposal" and msg_type == "rover_bid_cfp":
                rover.status = "moving"
                rover.goal = eval(msg.body)["target"]
                rover.is_locked_by_bid = False  # Unlock after acceptance
                rover.is_on_base = False # Out of base

                print(f"{CYAN}[{rover.name}] ACCEPTED mission to {rover.goal}{RESET}")
                await rover.viz_send_message(f"Mission accepted! Moving to {rover.goal}")
                rover.add_behaviour(rover.MoveAlongPath())

            # Reject proposal → unlock and stay idle
            elif performative == "reject_proposal" and msg_type == "rover_bid_cfp":
                rover.is_locked_by_bid = False  # Unlock the rover
                rover.status = "idle"
                rover.goal = None
                rover.path = []
                print(f"{CYAN}[{rover.name}] REJECTED for mission at {eval(msg.body)['target']}{RESET}")
                await rover.viz_send_message(f"Bid rejected for mission at {eval(msg.body)['target']}")

            # --------------------------
            # Inform on rover stats
            # --------------------------
            elif performative == "inform" and ontology == "return_path_to_base":
                rover.path = eval(msg.body)
                rover.goal = rover.path[-1] if rover.path else None
                rover.status = "returning"
                rover.is_locked_by_bid = False
                print(f"[{rover.name}] Received return path ({len(rover.path)} steps) to base.")

            await asyncio.sleep(1)

    class MoveAlongPath(CyclicBehaviour):
        """
        Behaviour that moves the rover along a previously computed path.

        Responsibilities:
        - Notify the base when leaving
        - Step the rover position along the path according to move_step and
          simulation speed
        - Detect collisions and attempt local avoidance
        - Trigger mission-complete events and start analysis behaviour
        """
        async def on_start(self) -> None:
            """
            Called when the behaviour is added to the agent. If the rover is in
            the moving state it sends an inform message to the base announcing
            departure.
            """
            rover = self.agent 

            if rover.status == "moving":
                print(f"{CYAN}[{rover.name}] Informing moving to goal to base{RESET}")
                msg = Message(
                    to=rover.base_jid,
                    metadata={"performative": "inform", "type": "rover_leaving_base"},
                    body=str({"goal": rover.goal})
                )
                await self.send(msg)

        async def run(self):
            """
            Execute a single movement step along the rover's path. The method
            performs checks for valid goal/state/path, computes the next
            position, updates energy, handles collisions, and triggers
            subsequent behaviours when the rover arrives at its destination or
            returns to base.
            """
            rover = self.agent

            if rover.goal == None:
                print(f"{CYAN}[{rover.name}] No goal set, cancelling MoveAlongPath{RESET}")
                self.kill()
                await asyncio.sleep(2)
                return

            if rover.status not in ["moving", "returning"]:
                print(f"{CYAN}[{rover.name}] Doing another task, cancelling MoveAlongPath{RESET}")
                self.kill()
                await asyncio.sleep(2)
                return

            if not rover.path:
                print(f"{CYAN}[{rover.name}] could not compute path to goal {rover.goal}{RESET}")
                self.kill()
                await asyncio.sleep(2)
                return

            s_path = len(rover.path)

            if rover.curr >= s_path:
                rover.curr = s_path - 1            

            next_is_goal = (
                (rover.status == "returning" or rover.status == "moving") and
                rover.curr == s_path - 1
            )

            next_step = rover.path[rover.curr] if not next_is_goal else rover.goal
            dist_to_next_step = rover.calculate_distance(rover.position, next_step) 

            dx, dy = rover.get_dpos(rover.position, next_step)
            step_strength = rover.move_step if not next_is_goal else min(rover.move_step, 1)
            step_size = min(step_strength, dist_to_next_step)

            dx /= dist_to_next_step
            dy /= dist_to_next_step

            new_pos = (rover.position[0] + dx * step_size, rover.position[1] + dy * step_size)

            rover.energy -= step_size * ENERGY_PER_DISTANCE_UNIT
            if rover.energy < 0:
                rover.energy = 0

            sleep_time = step_size / (SIMULATION_SPEED * ROVER_SPEED_UNIT_PER_SEC)
            await asyncio.sleep(max(0.001, sleep_time))

            collisions = list(filter(
                lambda collision: not "drone" in collision.id and collision.id != rover.base_jid,
                rover.world.collides(rover.jid, new_pos)
            ))
            s_collisions = len(collisions)
            if s_collisions > 0:
                print(f"{CYAN}[{rover.name}] collision detected near {new_pos}, collisions: {collisions}{RESET}")
                await rover.viz_send_message(f"collision detected! attempting to avoid obstacle")

                alt = await rover.try_go_around(next_step)
                if alt:
                    rover.position = alt
                    print(f"{CYAN}[{rover.name}] avoided obstacle locally.{RESET}")
                else:
                    print(f"{CYAN}[{rover.name}] could not avoid locally, crash.{RESET}")
                    await rover.viz_send_message(f"crash: unable to avoid obstacle")
                    return

            else:
                rover.position = new_pos

                distance_after_move = rover.calculate_distance(rover.position, next_step)
                arrived_next_step = distance_after_move <= COLLISION_RADIUS
                if arrived_next_step:
                    rover.position = next_step if not next_is_goal else rover.goal
                    rover.curr += 1
                    
                await rover.viz_update_position(rover.position)
                await rover.viz_update_battery(100 * rover.energy / MAX_ROVER_CHARGE)
 
                print(f"{CYAN}[{rover.name}] {rover.status}... current position: {rover.position}", end = '')
                print(f", energy: {(100 * rover.energy / MAX_ROVER_CHARGE):.1f}%", end = '')
                print(f", distance left: {rover.calculate_distance(rover.position, rover.goal)}{RESET}")

                if not arrived_next_step or rover.curr < s_path - 1:
                    return

                if rover.status == "moving":
                    rover.status = "arrived"

                    print(f"{CYAN}[{rover.name}] arrived at mission goal {rover.goal}{RESET}")
                    await rover.viz_send_message(f"arrived at target location {rover.goal}")
                    await rover.viz_update_status(rover.status)

                    msg = Message(
                        to=rover.base_jid,
                        metadata={"performative": "inform", "type": "mission_complete"},
                        body=str({"position": rover.position})
                    )
                    await self.send(msg)

                    rover.add_behaviour(rover.AnalyzeSoil())

                    self.kill()
                    rover.goal = rover.base_position
                    rover.status = "returning"
                    old_path = rover.path.reverse()

                    returning_status = await rover.find_path()
                    if returning_status != "viable":
                        rover.path = old_path
                        rover.goal = rover.base_position

                    rover.add_behaviour(rover.MoveAlongPath())

                elif rover.status == "returning":
                    rover.status = "idle"
                    rover.path = []
                    rover.goal = None
                    rover.is_on_base = True

                    print(f"{CYAN}[{rover.name}] returned to base successfully at {rover.position}{RESET}")
                    await rover.viz_send_message(f"successfully returned to base")
                    await rover.viz_update_status(rover.status)

                    msg = Message(
                        to=rover.base_jid,
                        metadata={"performative": "inform", "type": "rover_returned_to_base"},
                        body=str({"position": rover.position})
                    )

                    await self.send(msg)
                    self.kill()

    # -------------------------------------------------------------------------
    # NEW BEHAVIOUR — ANALYZE SOIL
    # -------------------------------------------------------------------------
    class AnalyzeSoil(CyclicBehaviour):
        """
        Behaviour that simulates a one-time soil/resource analysis at the rover's
        current location. It samples from defined probabilities and informs the
        base if resources are discovered.
        """
        async def run(self):
            """
            Execute resource sampling based on resource_probs. Sends an inform
            message to the base containing any discovered resources and then
            terminates the behaviour.
            """
            rover = self.agent
            found_resources = []

            for resource, prob in rover.resource_probs.items():
                if random.random() < prob:
                    found_resources.append(resource)

            if found_resources:
                msg = Message(
                    to=rover.base_jid,
                    metadata={"performative": "inform", "type": "resources_found"},
                    body=str({"position": rover.position, "resources": found_resources})
                )
                await self.send(msg)
                print(f"{CYAN}[{rover.name}] Resources found at {rover.position}: {found_resources}{RESET}")
                await rover.viz_send_message(f"Resources discovered: {', '.join(found_resources)}")
            else:
                print(f"{CYAN}[{rover.name}] No resources found at {rover.position}.{RESET}")
                await rover.viz_send_message(f"Soil analysis complete - no resources found")

            self.kill()  # one-time analysis
            await asyncio.sleep(1)

    # -------------------------------------------------------------------------
    # SETUP
    # -------------------------------------------------------------------------
    async def setup(self):
        """
        Agent setup method that registers initial behaviours and initializes
        visualization if available.

        This method is called by the SPADE framework when the agent starts.
        """
        print(f"{CYAN}Initializing [{self.name}] rover.{RESET}")
        self.add_behaviour(self.ReceiveMessages())
        self.add_behaviour(self.Charge())

        if hasattr(self, "viz_server"):
            self.add_behaviour(VisualizationBehaviour())

        print(f"{CYAN}[{self.name}] Rover initialized at {self.position}, waiting for path.{RESET}")
        await self.viz_send_message(f"Rover initialized at {self.position}")
