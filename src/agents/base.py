import asyncio
import random

from collections import deque, defaultdict
from math import sqrt
from typing import Tuple, List, Dict, Optional

import spade
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour
from spade.message import Message
from spade.template import Template

from agents.visualizator import VisualizationBehaviour, VisualizationMixin

from settings import *

class Base(VisualizationMixin, Agent):
    def __init__(
        self,
        jid: str,
        password: str,
        position: Tuple[float, float] = [0, 0],
        rover_jids: List[str] = [],
        drone_jids: List[str] = [],
        radius: int = 5,
        viz_server = None
    ) -> None:
        super().__init__(jid, password)
        self.position = tuple(position)
        self.radius = radius

        # This list is from rovers and drones that are currently on the base.
        # When the agent levaes the base, we lose information ab out it and remove it from the list

        self.rovers = rover_jids   # List of rover JIDs that are on the base in this moment
        self.drones = drone_jids

        self.resources = defaultdict(lambda: { "count": 0, "positions": [] }) # Dict of detected resources
        self.pending_missions = [] # Queue of locations to explore
        self.proposals = {}

        self.viz_server = viz_server
        if self.viz_server:
            self.setup_visualization(
                self.viz_server,
                agent_type="base",
                agent_jid=jid,
                position=position,
                battery=100.0,
                color="#ff00ff",
                radius=radius
            )

    # -------------------------------------------------------------------------
    # BEHAVIOURS
    # -------------------------------------------------------------------------
    class RequestRoverForBid(OneShotBehaviour):
        """
        Implements the Initiator role in the FIPA Contract Net Protocol
        """
        def __init__(self, target_position: Tuple[float, float], drone: str) -> None:
            super().__init__()
            self.target_position = target_position
            self.drone = drone
            
        async def run(self):
            """
                Send CFP to all rovers
            """
            base = self.agent

            for rover_jid in base.rovers:
                msg = Message(to=rover_jid)
                msg.set_metadata("performative", "cfp")
                msg.set_metadata("type", "rover_bid_cfp")
                msg.body = str(self.target_position)
                await self.send(msg)
                print(f"{MAGENTA}[{base.name}] CFP sent to {rover_jid} for mission at {self.target_position}{RESET}")

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
            print(f"{MAGENTA}[{self.agent.name}] Rover {str(message.sender).split("@")[0]} failed during the contract net protocol.{RESET}")

        def on_not_understood(self, message: Message):
            """Called if a rover doesn't understand the CFP."""
            print(f"{MAGENTA}[{self.agent.name}] Rover {str(message.sender).split("@")[0]} did not understand the CFP.{RESET}")

        def on_refuse(self, message: Message):
            """Called when a rover refuses to bid."""
            print(f"{MAGENTA}[{self.agent.name}] Rover {str(message.sender).split("@")[0]} refused to bid for mission at {self.target_position}: reason - {eval(message.body)}{RESET}")

        async def on_propose(self, message: Message):
            """
            Called when a rover sends a proposal (a bid).
            The bid should contain the cost for the mission (Time to be ready/reach target).
            """
            try:
                base = self.agent

                # The bid should be: {"cvost": 5.5, "rover": "rover_id"}
                bid_data = eval(message.body)
                cost = float(bid_data.get("cost", float('inf'))) # Time to be ready/reach target
                rover_jid = bid_data.get("rover")
                
                print(f"{MAGENTA}[{base.name}] Received PROPOSAL from {message.sender}: Cost={cost}, Rover={rover_jid}{RESET}")
                await base.viz_send_message(f"Received proposal from {str(message.sender).split('@')[0]}: Cost={cost}")
                
                # Store the valid bid
                if rover_jid is not None:
                    # Storing bid data along with the sender JID
                    base.proposals[str(message.sender)] = {"cost": cost, "rover": rover_jid, "proposal_msg": message}
                else:
                    print(f"{MAGENTA}[{base.name}] Ignoring invalid proposal from {message.sender}: No 'rover id' specified.{RESET}")
            
            except (SyntaxError, TypeError, ValueError):
                print(f"{MAGENTA}[{base.name}] Invalid proposal format from {message.sender}. Body: {message.body}{RESET}")

        async def on_all_responses_received(self):
            """
            Called when all expected replies (proposes or refuses) are received,
            or the timeout has expired.
            """
            base = self.agent
            print(f"{MAGENTA}[{base.name}] All responses received for mission at {self.target_position}.{RESET}")

            if not base.proposals:
                print(f"{MAGENTA}[{base.name}] No proposals received for mission at {self.target_position}{RESET}")
                await base.viz_send_message(f"No proposals received for mission at {self.target_position}")
                return

            """
            Finds the best available rover (ON the base)
            and estimates the minimum mission time (charge + travel).
            """

            best_sender, best_data = min(base.proposals.items(), key=lambda x: x[1]["cost"])
            best_bid = best_data
            
            # Send the winner bid to the drone and wait for further communication
            accept_msg = Message(to=self.drone)
            accept_msg.set_metadata("performative", "propose")
            accept_msg.set_metadata("type", "rover_bid_cfp")
            accept_msg.body = str({"target": self.target_position, "base": str(base.jid), "rover": str(best_sender), "cost": best_bid['cost']})
            print(f"{MAGENTA}[{base.name}] Sending winner bid to drone 'target': {self.target_position}, 'base': {base.jid}, 'rover': {best_sender}, 'cost': {best_bid['cost']}{RESET}")
            await base.viz_send_message(f"Selected {str(best_sender).split('@')[0]} for mission at {self.target_position} (cost: {best_bid['cost']:.1f})")
            await self.send(accept_msg)

            # Reject all other proposals
            for sender, data in base.proposals.items():
                if sender != best_sender:
                    reject_msg = Message(to=sender)
                    reject_msg.set_metadata("performative", "reject_proposal")
                    reject_msg.set_metadata("type", "rover_bid_cfp")
                    reject_msg.body = str({"target": self.target_position})
                    await self.send(reject_msg)
            base.proposals = {}

        async def on_inform(self, message: Message):
            print(f"{MAGENTA}[{self.agent.name}] Received INFORM from {message.sender} about mission completion.{RESET}")

    class ReceiveMessages(CyclicBehaviour):
        async def run(self):
            base = self.agent
            msg = await self.receive(timeout=5)

            if msg:
                sender = str(msg.sender).split("@")[0]
                msg_type = msg.metadata.get("type")
                performative = msg.metadata.get("performative")
                print(f"{MAGENTA}[{base.name}] Message received from {sender} (type: {msg_type}, performative: {performative}){RESET}")

                # --- MISSION REQUEST FROM DRONE ---
                if performative == "cfp" and msg_type == "rover_mission_cfp":
                    if not base.rovers:
                        drone_msg = Message(to=msg.sender)
                        drone_msg.set_metadata("performative", "refuse")
                        drone_msg.set_metadata("type", "drone_bid_cfp")
                        drone_msg.body = str({"reason": "no_rovers_available"})
                        print(f"{MAGENTA}[{base.name}] Sending reject bid to drone, no rovers available{RESET}")
                        await base.viz_send_message(f"Rejected mission request from {sender}: No rovers available")
                        await self.send(drone_msg)

                    else:
                        target_pos = eval(msg.body)
                        print(f"{MAGENTA}[{base.name}] Received mission CFP from {sender} for target {target_pos}{RESET}")
                        await base.viz_send_message(f"Received mission request from {sender} for target {target_pos}")
                        base.add_behaviour(base.RequestRoverForBid(target_pos, msg.sender))

                # --- BID ACCEPTED FROM DRONE ---
                if performative == "accept_proposal" and msg_type == "rover_bid_accepted":
                    target_data = eval(msg.body)
                    target_pos = target_data.get("target")
                    winning_rover = target_data.get("rover")

                    print(f"{MAGENTA}[{base.name}] Bid accepted from {sender} for target {target_pos}{RESET}")
                    await base.viz_send_message(f"Mission confirmed: Sending {str(winning_rover).split('@')[0]} to {target_pos}")
                    # Send accept to rover
                    accept_msg = Message(to=winning_rover)
                    accept_msg.set_metadata("performative", "accept_proposal")
                    accept_msg.set_metadata("type", "rover_bid_cfp")
                    accept_msg.body = str({"target": target_pos})
                    await self.send(accept_msg)
                
                # --- BID REJECTED FROM DRONE ---
                if performative == "reject_proposal" and msg_type == "rover_bid_rejected":
                    target_data = eval(msg.body)
                    target_pos = target_data.get("target")
                    rejected_rover = target_data.get("rover")
                    print(f"{MAGENTA}[{base.name}] Bid rejected CFP from {sender} for target {target_pos}{RESET}")

                    reject_msg = Message(to=rejected_rover)
                    reject_msg.set_metadata("performative", "reject_proposal")
                    reject_msg.set_metadata("type", "rover_bid_cfp")
                    await self.send(reject_msg)

                if performative == "inform" and msg_type == "rover_leaving_base":
                    rover = msg.sender
                    print(f"{MAGENTA}[{base.name}] Rover {str(rover).split("@")[0]} leaving base{RESET}")
                    await base.viz_send_message(f"Rover {str(rover).split('@')[0]} departing from base")
                    base.rovers.remove(rover)
                    
                if performative == "inform" and msg_type == "mission_complete":
                    rover = msg.sender
                    target_data = eval(msg.body)
                    position = target_data.get("position")
                    print(f"{MAGENTA}[{base.name}] Rover {str(rover).split("@")[0]} arrived at goal: current position {position}{RESET}")
                    await base.viz_send_message(f"Rover {str(rover).split('@')[0]} reached target at {position}")
                    await base.viz_mark_explored(position[0], position[1])

                if performative == "inform" and msg_type == "resources_found":
                    rover = msg.sender
                    target_data = eval(msg.body)
                    position = target_data.get("position")
                    resources = target_data.get("resources")
                    print(f"{MAGENTA}[{base.name}] Rover {str(rover).split("@")[0]} found resources at goal: current position {position}, resources: {resources}{RESET}")
                    await base.viz_send_message(f"Rover {str(rover).split('@')[0]} discovered {len(resources)} resources at {position}")

                    for resource in resources:
                        base.resources[resource]["count"] += 1
                        base.resources[resource]["positions"].append(position)
                        await base.viz_report_resource(resource, position[0], position[1])

                if performative == "inform" and msg_type == "rover_returned_to_base":
                    rover = msg.sender
                    print(f"{MAGENTA}[{base.name}] Rover {str(rover).split("@")[0]} returned to base{RESET}")
                    await base.viz_send_message(f"Rover {str(rover).split('@')[0]} returned to base")
                    base.rovers.append(rover)

                    for drone in base.drones:
                        has_rovers_msg = Message(to=drone)
                        has_rovers_msg.set_metadata("performative", "inform")
                        has_rovers_msg.set_metadata("type", "drone_bid_cfp")
                        has_rovers_msg.body = str({"inform": "has_rovers_available"})
                        print(f"{MAGENTA}[{base.name}] Sending inform bid to {drone}, rovers available{RESET}")
                        await self.send(has_rovers_msg)

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
        print(f"{MAGENTA}[{self.name}] Base operational at position {self.position}{RESET}")
        await self.viz_send_message(f"Base operational at position {self.position}")
        await self.viz_update_status("running")
        self.add_behaviour(self.ReceiveMessages())

        if hasattr(self, "viz_server"):
            self.add_behaviour(VisualizationBehaviour())

    async def stop(self):
        """Called when agent is being stopped"""
        print(f"{MAGENTA}[{self.name}] Base shutting down...{RESET}")
        print(f"{MAGENTA}Collected...{RESET}")
        for resource, value in self.resources.items():
            print(f"{MAGENTA}  Found {resource}:{RESET}")
            print(f"{MAGENTA}    count = {value["count"]}{RESET}")
            print(f"{MAGENTA}    positions = {value["positions"]}{RESET}")
                
        # Call parent's stop
        await super().stop()
