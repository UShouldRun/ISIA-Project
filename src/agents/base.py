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
        position: Tuple[float, float] = [0, 0],
        rover_jids: List[str] = []
    ) -> None:
        super().__init__(jid, password)
        self.position = tuple(position)
        # This list is from rovers and drones that are currently on the base.
        # When the agent levaes the base, we lose information ab out it and remove it from the list
        self.rovers = rover_jids   # List of rover JIDs that are on the base in this moment
        self.resources = []        # List of detected resources
        self.pending_missions = [] # Queue of locations to explore
        self.proposals = {}

    # -------------------------------------------------------------------------
    # BEHAVIOURS
    # -------------------------------------------------------------------------
    class RequestRoverForBid(OneShotBehaviour):
        """
        Implements the Initiator role in the FIPA Contract Net Protocol
        """
        def __init__(self, target_position: Tuple[float, float]):
            super().__init__()
            self.target_position = target_position
            
        async def run(self):
            """
                Send CFP to all rovers
            """
            for rover_jid in self.agent.rovers:
                msg = Message(to=rover_jid)
                msg.set_metadata("performative", "cfp")
                msg.set_metadata("ontology", "rover_bid_cfp")
                msg.body = str(self.target_position)
                await self.send(msg)
                print(f"[{self.agent.name}] CFP sent to {rover_jid} for mission at {self.target_position}")

            timeout = 1  # seconds to wait for bids

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
            print(f"[{self.agent.name}] Rover {message.sender} failed during the contract net protocol.")

        def on_not_understood(self, message: Message):
            """Called if a rover doesn't understand the CFP."""
            print(f"[{self.agent.name}] Rover {message.sender} did not understand the CFP.")

        def on_refuse(self, message: Message):
            """Called when a rover refuses to bid."""
            print(f"[{self.agent.name}] Rover {message.sender} refused to bid for mission at {self.target_position}")

        async def on_propose(self, message: Message):
            """
            Called when a rover sends a proposal (a bid).
            The bid should contain the cost for the mission (Time to be ready/reach target).
            """
            try:
                # The bid should be: {"cvost": 5.5, "rover": "rover_id"}
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

        async def on_all_responses_received(self):
            """
            Called when all expected replies (proposes or refuses) are received,
            or the timeout has expired.
            """
            print(f"[{self.agent.name}] All responses received for mission at {self.target_position}.")

            if not self.agent.proposals:
                print(f"[{self.agent.name}] No proposals received for mission at {self.target_position}")
                return

            """
            Finds the best available rover (ON the base)
            and estimates the minimum mission time (charge + travel).
            """

            best_sender, best_data = min(self.agent.proposals.items(), key=lambda x: x[1]["cost"])
            best_bid = best_data
            
            # Send the winner bid to the drone and wait for further communication
            accept_msg = Message(to="drone@localhost")
            accept_msg.set_metadata("performative", "propose")
            accept_msg.set_metadata("ontology", "rover_bid_cfp")
            accept_msg.body = str({"target": self.target_position, "base": str(self.agent.jid), "rover": str(best_sender), "cost": best_bid['cost']})
            print(f"[{self.agent.name}] Sending winner bid to satelite 'target': {self.target_position}, 'base': {self.agent.jid}, 'rover': {best_sender}, 'cost': {best_bid['cost']}")
            await self.send(accept_msg)

            # Reject all other proposals
            for sender, data in self.agent.proposals.items():
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
                    base.add_behaviour(self.agent.RequestRoverForBid(target_pos))

                # --- BID ACCEPTED FROM SATELLITE ---
                if performative == "accept_proposal" and msg_type == "rover_bid_accepted":
                    target_data = eval(msg.body)
                    target_pos = target_data.get("target")
                    winning_rover = target_data.get("rover")

                    print(f"[{base.name}] Bid accepted from {sender} for target {target_pos}")
                    # Send accept to rover
                    accept_msg = Message(to=winning_rover)
                    accept_msg.set_metadata("performative", "accept_proposal")
                    accept_msg.set_metadata("ontology", "rover_bid_cfp")
                    accept_msg.body = str({"target": target_pos})
                    await self.send(accept_msg)
                
                # --- BID REJECTED FROM SATELLITE ---
                if performative == "reject_proposal" and msg_type == "rover_bid_rejected":
                    target_data = eval(msg.body)
                    target_pos = target_data.get("target")
                    rejected_rover = target_data.get("rover")
                    print(f"[{base.name}] Bid rejected CFP from {sender} for target {target_pos}")

                    # Send reject to rover
                    reject_msg = Message(to="best_sender")
                    reject_msg.set_metadata("performative", "reject_proposal")
                    reject_msg.set_metadata("ontology", "rover_bid_cfp")
                    await self.send(reject_msg)


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
