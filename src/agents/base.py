import asyncio
import random

from collections import deque
from math import sqrt
from typing import Tuple, List, Dict, Optional

import spade
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour
from spade.message import Message
from spade.template import Template
from visualization_mixin import VisualizationMixin, VisualizationBehaviour

from settings import *

class Base(VisualizationMixin, Agent):
    def __init__(
        self,
        jid: str,
        password: str,
        position: Tuple[float, float] = [0, 0],
        viz_server=None
    ) -> None:
        super().__init__(jid, password)
        self.position = tuple(position)
        if viz_server:
            self.setup_visualization(
                viz_server=viz_server,
                agent_type='base',
                color='#3b82f6'
            )
        # This list is from rovers and drones that are currently on the base.
        # When the agent levaes the base, we lose information ab out it and remove it from the list
        self.rovers = ["rover1@planet.local", "rover2@planet.local"]  # List of rover JIDs that are on the base in this moment
        self.drones = ["drone1@planet.local", "drone2@planet.local"]  # List of drone JIDs that are on the base in this moment
        self.resources = []                 # List of detected resources
        self.pending_missions = []          # Queue of locations to explore

    # -------------------------------------------------------------------------
    # UTILITIES
    # -------------------------------------------------------------------------

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
    # BEHAVIOURS
    # -------------------------------------------------------------------------
    class RequestRoverForBid(OneShotBehaviour):
        """
        Implements the Initiator role in the FIPA Contract Net Protocol
        """
        def __init__(self, target_position: Tuple[float, float], rover_jids: List[str]):
            super().__init__(self.agent.bases) # Targets all rovers in self.agent.rovers
            self.target_position = target_position
            self.rover_jids = rover_jids
            self.proposals: Dict[str, Dict] = {}
            
        async def run(self, message: Message):
            """
                Send CFP to all rovers
            """
            for rover_jid in self.rover_jids:
                msg = Message(to=rover_jid)
                msg.set_metadata("performative", "cfp")
                msg.set_metadata("ontology", "rover_bid_cfp")
                msg.body = str(self.target_position)
                await self.send(msg)
                print(f"[{self.agent.name}] CFP sent to {rover_jid} for mission at {self.target_position}")

            timeout = 5  # seconds to wait for bids

            start_time = asyncio.get_event_loop().time()

            while asyncio.get_event_loop().time() - start_time < timeout:
                msg = await self.receive(timeout=1)
                if msg:
                    perf = msg.metadata.get("performative")
                    if perf == "propose":
                        await self.on_propose(msg)
                    elif perf == "refuse":
                        self.on_refuse(msg)
                    elif perf == "not-understood":
                        self.on_not_understood(msg)
                    elif perf == "failure":
                        self.on_failure(msg)
    
            await self.on_all_responses_received()

        def on_failure(self, message: Message):
            """Called if a rover fails during the negotiation."""
            print(f"[{self.agent.name}] Base {message.sender} failed during the contract net protocol.")

        def on_not_understood(self, message: Message):
            """Called if a rover doesn't understand the CFP."""
            print(f"[{self.agent.name}] Base {message.sender} did not understand the CFP.")

        async def on_propose(self, message: Message):
            """
            Called when a rover sends a proposal (a bid).
            The bid should contain the current energy of the agent.
            """
            try:
                # The bid should be: {"energy": 5.5, "rover": "rover_id"}
                bid_data = eval(message.body)
                energy = float(bid_data.get("energy", float('inf'))) # Time to be ready/reach target
                rover_jid = bid_data.get("rover")
                
                print(f"[{self.agent.name}] Received PROPOSAL from {message.sender}: Energy={energy}, Rover={rover_jid}")
                
                # Store the valid bid
                if rover_jid is not None:
                    # Storing bid data along with the sender JID
                    self.agent.proposals[str(message.sender)] = {"energy": energy, "rover": rover_jid, "proposal_msg": message}
                else:
                    print(f"[{self.agent.name}] Ignoring invalid proposal from {message.sender}: No 'rover id' specified.")
            
            except (SyntaxError, TypeError, ValueError):
                print(f"[{self.agent.name}] Invalid proposal format from {message.sender}. Body: {message.body}")


        async def on_all_responses_received(self, replies: List[Message]):
            """
            Called when all expected replies (proposes or refuses) are received,
            or the timeout has expired.
            """
            print(f"[{self.agent.name}] All responses received for mission at {self.target_position}. Total replies: {len(replies)}")

            if not self.proposals:
                print(f"[{self.agent.name}] No proposals received for mission at {self.target_position}")
                return

            """
            Finds the best available rover (ON the base)
            and estimates the minimum mission time (charge + travel).
            """

            best_sender, best_data = min(self.proposals.items(), key=lambda x: x[1]["bid"]["cost"])
            best_bid = best_data["bid"]
            print(f"[{self.agent.name}] Accepting proposal from {best_sender} with cost {best_bid['cost']}")
            
            # Accept the winner
            accept_msg = Message(to=best_sender)
            accept_msg.set_metadata("performative", "accept_proposal")
            accept_msg.set_metadata("ontology", "rover_bid_cfp")
            accept_msg.body = str({"target": self.target_position})
            await self.send(accept_msg)

            # Reject all other proposals
            for sender, data in self.proposals.items():
                if sender != best_sender:
                    reject_msg = Message(to=sender)
                    reject_msg.set_metadata("performative", "reject_proposal")
                    reject_msg.set_metadata("ontology", "rover_bid_cfp")
                    reject_msg.body = str({"target": self.target_position})
                    await self.send(reject_msg)

        async def on_inform(self, message: Message):
            print(f"[{self.agent.name}] Received INFORM from {message.sender} about mission completion.")

    class ReceiveMessages(CyclicBehaviour):
        async def run(self):
            base = self.agent
            msg = await self.receive(timeout=5)

            if msg:
                sender = str(msg.sender).split("@")[0]
                msg_type = msg.metadata.get("type")
                print(f"[{base.name}] Message received from {sender} (type: {msg_type})")

                # --- STATUS UPDATE ---
                if msg_type == "status":
                    if "rover" in sender:
                        base.rovers.setdefault(sender, {})["status"] = "available"
                        print(f"[{base.name}] Rover {sender} marked as available.")
                    elif "drone" in sender:
                        base.drones.setdefault(sender, {})["status"] = "available"
                        print(f"[{base.name}] Drone {sender} marked as available.")

                # --- RESOURCE DISCOVERY ---
                elif msg_type == "resource":
                    resource_data = eval(msg.body)
                    base.resources.append(resource_data)
                    print(f"[{base.name}] Resource logged: {resource_data}")

                    await base.send_message(
                        "satellite@planet.local", "resource_found", str(resource_data)
                    )

                # --- POSITION UPDATE ---
                elif msg_type == "position_update":
                    position_data = eval(msg.body)
                    if "rover" in sender:
                        base.rovers.setdefault(sender, {}).update({
                            "position": position_data["position"],
                            "energy": position_data["energy"]
                        })
                    elif "drone" in sender:
                        base.drones.setdefault(sender, {}).update({
                            "position": position_data["position"],
                            "energy": position_data["energy"]
                        })

                # --- MISSION REQUEST FROM SATELLITE ---
                elif msg_type == "mission_request":
                    target_pos = eval(msg.body)
                    closest_rover = base.find_closest_rover(target_pos)

                    await base.send_message(
                        str(msg.sender),
                        "rover_assignment",
                        str({"rover": closest_rover, "target": target_pos})
                    )

                    print(f"[{base.name}] Assigned rover {closest_rover} to mission at {target_pos}")

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
                AssignMissionToRover(mission_msg)

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

    # class AssignMissionToAgent():

    # -------------------------------------------------------------------------
    # SETUP
    # -------------------------------------------------------------------------
    async def setup(self):
        print(f"[{self.name}] Base operational at position {self.position}")
        if hasattr(self, 'viz_server'):
            viz_behaviour = VisualizationBehaviour(update_interval=0.1)
            self.add_behaviour(viz_behaviour)
        self.add_behaviour(self.ReceiveMessages())
        self.add_behaviour(self.MissionResponder())
