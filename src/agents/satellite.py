import spade
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour
from spade.message import Message
from spade.template import Template
import asyncio
from typing import Tuple, List, Dict
from math import sqrt

from spade.behaviour import FIPANetInitiator, State
from spade.protocol import FIPA_CONTRACT_NET_PROTOCOL
from aioxmpp.xso.types import InvalidValue

class Satellite(Agent):
    def __init__(
        self, jid: str, password: str,
        orbit_height: float = 1000.0,
        scan_radius: float = 500.0
    ) -> None:
        super().__init__(jid, password)
        self.orbit_height = orbit_height
        self.scan_radius = scan_radius
        self.bases = ["base@planet.local"]  # List of base JIDs
        self.scanned_areas = []  # Areas already scanned
        self.areas_of_interest = []  # Detected areas that need exploration
        self.current_scan_position = [0, 0]

    class ScanTerrain(CyclicBehaviour):
        async def on_start(self):
            print(f"[{self.agent.name}] Starting terrain scanning...")

        async def run(self):
            satellite = self.agent
            
            # Simulate scanning by moving scan position
            satellite.current_scan_position[0] += 100
            if satellite.current_scan_position[0] > 1000:
                satellite.current_scan_position[0] = 0
                satellite.current_scan_position[1] += 100
            
            if satellite.current_scan_position[1] > 1000:
                satellite.current_scan_position[1] = 0
            
            scan_pos = tuple(satellite.current_scan_position)
            
            # Check if already scanned
            if scan_pos not in satellite.scanned_areas:
                satellite.scanned_areas.append(scan_pos)
                print(f"[{satellite.name}] Scanning area: {scan_pos}")
                
                # Simulate detection of area of interest (30% chance)
                import random
                if random.random() < 0.3:
                    satellite.areas_of_interest.append(scan_pos)
                    print(f"[{satellite.name}] Area of interest detected at {scan_pos}")
                    
                    # Request mission assignment
                    satellite.add_behaviour(satellite.RequestMission(scan_pos))
            
            await asyncio.sleep(3)

    class RequestMission(OneShotBehaviour):
        def __init__(self, target_position: Tuple[float, float]):
            super().__init__()
            self.target_position = target_position

        async def run(self):
            satellite = self.agent
            
            # Ask base for closest rover
            for base_jid in satellite.bases:
                msg = Message(
                    to=base_jid,
                    body=str(self.target_position),
                    metadata={"type": "mission_request"}
                )
                await self.send(msg)
                print(f"[{satellite.name}] Requesting rover for mission at {self.target_position}")

    class ReceiveMessages(CyclicBehaviour):
        async def run(self):
            satellite = self.agent
            msg = await self.receive(timeout=5)
            
            if msg:
                msg_type = msg.metadata.get("type")
                sender = str(msg.sender).split("@")[0]
                
                print(f"[{satellite.name}] Message received from {sender} (type: {msg_type})")
                
                if msg_type == "rover_assignment":
                    # Base has assigned a rover to the mission
                    assignment_data = eval(msg.body)
                    rover_jid = assignment_data["rover"]
                    target_pos = assignment_data["target"]
                    
                    if rover_jid:
                        # Send mission directly to rover
                        mission_msg = Message(
                            to=f"{rover_jid}@planet.local",
                            body=str(target_pos),
                            metadata={"type": "mission"}
                        )
                        await self.send(mission_msg)
                        print(f"[{satellite.name}] Mission sent to {rover_jid}: explore {target_pos}")
                    else:
                        print(f"[{satellite.name}] No available rover for mission at {target_pos}")
                
                elif msg_type == "resource_found":
                    # Resource report from base
                    resource_data = eval(msg.body)
                    print(f"[{satellite.name}] Resource confirmed: {resource_data}")
            
            await asyncio.sleep(1)

    class MonitorMissions(CyclicBehaviour):
        async def run(self):
            satellite = self.agent
            
            # Periodic status report
            print(f"[{satellite.name}] Status: {len(satellite.scanned_areas)} areas scanned, "
                  f"{len(satellite.areas_of_interest)} areas of interest")
            
            await asyncio.sleep(30)

    # Start a FIPA contract-net protocol with all the bases 
    # Get the bids from the bases
    # Choose the bid that has the lowest time from the base to the objective
    ## This time can be the time to let a rover charge to be fully ready for the mission
    # Assign mission to base (pass it the mission along with the agent id in the bid)
    class RequestAgentForMission(FIPANetInitiator):
            """
            Implements the Initiator role in the FIPA Contract Net Protocol
            """
            def __init__(self, target_position: Tuple[float, float]):
                super().__init__(self.agent.bases) # Targets all agents in self.agent.bases
                self.target_position = target_position
                
            async def execute(self, message: Message):
                """
                Construct the initial Call For Proposal (CFP) message.
                """
                self.message = message
                self.message.set_metadata("protocol", FIPA_CONTRACT_NET_PROTOCOL)
                self.message.set_metadata("performative", "cfp")
                self.message.set_metadata("type", "rover_mission_cfp")
                self.message.body = str(self.target_position)
                print(f"[{self.agent.name}] Sending CFP for mission at {self.target_position} to {self.agent.bases}")
                
            def on_refuse(self, message: Message):
                """Called when a base refuses to bid."""
                print(f"[{self.agent.name}] Base {message.sender} refused to bid for mission at {self.target_position}")

            def on_failure(self, message: Message):
                """Called if a base fails during the negotiation."""
                print(f"[{self.agent.name}] Base {message.sender} failed during the contract net protocol.")

            def on_not_understood(self, message: Message):
                """Called if a base doesn't understand the CFP."""
                print(f"[{self.agent.name}] Base {message.sender} did not understand the CFP.")

            async def on_propose(self, message: Message):
                """
                Called when a base sends a proposal (a bid).
                The bid should contain the estimated time (cost) for the mission.
                """
                try:
                    # The bid should be: {"cost": 5.5, "rover": "rover_id"}
                    bid_data = eval(message.body)
                    cost = float(bid_data.get("cost", float('inf'))) # Time to be ready/reach target
                    rover_jid = bid_data.get("rover")
                    
                    print(f"[{self.agent.name}] Received PROPOSAL from {message.sender}: Cost={cost}, Rover={rover_jid}")
                    
                    # Store the valid bid
                    if rover_jid is not None:
                        # Storing bid data along with the sender JID
                        self.agent.proposals[str(message.sender)] = {"cost": cost, "rover": rover_jid, "proposal_msg": message}
                    else:
                        print(f"[{self.agent.name}] Ignoring invalid proposal from {message.sender}: No 'rover' specified.")
                
                except (SyntaxError, TypeError, ValueError):
                    print(f"[{self.agent.name}] Invalid proposal format from {message.sender}. Body: {message.body}")


            async def on_all_responses_received(self, replies: List[Message]):
                """
                Called when all expected replies (proposes or refuses) are received,
                or the timeout has expired.
                """
                print(f"[{self.agent.name}] All responses received for mission at {self.target_position}. Total replies: {len(replies)}")
                
                best_base = None
                min_cost = float('inf')
                
                # Find the best proposal (lowest cost/time)
                for base_jid, data in self.agent.proposals.items():
                    if data["cost"] < min_cost:
                        min_cost = data["cost"]
                        best_base = base_jid

                if best_base:
                    # 1. ACCEPT the best proposal
                    print(f"[{self.agent.name}] Accepting proposal from {best_base} with cost {min_cost}")
                    accept_msg = self.agent.proposals[best_base]["proposal_msg"]
                    
                    # The FIPANetInitiator will handle creating the ACCEPT_PROPOSAL message 
                    # based on the original proposal message.
                    await self.send_accept_proposal(accept_msg)

                    # 2. REJECT all other proposals
                    for base_jid, data in self.agent.proposals.items():
                        if base_jid != best_base:
                            print(f"[{self.agent.name}] Rejecting proposal from {base_jid}")
                            reject_msg = data["proposal_msg"]
                            # The FIPANetInitiator will handle creating the REJECT_PROPOSAL message
                            await self.send_reject_proposal(reject_msg)
                else:
                    print(f"[{self.agent.name}] No suitable proposals received for mission at {self.target_position}. Retrying later.")

                # Clear proposals for the next negotiation
                self.agent.proposals = {}


            async def on_inform(self, message: Message):
                """
                Called when the winning base sends an INFORM,
                to confirm the mission has been successfully taken on 
                or completed (depending on protocol stage).
                For this setup, it's used to confirm the rover assignment.
                """
                sender = str(message.sender)
                print(f"[{self.agent.name}] Received INFORM from winning base {sender}.")

                # The base is expected to send an INFORM back to the satellite
                # with the final rover assignment details.
                pass

    async def setup(self):
        print(f"[{self.name}] Satellite online at orbit height {self.orbit_height}km")
        self.add_behaviour(self.ScanTerrain())
        self.add_behaviour(self.ReceiveMessages())
        self.add_behaviour(self.MonitorMissions())
