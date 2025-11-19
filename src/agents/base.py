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
    """
    Base station agent that coordinates rovers and drones for exploration missions.
    
    Manages available rovers, receives mission requests from drones, and implements
    the FIPA Contract Net Protocol to assign missions to the best available rover.
    
    Attributes:
        position (Tuple[float, float]): The (x, y) coordinates of the base station.
        radius (int): Communication radius of the base station.
        rovers (List[str]): List of rover JIDs currently at the base.
        drones (List[str]): List of drone JIDs known to the base.
        resources (Dict): Dictionary tracking detected resources with counts and positions.
        pending_missions (List): Queue of locations awaiting exploration.
        proposals (Dict): Temporary storage for rover bids during contract negotiation.
        viz_server: Visualization server connection for displaying base status.
    """
    
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
        """
        Initialize a Base station agent.
        
        Args:
            jid (str): XMPP JID for the base agent.
            password (str): Password for XMPP authentication.
            position (Tuple[float, float]): Initial (x, y) position of the base.
            rover_jids (List[str]): List of rover JIDs initially at the base.
            drone_jids (List[str]): List of drone JIDs to communicate with.
            radius (int): Communication radius of the base station.
            viz_server: Visualization server for status updates.
        """
        super().__init__(jid, password)
        self.position = tuple(position)
        self.radius = radius

        self.rovers = rover_jids
        self.drones = drone_jids

        self.resources = defaultdict(lambda: { "count": 0, "positions": [] })
        self.pending_missions = []
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

    class RequestRoverForBid(OneShotBehaviour):
        """
        Implements the Initiator role in the FIPA Contract Net Protocol.
        
        Sends Call For Proposals (CFP) to all available rovers, collects bids,
        and selects the best rover based on mission cost.
        
        Attributes:
            target_position (Tuple[float, float]): The mission target coordinates.
            drone (str): JID of the requesting drone.
        """
        
        def __init__(self, target_position: Tuple[float, float], drone: str) -> None:
            """
            Initialize the bidding behavior for a mission.
            
            Args:
                target_position (Tuple[float, float]): Target (x, y) coordinates for the mission.
                drone (str): JID of the drone requesting the mission.
            """
            super().__init__()
            self.target_position = target_position
            self.drone = drone
            
        async def run(self):
            """
            Execute the contract net protocol by sending CFPs and collecting proposals.
            
            Sends CFP messages to all rovers, waits for proposals, and processes
            responses to select the winning bid.
            """
            base = self.agent

            for rover_jid in base.rovers:
                msg = Message(to=rover_jid)
                msg.set_metadata("performative", "cfp")
                msg.set_metadata("type", "rover_bid_cfp")
                msg.body = str(self.target_position)
                await self.send(msg)
                print(f"{MAGENTA}[{base.name}] CFP sent to {rover_jid} for mission at {self.target_position}{RESET}")

            timeout = 1

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
            """
            Handle failure messages from rovers during negotiation.
            
            Args:
                message (Message): The failure message from a rover.
            """
            print(f"{MAGENTA}[{self.agent.name}] Rover {str(message.sender).split('@')[0]} failed during the contract net protocol.{RESET}")

        def on_not_understood(self, message: Message):
            """
            Handle not-understood messages when a rover doesn't comprehend the CFP.
            
            Args:
                message (Message): The not-understood message from a rover.
            """
            print(f"{MAGENTA}[{self.agent.name}] Rover {str(message.sender).split('@')[0]} did not understand the CFP.{RESET}")

        def on_refuse(self, message: Message):
            """
            Handle refusal messages from rovers declining to bid.
            
            Args:
                message (Message): The refusal message containing the reason.
            """
            print(f"{MAGENTA}[{self.agent.name}] Rover {str(message.sender).split('@')[0]} refused to bid for mission at {self.target_position}: reason - {eval(message.body)}{RESET}")

        async def on_propose(self, message: Message):
            """
            Process proposal messages containing rover bids.
            
            Validates and stores bid data including cost and rover identification
            for later evaluation.
            
            Args:
                message (Message): The proposal message containing bid details.
            """
            try:
                base = self.agent

                bid_data = eval(message.body)
                cost = float(bid_data.get("cost", float('inf')))
                rover_jid = bid_data.get("rover")
                
                print(f"{MAGENTA}[{base.name}] Received PROPOSAL from {message.sender}: Cost={cost}, Rover={rover_jid}{RESET}")
                await base.viz_send_message(f"Received proposal from {str(message.sender).split('@')[0]}: Cost={cost}")
                
                if rover_jid is not None:
                    base.proposals[str(message.sender)] = {"cost": cost, "rover": rover_jid, "proposal_msg": message}
                else:
                    print(f"{MAGENTA}[{base.name}] Ignoring invalid proposal from {message.sender}: No 'rover id' specified.{RESET}")
            
            except (SyntaxError, TypeError, ValueError):
                print(f"{MAGENTA}[{base.name}] Invalid proposal format from {message.sender}. Body: {message.body}{RESET}")

        async def on_all_responses_received(self):
            """
            Process all received proposals and select the winning bid.
            
            Identifies the rover with the lowest mission cost, sends acceptance
            to the drone, notifies the winning rover, and rejects other proposals.
            """
            base = self.agent
            print(f"{MAGENTA}[{base.name}] All responses received for mission at {self.target_position}.{RESET}")

            if not base.proposals:
                print(f"{MAGENTA}[{base.name}] No proposals received for mission at {self.target_position}{RESET}")
                await base.viz_send_message(f"No proposals received for mission at {self.target_position}")
                return

            best_sender, best_data = min(base.proposals.items(), key=lambda x: x[1]["cost"])
            best_bid = best_data
            
            accept_msg = Message(to=self.drone)
            accept_msg.set_metadata("performative", "propose")
            accept_msg.set_metadata("type", "rover_bid_cfp")
            accept_msg.body = str({"target": self.target_position, "base": str(base.jid), "rover": str(best_sender), "cost": best_bid['cost']})
            print(f"{MAGENTA}[{base.name}] Sending winner bid to drone 'target': {self.target_position}, 'base': {base.jid}, 'rover': {best_sender}, 'cost': {best_bid['cost']}{RESET}")
            await base.viz_send_message(f"Selected {str(best_sender).split('@')[0]} for mission at {self.target_position} (cost: {best_bid['cost']:.1f})")
            await self.send(accept_msg)

            for sender, data in base.proposals.items():
                if sender != best_sender:
                    reject_msg = Message(to=sender)
                    reject_msg.set_metadata("performative", "reject_proposal")
                    reject_msg.set_metadata("type", "rover_bid_cfp")
                    reject_msg.body = str({"target": self.target_position})
                    await self.send(reject_msg)
            base.proposals = {}

        async def on_inform(self, message: Message):
            """
            Handle inform messages about mission completion.
            
            Args:
                message (Message): The inform message from a rover.
            """
            print(f"{MAGENTA}[{self.agent.name}] Received INFORM from {message.sender} about mission completion.{RESET}")

    class ReceiveMessages(CyclicBehaviour):
        """
        Continuously receive and process incoming messages from rovers and drones.
        
        Handles various message types including mission requests, bid acceptances,
        rover status updates, and resource discoveries.
        """
        
        async def run(self):
            """
            Process incoming messages and dispatch them to appropriate handlers.
            
            Monitors for mission CFPs, bid results, rover departures/returns,
            and resource discovery notifications.
            """
            base = self.agent
            msg = await self.receive(timeout=3)

            if msg:
                sender = str(msg.sender).split("@")[0]
                msg_type = msg.metadata.get("type")
                performative = msg.metadata.get("performative")
                print(f"{MAGENTA}[{base.name}] Message received from {sender} (type: {msg_type}, performative: {performative}){RESET}")

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

                if performative == "accept_proposal" and msg_type == "rover_bid_accepted":
                    target_data = eval(msg.body)
                    target_pos = target_data.get("target")
                    winning_rover = target_data.get("rover")

                    print(f"{MAGENTA}[{base.name}] Bid accepted from {sender} for target {target_pos}{RESET}")
                    await base.viz_send_message(f"Mission confirmed: Sending {str(winning_rover).split('@')[0]} to {target_pos}")
                    
                    accept_msg = Message(to=winning_rover)
                    accept_msg.set_metadata("performative", "accept_proposal")
                    accept_msg.set_metadata("type", "rover_bid_cfp")
                    accept_msg.body = str({"target": target_pos})
                    await self.send(accept_msg)
                
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
                    print(f"{MAGENTA}[{base.name}] Rover {str(rover).split('@')[0]} leaving base{RESET}")
                    await base.viz_send_message(f"Rover {str(rover).split('@')[0]} departing from base")
                    base.rovers.remove(rover)
                    
                if performative == "inform" and msg_type == "mission_complete":
                    rover = msg.sender
                    target_data = eval(msg.body)
                    position = target_data.get("position")
                    print(f"{MAGENTA}[{base.name}] Rover {str(rover).split('@')[0]} arrived at goal: current position {position}{RESET}")
                    await base.viz_send_message(f"Rover {str(rover).split('@')[0]} reached target at {position}")
                    await base.viz_mark_explored(position[0], position[1])

                if performative == "inform" and msg_type == "resources_found":
                    rover = msg.sender
                    target_data = eval(msg.body)
                    position = target_data.get("position")
                    resources = target_data.get("resources")
                    print(f"{MAGENTA}[{base.name}] Rover {str(rover).split('@')[0]} found resources at goal: current position {position}, resources: {resources}{RESET}")
                    await base.viz_send_message(f"Rover {str(rover).split('@')[0]} discovered {len(resources)} resources at {position}")

                    for resource in resources:
                        base.resources[resource]["count"] += 1
                        base.resources[resource]["positions"].append(position)
                        await base.viz_report_resource(resource, position[0], position[1])

                if performative == "inform" and msg_type == "rover_returned_to_base":
                    rover = msg.sender
                    print(f"{MAGENTA}[{base.name}] Rover {str(rover).split('@')[0]} returned to base{RESET}")
                    await base.viz_send_message(f"Rover {str(rover).split('@')[0]} returned to base")
                    base.rovers.append(rover)

                    for drone in base.drones:
                        has_rovers_msg = Message(to=drone)
                        has_rovers_msg.set_metadata("performative", "inform")
                        has_rovers_msg.set_metadata("type", "drone_bid_cfp")
                        has_rovers_msg.body = str({"inform": "has_rovers_available"})
                        print(f"{MAGENTA}[{base.name}] Sending inform bid to {drone}, rovers available{RESET}")
                        await self.send(has_rovers_msg)

    async def setup(self):
        """
        Initialize the base agent and start its behaviors.
        
        Registers message receiving behavior and visualization updates.
        Announces base operational status.
        """
        print(f"{MAGENTA}[{self.name}] Base operational at position {self.position}{RESET}")
        await self.viz_send_message(f"Base operational at position {self.position}")
        await self.viz_update_status("running")
        self.add_behaviour(self.ReceiveMessages())

        if hasattr(self, "viz_server"):
            self.add_behaviour(VisualizationBehaviour())

    async def stop(self):
        """
        Shut down the base agent and report collected resources.
        
        Prints a summary of all discovered resources with their counts
        and locations before stopping the agent.
        """
        print(f"{MAGENTA}[{self.name}] Base shutting down...{RESET}")
        await self.viz_send_message(f"Base shutting down")

        print(f"{MAGENTA}Collected...{RESET}")
        for resource, value in self.resources.items():
            print(f"{MAGENTA}  Found {resource}:{RESET}")
            print(f"{MAGENTA}    count = {value['count']}{RESET}")
            print(f"{MAGENTA}    positions = {value['positions']}{RESET}")
        await self.viz_send_message(f"Collected {str(self.resources)}")
                
        await super().stop()
