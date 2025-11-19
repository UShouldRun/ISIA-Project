import asyncio
import random

from typing import Dict, Tuple, List

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour, State
from spade.message import Message

from world.world import World, WorldObject
from world.map import Map

from agents.visualizator import VisualizationBehaviour, VisualizationMixin

from settings import *

class Drone(VisualizationMixin, Agent):
    """
    Aerial surveillance drone for terrain scanning and mission coordination.
    
    Continuously scans the terrain for areas of interest, negotiates with base
    stations using the FIPA Contract Net Protocol to assign exploration missions
    to rovers, and manages base availability.
    
    Attributes:
        world (World): Reference to the simulation world.
        map (Map): Map representation of the terrain.
        position (Tuple[float, float]): Current (x, y) coordinates of the drone.
        height (float): Altitude above ground in kilometers.
        scan_radius (float): Detection radius for terrain scanning.
        bases (List[str]): List of available base station JIDs.
        non_available_bases (List[str]): List of base JIDs currently without rovers.
        areas_of_interest (List[Tuple[float, float]]): Detected locations needing exploration.
        current_scan_position (List[float]): Current scanning window position.
        proposals (Dict[str, Dict]): Temporary storage for base bids during negotiation.
        viz_server: Visualization server connection.
    """
    
    def __init__(
        self,
        jid: str,
        password: str,
        world: World,
        map_: Map,
        position: Tuple[float, float],
        known_bases: List[str],
        height: float = 1.0,
        scan_radius: float = 20.0,
        viz_server = None
    ) -> None:
        """
        Initialize a Drone agent.
        
        Args:
            jid (str): XMPP JID for the drone agent.
            password (str): Password for XMPP authentication.
            world (World): Simulation world instance.
            map_ (Map): Map instance for terrain information.
            position (Tuple[float, float]): Starting (x, y) position.
            known_bases (List[str]): List of base station JIDs to coordinate with.
            height (float): Operating altitude in kilometers.
            scan_radius (float): Scanning detection radius.
            viz_server: Visualization server instance.
        """
        super().__init__(jid, password)
        self.world = world
        self.map = map_
        self.position = position

        self.height = height
        self.scan_radius = scan_radius

        self.bases = known_bases
        self.non_available_bases = []

        self.areas_of_interest = []
        self.current_scan_position = [0, 0]
        self.proposals: Dict[str, Dict] = {}

        self.areas_of_interest: List[Tuple[float, float]] = []
        self.current_scan_position = list(self.position)

        self.viz_server = viz_server
        if self.viz_server:
            self.setup_visualization(
                self.viz_server,
                agent_type="drone",
                agent_jid=jid,
                position=position,
                battery=100.0,
                color="#00F000",
                radius=scan_radius
            )

    class ScanTerrain(CyclicBehaviour):
        """
        Continuously scan terrain in a grid pattern to detect areas of interest.
        
        Moves scanning window across the map and probabilistically identifies
        locations requiring exploration. Initiates mission requests when areas
        are detected.
        """
        
        async def on_start(self):
            """
            Initialize terrain scanning and announce start.
            """
            print(f"{GREEN}[{self.agent.name}] Starting terrain scanning...{RESET}")
            await self.agent.viz_send_message("Starting terrain scanning")

        def in_scan_radius(self, scan_pos: Tuple[int, int]):
            drone = self.agent
            return ((drone.position[0] - scan_pos[0]) ** 2 + (drone.position[1] - scan_pos[1]) ** 2) <= drone.scan_radius ** 2

        def is_area_of_interest(self) -> bool:
            """
            Determine if current scan position is an area of interest.
            
            Returns:
                bool: True with 25% probability, False otherwise.
            """
            return random.random() < 0.25

        async def run(self):
            """
            Execute one scanning iteration.
            
            Advances scan position, checks for areas of interest, and initiates
            mission negotiation with available bases. Handles base unavailability
            by scheduling recheck behavior.
            """
            drone = self.agent

            rate = drone.map.length // SCAN_MAP_SIZE
            drone.current_scan_position[0] += rate
            if drone.current_scan_position[0] > drone.map.length:
                drone.current_scan_position[0] = 0
                drone.current_scan_position[1] += rate

            if drone.current_scan_position[1] > drone.map.height:
                drone.current_scan_position[1] = 0

            scan_pos = tuple(drone.current_scan_position)

            print(f"{GREEN}[{drone.name}] Scanning area: {scan_pos}{RESET}")
            
            if self.is_area_of_interest() and self.in_scan_radius(scan_pos):
                drone.areas_of_interest.append(scan_pos)
                print(f"{GREEN}[{drone.name}] Area of interest detected at {scan_pos}{RESET}")
                await drone.viz_send_message(f"Area of interest detected at {scan_pos}")
                
                if not drone.bases:
                    print(f"{GREEN}[{drone.name}] No bases available. Trying later...{RESET}")
                    await drone.viz_send_message("No bases available - will retry later")
                    self.kill()
                    drone.add_behaviour(drone.RecheckBaseAvailability())
                    return

                self.kill()
                drone.add_behaviour(drone.RequestAgentForMission(scan_pos))

    class RequestAgentForMission(OneShotBehaviour):
        """
        Implement FIPA Contract Net Protocol initiator for mission assignment.
        
        Sends CFPs to all base stations, collects proposals, selects the best bid,
        and coordinates mission acceptance/rejection with bases.
        
        Attributes:
            target_position (Tuple[float, float]): Mission target coordinates.
        """
        
        def __init__(self, target_position: Tuple[float, float]):
            """
            Initialize mission request behavior.
            
            Args:
                target_position (Tuple[float, float]): Target (x, y) coordinates for exploration.
            """
            super().__init__()
            self.target_position = target_position

        async def run(self):
            """
            Execute contract net protocol for mission assignment.
            
            Broadcasts CFP to all bases, collects proposals within timeout period,
            processes responses, and selects winning bid. Resumes scanning after
            negotiation completion.
            """
            drone = self.agent
 
            for base_jid in drone.bases:
                msg = Message(to=base_jid)
                msg.set_metadata("performative", "cfp")
                msg.set_metadata("type", "rover_mission_cfp")
                msg.body = str(self.target_position)
                await self.send(msg)
                print(f"{GREEN}[{drone.name}] CFP sent to {base_jid} for mission at {self.target_position}{RESET}")
            
            await drone.viz_send_message(f"Requesting mission bids for target {self.target_position}")

            timeout = 4

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
                    elif perf == "inform":
                        self.on_inform(msg)

            await self.on_all_responses_received()
            drone.add_behaviour(drone.ScanTerrain())
            
        def on_refuse(self, message: Message):
            """
            Handle refusal from base unable to provide a rover.
            
            Moves base to non-available list if it has no rovers.
            
            Args:
                message (Message): Refusal message containing reason.
            """
            drone = self.agent
            reason = eval(message.body)["reason"]
            print(f"{GREEN}[{drone.name}] Base {str(message.sender).split('@')[0]} refused to bid for mission at {self.target_position}: reason - {reason}{RESET}")
            if reason == "no_rovers_available":
               drone.bases.remove(message.sender) 
               drone.non_available_bases.append(message.sender)

        def on_inform(self, message: Message):
            """
            Handle informational messages from bases.
            
            Processes base availability updates and moves bases back to
            available list when rovers become ready.
            
            Args:
                message (Message): Inform message with status update.
            """
            drone = self.agent
            msg_info = eval(message.body)["inform"]
            print(f"{GREEN}[{drone.name}] message info {msg_info}{RESET}") 

            if msg_info == "has_rovers_available":
                print(f"{GREEN}[{drone.name}] Base {str(message.sender).split('@')[0]} informed it has rovers available{RESET}")
                drone.non_available_bases.remove(message.sender)
                drone.bases.append(message.sender)

        def on_failure(self, message: Message):
            """
            Handle failure during contract negotiation.
            
            Args:
                message (Message): Failure notification from base.
            """
            print(f"{GREEN}[{self.agent.name}] Base {str(message.sender).split('@')[0]} failed during the contract net protocol.{RESET}")

        def on_not_understood(self, message: Message):
            """
            Handle not-understood messages when CFP format is invalid.
            
            Args:
                message (Message): Not-understood notification from base.
            """
            print(f"{GREEN}[{self.agent.name}] Base {str(message.sender).split('@')[0]} did not understand the CFP.{RESET}")

        async def on_propose(self, message: Message):
            """
            Process proposal bids from base stations.
            
            Validates bid format, extracts cost and rover information, and
            stores valid proposals for later evaluation.
            
            Args:
                message (Message): Proposal message containing bid details.
            """
            try:
                bid_data = eval(message.body)
                cost = float(bid_data.get("cost", float('inf')))
                base_jid = bid_data.get("base")
                rover_jid = bid_data.get("rover")
                
                print(f"{GREEN}[{self.agent.name}] Received PROPOSAL from base: {base_jid}: Cost={cost}, Rover={rover_jid}{RESET}")
                await self.agent.viz_send_message(f"Received bid from {str(base_jid).split('@')[0]} (cost: {cost:.1f}s)")
                                
                if base_jid is not None and rover_jid is not None:
                    self.agent.proposals[base_jid] = {"cost": cost, "base": base_jid, "rover": rover_jid, "proposal_msg": message}
                else:
                    print(f"{GREEN}[{self.agent.name}] Ignoring invalid proposal from {message.sender}: No 'rover' specified.{RESET}")
            
            except (SyntaxError, TypeError, ValueError):
                print(f"{GREEN}[{self.agent.name}] Invalid proposal format from {message.sender}. Body: {message.body}{RESET}")

        async def on_all_responses_received(self):
            """
            Evaluate all proposals and select winning bid.
            
            Chooses base with lowest mission cost, sends acceptance to winner,
            sends rejections to other bidders, and clears proposal storage.
            Handles case where no valid proposals are received.
            """
            drone = self.agent
            print(f"{GREEN}[{drone.name}] All responses received for mission at {self.target_position}.{RESET}")

            if not drone.proposals:
                print(f"{GREEN}[{drone.name}] No proposals received for mission at {self.target_position}. Retrying later.{RESET}")
                await drone.viz_send_message(f"No bids received for {self.target_position} - will retry")
                drone.proposals = {} 
                return

            best_base, best_data = min(drone.proposals.items(), key=lambda x: x[1]["cost"])           
            min_cost = best_data['cost']

            if best_base:
                print(f"{GREEN}[{drone.name}] Accepting proposal from {best_base} with cost {min_cost}{RESET}")
                await drone.viz_send_message(f"Accepted bid from {str(best_base).split('@')[0]} for mission to {self.target_position}")

                accept_msg = Message(to=best_base)
                accept_msg.set_metadata("performative", "accept_proposal")
                accept_msg.set_metadata("type", "rover_bid_accepted")
                accept_msg.body = str({"target": self.target_position, "rover": best_data["rover"]})

                await self.send(accept_msg)

                for base_jid, data in drone.proposals.items():
                    if base_jid != best_base:
                        print(f"{GREEN}[{drone.name}] Rejecting proposal from {base_jid}{RESET}")
                        reject_msg = Message(to=base_jid)
                        reject_msg.set_metadata("performative", "reject_proposal")
                        reject_msg.set_metadata("type", "rover_bid_rejected")
                        reject_msg.body = str({"target": self.target_position, "rover": data["rover"]})

                        await self.send(reject_msg)
            else:
                print(f"{GREEN}[{drone.name}] No suitable proposals received for mission at {self.target_position}. Retrying later.{RESET}")
                await drone.viz_send_message(f"No suitable bids for {self.target_position} - will retry")

            drone.proposals = {}

        async def on_inform(self, message: Message):
            """
            Handle mission confirmation from winning base.
            
            Receives acknowledgment that rover has been assigned to the mission.
            
            Args:
                message (Message): Inform message with mission details.
            """
            sender = str(message.sender)
            print(f"{GREEN}[{self.agent.name}] Received INFORM from winning base {sender}.{RESET}")

    class ReceiveMessages(CyclicBehaviour):
        """
        Process incoming messages from base stations outside negotiation.
        
        Handles base availability updates and other inform messages.
        """
        
        async def run(self):
            """
            Receive and process messages about base status changes.
            
            Updates base availability when rovers return and become ready
            for new missions.
            """
            drone = self.agent
            msg = await self.receive()

            if msg:
                perf = msg.metadata.get("performative")
                msg_type = msg.metadata.get("type")
                sender = str(msg.sender).split("@")[0]
              
                print(f"{GREEN}[{drone.name}] Message received from {sender} (type: {msg_type}){RESET}")

                if perf == "inform":
                    msg_info = eval(msg.body)["inform"]
                    if msg_info == "has_rovers_available":
                        print(f"{GREEN}[{drone.name}] Base {sender} informed it has rovers available{RESET}")
                        await drone.viz_send_message(f"Base {sender} now has rovers available")
                        drone.non_available_bases.remove(msg.sender)
                        drone.bases.append(msg.sender)

    class RecheckBaseAvailability(CyclicBehaviour):
        """
        Periodically restore unavailable bases to retry mission assignments.
        
        After a delay, moves all bases from non-available back to available list
        and resumes terrain scanning.
        """
        
        async def run(self):
            """
            Wait 30 seconds then restore all bases and resume scanning.
            
            Moves bases from non_available_bases back to bases list and
            restarts the terrain scanning behavior.
            """
            drone = self.agent
            await asyncio.sleep(30)

            print(f"{GREEN}[{drone.name}] preparing to check base availability{RESET}")
            await drone.viz_send_message("Rechecking base availability")
            drone.bases.extend(drone.non_available_bases)
            drone.non_available_bases = []

            drone.add_behaviour(drone.ScanTerrain())
            self.kill()

    async def setup(self):
        """
        Initialize the drone agent and start its behaviors.
        
        Registers terrain scanning, message receiving, and visualization behaviors.
        Announces drone online status.
        """
        print(f"{GREEN}Initializing [{self.name}] drone.{RESET}")
        await asyncio.sleep(2)
        await self.viz_update_status("running")
        self.add_behaviour(self.ScanTerrain())
        self.add_behaviour(self.ReceiveMessages())

        if hasattr(self, "viz_server"):
            self.add_behaviour(VisualizationBehaviour())

        print(f"{GREEN}[{self.name}] Drone online at height {self.height} km{RESET}")
        await self.viz_send_message(f"Drone online at height {self.height} km")
