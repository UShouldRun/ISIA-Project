import asyncio
import random

from typing import Dict, Tuple, List

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour, State
from spade.message import Message

from world.world import World, WorldObject
from world.map import Map

from settings import *

class Drone(Agent):
    def __init__(
        self,
        jid: str,
        password: str,
        world: World,
        map_: Map,
        position: Tuple[float, float],
        known_bases: List[str],
        orbit_height: float = 1000.0,
        scan_radius: float = 500.0
    ) -> None:
        super().__init__(jid, password)
        self.world = world
        self.map = map_
        self.position = position

        self.orbit_height = orbit_height
        self.scan_radius = scan_radius
        self.bases = known_bases
        self.scanned_areas = []  # Areas already scanned
        self.areas_of_interest = []  # Detected areas that need exploration
        self.current_scan_position = [0, 0]
        # Dictionary to hold proposals during Contract Net negotiation
        self.proposals: Dict[str, Dict] = {}

        self.scanned_areas: List[Tuple[float, float]] = []
        self.areas_of_interest: List[Tuple[float, float]] = []
        self.current_scan_position = list(self.position)

    # -------------------------------------------------------------------------
    # BEHAVIOURS
    # -------------------------------------------------------------------------
    class ScanTerrain(CyclicBehaviour):
        async def on_start(self):
            print(f"{GREEN}[{self.agent.name}] Starting terrain scanning...{RESET}")

        # Simulate detection of area of interest (5% chance)
        def is_area_of_interest(self) -> bool:
            return random.random() < 0.25

        async def run(self):
            drone = self.agent

            # Move scanning window
            rate = drone.map.length // SCAN_MAP_SIZE
            drone.current_scan_position[0] += rate
            if drone.current_scan_position[0] > drone.map.length:
                drone.current_scan_position[0] = 0
                drone.current_scan_position[1] += rate

            if drone.current_scan_position[1] > drone.map.height:
                drone.current_scan_position[1] = 0

            scan_pos = tuple(drone.current_scan_position)

            if scan_pos not in drone.scanned_areas:
                drone.scanned_areas.append(scan_pos)
                print(f"{GREEN}[{drone.name}] Scanning area: {scan_pos}{RESET}")
                
                if self.is_area_of_interest():
                    drone.areas_of_interest.append(scan_pos)
                    print(f"{GREEN}[{drone.name}] Area of interest detected at {scan_pos}{RESET}")
                    
                    # Request mission x
                    drone.add_behaviour(drone.RequestAgentForMission(scan_pos))

                    await asyncio.sleep(10)

    # Start a FIPA contract-net protocol with all the bases 
    # Get the bids from the bases
    # Choose the bid that has the lowest time from the base to the objective
    ## This time can be the time to let a rover charge to be fully ready for the mission
    # Assign mission to base (pass it the mission along with the agent id in the bid)
    class RequestAgentForMission(OneShotBehaviour):
        """
        Implements the Initiator role in the FIPA Contract Net Protocol
        """
        def __init__(self, target_position: Tuple[float, float]):
            super().__init__() # Targets all agents in self.agent.bases
            self.target_position = target_position

        async def run(self):
            """
                Send CFP to all bases
            """
            for base_jid in self.agent.bases:
                msg = Message(to=base_jid)
                msg.set_metadata("performative", "cfp")
                msg.set_metadata("type", "rover_mission_cfp")
                msg.body = str(self.target_position)
                await self.send(msg)
                print(f"{GREEN}[{self.agent.name}] CFP sent to {base_jid} for mission at {self.target_position}{RESET}")

            timeout = 4  # seconds to wait for bids

            start_time = asyncio.get_event_loop().time()
            replies = []

            while asyncio.get_event_loop().time() - start_time < timeout:
                msg = await self.receive(timeout=1)
                replies.append(msg)
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

            await self.on_all_responses_received(replies)
            
        def on_refuse(self, message: Message):
            """Called when a base refuses to bid."""
            print(f"{GREEN}[{self.agent.name}] Base {message.sender} refused to bid for mission at {self.target_position}{RESET}")

        def on_failure(self, message: Message):
            """Called if a base fails during the negotiation."""
            print(f"{GREEN}[{self.agent.name}] Base {message.sender} failed during the contract net protocol.{RESET}")

        def on_not_understood(self, message: Message):
            """Called if a base doesn't understand the CFP."""
            print(f"{GREEN}[{self.agent.name}] Base {message.sender} did not understand the CFP.{RESET}")

        async def on_propose(self, message: Message):
            """
            Called when a base sends a proposal (a bid).
            The bid should contain the cost for the mission (Time to be ready/reach target).
            """
            try:
                # The bid should be: {"cost": 5.5, "base": "base_id", "rover": "rover_id"}
                bid_data = eval(message.body)
                cost = float(bid_data.get("cost", float('inf'))) # Time to be ready/reach target
                base_jid = bid_data.get("base")
                rover_jid = bid_data.get("rover")
                
                print(f"{GREEN}[{self.agent.name}] Received PROPOSAL from base: {base_jid}: Cost={cost}, Rover={rover_jid}{RESET}")
                                
                # Store the valid bid
                if base_jid is not None and rover_jid is not None:
                    # Storing bid data along with the sender JID
                    self.agent.proposals[base_jid] = {"cost": cost, "base": base_jid, "rover": rover_jid, "proposal_msg": message}
                else:
                    print(f"{GREEN}[{self.agent.name}] Ignoring invalid proposal from {message.sender}: No 'rover' specified.{RESET}")
            
            except (SyntaxError, TypeError, ValueError):
                print(f"{GREEN}[{self.agent.name}] Invalid proposal format from {message.sender}. Body: {message.body}{RESET}")


        async def on_all_responses_received(self, replies: List[Message]):
            """
            Called when all expected replies (proposes or refuses) are received,
            or the timeout has expired.
            """
            print(f"{GREEN}[{self.agent.name}] All responses received for mission at {self.target_position}. Total replies: {len(replies)}{RESET}")

            if not self.agent.proposals:
                print(f"{GREEN}[{self.agent.name}] No proposals received for mission at {self.target_position}. Retrying later.{RESET}")
                # Clear proposals for the next negotiation
                self.agent.proposals = {} 
                return

            best_base, best_data = min(self.agent.proposals.items(), key=lambda x: x[1]["cost"])           
            min_cost = best_data['cost']

            if best_base:
                # ACCEPT the best proposal
                print(f"{GREEN}[{self.agent.name}] Accepting proposal from {best_base} with cost {min_cost}{RESET}")

                # Send the winner bid to the satelite and wait for further communication
                accept_msg = Message(to=best_base)
                accept_msg.set_metadata("performative", "accept_proposal")
                accept_msg.set_metadata("type", "rover_bid_accepted")
                accept_msg.body = str({"target": self.target_position, "rover": best_data["rover"]})

                await self.send(accept_msg)

                # REJECT all other proposals
                for base_jid, data in self.agent.proposals.items():
                    if base_jid != best_base:
                        print(f"{GREEN}[{self.agent.name}] Rejecting proposal from {base_jid}{RESET}")
                        reject_msg = Message(to=base_jid)
                        reject_msg.set_metadata("performative", "reject_proposal")
                        reject_msg.set_metadata("type", "rover_bid_rejected")
                        reject_msg.body = str({"target": self.target_position, "rover": data["rover"]})

                        await self.send(reject_msg)
            else:
                print(f"{GREEN}[{self.agent.name}] No suitable proposals received for mission at {self.target_position}. Retrying later.{RESET}")

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
            print(f"{GREEN}[{self.agent.name}] Received INFORM from winning base {sender}.{RESET}")

            # The base is expected to send an INFORM back to the drone
            # with the final rover assignment details.
            pass

    # class ReceiveMessages(CyclicBehaviour):
        # async def run(self):
            # drone = self.agent
            # msg = await self.receive(timeout=5)

            #if msg:
                # performative = msg.metadata.get("performative")
                # ontology = msg.metadata.get("ontology")
                # sender = str(msg.sender).split("@")[0]
                
                # print(f"{GREEN}[{drone.name}] Message received from {sender} (type: ){RESET}")

            # await asyncio.sleep(1)

    async def setup(self):
        print(f"{GREEN}Initializing [{self.name}] drone.{RESET}")
        await asyncio.sleep(5)
        self.add_behaviour(self.ScanTerrain())
        # self.add_behaviour(self.ReceiveMessages())
        print(f"{GREEN}[{self.name}] Drone online at orbit height {self.orbit_height} km{RESET}")
