import spade
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour
from spade.message import Message
from spade.template import Template
import asyncio
from typing import Tuple, List, Dict
from math import sqrt

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

    async def setup(self):
        print(f"[{self.name}] Satellite online at orbit height {self.orbit_height}km")
        self.add_behaviour(self.ScanTerrain())
        self.add_behaviour(self.ReceiveMessages())
        self.add_behaviour(self.MonitorMissions())
