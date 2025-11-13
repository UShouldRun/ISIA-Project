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

from settings import *

class Base(Agent):
    def __init__(
        self,
        jid: str,
        password: str,
        position: Tuple[float, float] = [0, 0]
    ) -> None:
        super().__init__(jid, password)
        self.position = tuple(position)
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
            super().__init__(self.agent.rovers) # Targets all rovers in self.agent.rovers
            self.target_position = target_position
            self.rover_jids = rover_jids
            self.proposals: Dict[str, Dict] = {}
            
        async def run(self):
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
                cost = float(bid_data.get("cost", float('inf'))) # Time to be ready/reach target
                rover_jid = bid_data.get("rover")
                
                print(f"[{self.agent.name}] Received PROPOSAL from {message.sender}: Cost={cost}, Rover={rover_jid}")
                
                # Store the valid bid
                if rover_jid is not None:
                    # Storing bid data along with the sender JID
                    self.agent.proposals[str(message.sender)] = {"cost": cost, "rover": rover_jid, "proposal_msg": message}
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
                performative = msg.metadata.get("performative")
                print(f"[{base.name}] Message received from {sender} (type: {msg_type}, performative: {performative})")

                # --- MISSION REQUEST FROM SATELLITE ---
                if performative == "cfp" and msg_type == "rover_mission_cfp":
                    target_pos = eval(msg.body)
                    print(f"[{base.name}] Received mission CFP from {sender} for target {target_pos}")
                    
                    rover_jids = list(base.rovers)
                    behaviour = self.RequestRoverForBid(target_pos, rover_jids)
                    base.add_behaviour(behaviour)

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

    # class AssignMissionToAgent():

    # -------------------------------------------------------------------------
    # SETUP
    # -------------------------------------------------------------------------
    async def setup(self):
        print(f"[{self.name}] Base operational at position {self.position}")
        self.add_behaviour(self.ReceiveMessages())
        self.add_behaviour(self.MissionResponder())
        self.add_behaviour(self.RequestRoverForBid())
