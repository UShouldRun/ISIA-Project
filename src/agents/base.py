import asyncio
from collections import deque
from math import sqrt
from typing import Tuple, List, Dict, Optional

import spade
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour
from spade.message import Message

from world.world import World, WorldObject
from world.map import Map

class Base(Agent):
    def __init__(
        self,
        jid: str,
        password: str,
        position: WorldObject,
        world: World,
        known_drones: List[str],
        known_rovers: List[str],
        satellite_jid: str,
        base_radius: float = 100.0
    ) -> None:
        super().__init__(jid, password)
        self.position = tuple(position)
        # This list is from rovers and drones that are currently on the base.
        # When the agent levaes the base, we lose information ab out it and remove it from the list
        self.rovers: Dict[str, Dict] = {}   # {rover_jid: {"position": (x, y), "energy": int, "status": str}}
        self.drones: Dict[str, Dict] = {}   # {drone_jid: {"position": (x, y), "energy": int, "status": str}}
        self.resources = []                 # List of detected resources
        self.pending_missions = []          # Queue of locations to explore

    # -------------------------------------------------------------------------
    # UTILITIES
    # -------------------------------------------------------------------------
    def calculate_distance(self, pos1: Tuple[float, float], pos2: Tuple[float, float]) -> float:
        return sqrt((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2)

    def calculate_pathfinding_cost(self, start_pos: Tuple[float, float], target_pos: Tuple[float, float]) -> float:
            """
            Slightly randomized Euclidean distance.
            """
            euclidean_dist = self.calculate_distance(start_pos, target_pos)
            # Simulate complexity by making the pathfinding distance 10-30% longer than straight-line
            return euclidean_dist * random.uniform(1.1, 1.3)

    def find_available_rover(self, target_pos: Tuple[float, float]) -> Tuple[str, float, float] | None:
        """
        Finds the best available rover (ON the base)
        and estimates the minimum mission time (charge + travel).
        """

        best_rover_jid = None
        min_mission_time = float('inf')
        
        # Filter: Only rovers NOT locked to a prior bid (as they are all assumed to be at the base)
        standby_rovers = {
            jid: info for jid, info in self.rovers.items()
            if info.get("locked_mission") is None
        }

        if not standby_rovers:
            return None # No rovers on standby (at base)

        # rover_pos is now assumed to be self.position for all rovers in standby_rovers
        rover_pos = self.position 

        for jid, info in standby_rovers.items():
            current_energy = info["energy"]
            
            # 1. Calculate an approximation of the distance that the rover will have to go (2-way trip: Base -> Target -> Base)
            # We use the base position as the starting point.
            # We use eucledian distance for the approximation

            dist_to_target = self.calculate_pathfinding_cost(rover_pos, target_pos)
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
            
            if mission_time < min_mission_time:
                min_mission_time = mission_time
                best_rover_jid = jid

        if best_rover_jid:
            return best_rover_jid, min_mission_time, energy_required 
        return None

    async def send_message(self, to: str, msg_type: str, body: str):
        """Communication for all outgoing Base messages."""
        msg = Message(to=to, metadata={"type": msg_type}, body=body)
        await self.send(msg)
        print(f"[{self.name}] → Sent to {to}: ({perf}) {body}")

    def distance(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        return sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

    def select_drone(self) -> Optional[str]:
        """Pop next available drone (FIFO)."""
        if not self.drones_queue:
            return None
        return self.drones_queue.popleft()

    def select_rover(self) -> Optional[str]:
        """Pop next available rover (FIFO)."""
        if not self.rovers_queue:
            return None
        return self.rovers_queue.popleft()

    def mark_drone_available(self, jid: str):
        """Return a drone to the queue after mission completion."""
        if jid not in self.drones_queue:
            self.drones_queue.append(jid)

    def mark_rover_available(self, jid: str):
        """Return a rover to the queue after mission completion."""
        if jid not in self.rovers_queue:
            self.rovers_queue.append(jid)

    # -------------------------------------------------------------------------
    # BEHAVIOUR: Handle messages from Satellite / Drones / Rovers
    # -------------------------------------------------------------------------
    class ManageMissions(CyclicBehaviour):
        async def run(self):
            base = self.agent
            msg = await self.receive(timeout=5)
            if not msg:
                await asyncio.sleep(1)
                return

            perf = msg.metadata.get("performative", "")
            sender = str(msg.sender).split("@")[0]
            print(f"[{base.name}] Received ({perf}) from {sender}: {msg.body}")

            # Satellite requests mission allocation
            if perf == "request":
                mission_data = eval(msg.body)
                target = mission_data.get("target")
                print(f"[{base.name}] Mission request received for area {target}")

                # Assign a Drone and Rover using FIFO
                drone = base.select_drone()
                rover = base.select_rover()
                if not drone or not rover:
                    print(f"[{base.name}] No available agents for mission at {target}")
                    return

                base.active_missions[target] = {"drone": drone, "rover": rover}
                print(f"[{base.name}] Assigned Drone {drone} and Rover {rover} to {target}")

                await base.send_msg(
                    to=drone,
                    body=str({"target": target, "rover": rover}),
                    perf="inform",
                )

            # Drones inform mission completion
            elif perf == "inform_done":
                data = eval(msg.body)
                target = data.get("target")
                drone = sender
                print(f"[{base.name}] Drone {drone} completed mission at {target}")
                base.mark_drone_available(drone)

            # Rovers report mission completion
            elif perf == "inform_success":
                data = eval(msg.body)
                target = data.get("target")
                rover = sender
                print(f"[{base.name}] Rover {rover} finished mission at {target}")
                base.mark_rover_available(rover)

            # Drones or Rovers send resource discovery
            elif perf == "inform_resource":
                resource_data = eval(msg.body)
                base.resource_reports.append(resource_data)
                print(f"[{base.name}] Resource reported: {resource_data}")

            await asyncio.sleep(1)

    # For rover in standby rovers
    ## calculate necessary energy for mission
    ### Here we need to calculate an approximation of the distance between the base and the mission target
    ### Then we need to calculate how much energy will that distance take
    ## Calculate distance between rover energy and necessary energy
    ## Choose the rover that has the shortest difference (or the highest energy (to be decided))
    # Calculate the time needed to execute the mission (2 way distance)
    ## Here, if no rover has the necessary energy, append to the time the time needed to charge the rover enough
    # return to the satelite the minimum time necessary to fulfill the mission
    # also return the id of the agent that would preform the mission and put this agent on "lock"
    class MissionResponder():
        """Handles the Contract Net Protocol for incoming mission requests (CFP)."""

        def __init__(self, template):
            super().__init__(template)

        # ---------------------------------------------------------------------
        # FIPA Contract Net Steps
        # ---------------------------------------------------------------------

        async def prepare_response(self, message: Message):
            """
            Finds best rover at base, calculates cost (time), and sends PROPOSE or REFUSE.
            """
            base = self.agent
            satellite_jid = str(message.sender)
            
            try:
                target_pos = eval(message.body)
            except (SyntaxError, TypeError):
                print(f"[{base.name}] Error decoding CFP body: {message.body}")
                return await self.create_refuse(message)

            rover_info = base.find_available_rover(target_pos)

            if rover_info:
                # Rover found at base, lock it and bid
                rover_jid, mission_time, _ = rover_info
                
                base.rovers[rover_jid]["locked_mission"] = target_pos 

                bid_data = {
                    "cost": mission_time, 
                    "rover": rover_jid.split('@')[0], 
                    "target": target_pos
                }
                
                response = await self.create_propose(message)
                response.body = str(bid_data)
                response.set_metadata("type", "mission_proposal")

                print(f"[{base.name}] PROPOSING rover {rover_jid.split('@')[0]} (currently at base) with time {mission_time:.2f}s")
                return response
            else:
                # No suitable/standby rovers at the base
                print(f"[{base.name}] REFUSING: No standby rover at base for mission at {target_pos}")
                return await self.create_refuse(message)

        async def prepare_result(self, message: Message):
            """
            Implements StartMission logic.
            Called when an ACCEPT_PROPOSAL is received.
            """
            base = self.agent
            
            try:
                proposal_data = eval(message.body) 
                accepted_rover_id = proposal_data["rover"]
                accepted_target_pos = proposal_data["target"]
                accepted_rover_jid = f"{accepted_rover_id}@planet.local"
                
            except (SyntaxError, TypeError, KeyError):
                return await self.create_failure(message, body="Could not parse accepted mission details.")
            
            # 1. FINAL ASSIGNMENT & LOCK RELEASE
            if accepted_rover_jid in base.rovers and base.rovers[accepted_rover_jid]["locked_mission"] == accepted_target_pos:
                
                # Status change: Rover leaves the base
                base.rovers[accepted_rover_jid]["status"] = "busy"
                base.rovers[accepted_rover_jid]["locked_mission"] = None 

                # 2. ASSIGN MISSION TO ROVER
                mission_msg = Message(
                    to=accepted_rover_jid,
                    body=str(accepted_target_pos),
                    metadata={"type": "mission"}
                )
                await base.send(mission_msg)
                
                print(f"[{base.name}] Rover {accepted_rover_id} assigned definitive mission to {accepted_target_pos}.")

                # 3. Send INFORM (Success Confirmation) back to the Satellite
                return await self.create_inform(message, body=str({"rover": accepted_rover_id, "target": accepted_target_pos}))
            else:
                print(f"[{base.name}] FAILURE: Accepted rover {accepted_rover_id} is unavailable or was unlocked.")
                return await self.create_failure(message, body=f"Rover {accepted_rover_id} is no longer available.")


        async def on_reject(self, message: Message):
            """Called when a REJECT_PROPOSAL is received to unlock the rover."""
            try:
                proposal_data = eval(message.body)
                rejected_rover_id = proposal_data["rover"]
                rejected_rover_jid = f"{rejected_rover_id}@planet.local"
                
                if rejected_rover_jid in self.agent.rovers:
                    self.agent.rovers[rejected_rover_jid]["locked_mission"] = None
                    print(f"[{self.agent.name}] Rover {rejected_rover_id} unlocked after REJECT_PROPOSAL.")
            except:
                pass

    # -------------------------------------------------------------------------
    # SETUP
    # -------------------------------------------------------------------------
    async def setup(self):
        print(f"[{self.name}] Base online at position {self.position}")
        self.add_behaviour(self.ManageMissions())
