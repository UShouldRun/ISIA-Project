import spade
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour
from spade.message import Message
from spade.template import Template
import asyncio
from typing import Tuple, List, Dict
from math import sqrt

class Base(Agent):
    def __init__(
        self, jid: str, password: str,
        position: Tuple[float, float] = (0, 0)
    ) -> None:
        super().__init__(jid, password)
        self.position = tuple(position)
        self.rovers = {}  # {rover_jid: {"position": (x, y), "energy": int, "status": str}}
        self.drones = {}  # {drone_jid: {"position": (x, y), "energy": int, "status": str}}
        self.resources = []  # List of detected resources
        self.pending_missions = []  # Queue of locations to explore

    def calculate_distance(self, pos1: Tuple[float, float], pos2: Tuple[float, float]) -> float:
        return sqrt((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2)

    def find_closest_rover(self, target_pos: Tuple[float, float]) -> str:
        """Find the closest available rover to a target position"""
        available_rovers = {
            jid: info for jid, info in self.rovers.items() 
            if info.get("status") == "available" and info.get("energy", 0) > 30
        }
        
        if not available_rovers:
            return None
        
        closest_jid = min(
            available_rovers.keys(),
            key=lambda jid: self.calculate_distance(available_rovers[jid]["position"], target_pos)
        )
        return closest_jid

    class ReceiveMessages(CyclicBehaviour):
        async def run(self):
            base = self.agent
            msg = await self.receive(timeout=5)
            
            if msg:
                sender = str(msg.sender).split("@")[0]
                msg_type = msg.metadata.get("type")
                
                print(f"[{base.name}] Message received from {sender} (type: {msg_type})")
                
                if msg_type == "status":
                    # Update rover/drone status
                    if "rover" in sender:
                        if sender not in base.rovers:
                            base.rovers[sender] = {}
                        base.rovers[sender]["status"] = "available"
                        print(f"[{base.name}] Rover {sender} is now available")
                    elif "drone" in sender:
                        if sender not in base.drones:
                            base.drones[sender] = {}
                        base.drones[sender]["status"] = "available"
                        print(f"[{base.name}] Drone {sender} is now available")
                
                elif msg_type == "resource":
                    # Store detected resource
                    resource_data = eval(msg.body)
                    base.resources.append(resource_data)
                    print(f"[{base.name}] Resource logged: {resource_data}")
                    
                    # Notify satellite
                    satellite_msg = Message(
                        to="satellite@planet.local",
                        body=str(resource_data),
                        metadata={"type": "resource_found"}
                    )
                    await self.send(satellite_msg)
                
                elif msg_type == "position_update":
                    # Update rover/drone position
                    position_data = eval(msg.body)
                    if "rover" in sender:
                        if sender not in base.rovers:
                            base.rovers[sender] = {}
                        base.rovers[sender]["position"] = position_data["position"]
                        base.rovers[sender]["energy"] = position_data["energy"]
                    elif "drone" in sender:
                        if sender not in base.drones:
                            base.drones[sender] = {}
                        base.drones[sender]["position"] = position_data["position"]
                        base.drones[sender]["energy"] = position_data["energy"]
                
                elif msg_type == "mission_request":
                    # Satellite requesting closest rover for a mission
                    target_pos = eval(msg.body)
                    closest_rover = base.find_closest_rover(target_pos)
                    
                    response = Message(
                        to=str(msg.sender),
                        body=str({"rover": closest_rover, "target": target_pos}),
                        metadata={"type": "rover_assignment"}
                    )
                    await self.send(response)
                    print(f"[{base.name}] Assigned rover {closest_rover} to mission at {target_pos}")
            
            await asyncio.sleep(1)

    class AssignMissions(CyclicBehaviour):
        async def run(self):
            base = self.agent
            
            # If there are pending missions, try to assign them
            if base.pending_missions:
                mission_pos = base.pending_missions[0]
                closest_rover = base.find_closest_rover(mission_pos)
                
                if closest_rover:
                    msg = Message(
                        to=f"{closest_rover}@planet.local",
                        body=str(mission_pos),
                        metadata={"type": "mission"}
                    )
                    await self.send(msg)
                    base.rovers[closest_rover]["status"] = "on_mission"
                    base.pending_missions.pop(0)
                    print(f"[{base.name}] Mission assigned to {closest_rover}: go to {mission_pos}")
            
            await asyncio.sleep(10)

    async def setup(self):
        print(f"[{self.name}] Base operational at position {self.position}")
        self.add_behaviour(self.ReceiveMessages())
        self.add_behaviour(self.AssignMissions())
