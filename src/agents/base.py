import spade
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
import asyncio
from typing import Tuple, Dict
from math import sqrt

class Base(Agent):
    def __init__(
        self, jid: str, password: str,
        position: Tuple[float, float] = (0, 0)
    ) -> None:
        super().__init__(jid, password)
        self.position = tuple(position)
        self.rovers: Dict[str, Dict] = {}   # {rover_jid: {"position": (x, y), "energy": int, "status": str}}
        self.drones: Dict[str, Dict] = {}   # {drone_jid: {"position": (x, y), "energy": int, "status": str}}
        self.resources = []                 # List of detected resources
        self.pending_missions = []          # Queue of locations to explore

    # -------------------------------------------------------------------------
    # UTILITIES
    # -------------------------------------------------------------------------
    def calculate_distance(self, pos1: Tuple[float, float], pos2: Tuple[float, float]) -> float:
        return sqrt((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2)

    def find_closest_rover(self, target_pos: Tuple[float, float]) -> str:
        """Find the closest available rover to a target position."""
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

    async def send_message(self, to: str, msg_type: str, body: str):
        """Unified communication for all outgoing Base messages."""
        msg = Message(to=to, metadata={"type": msg_type}, body=body)
        await self.send(msg)
        print(f"[{self.name}] → Sent to {to} ({msg_type}): {body}")

    # -------------------------------------------------------------------------
    # BEHAVIOURS
    # -------------------------------------------------------------------------
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

    class AssignMissions(CyclicBehaviour):
        async def run(self):
            base = self.agent

            # If there are pending missions, assign them to the closest available rover
            if base.pending_missions:
                mission_pos = base.pending_missions[0]
                closest_rover = base.find_closest_rover(mission_pos)

                if closest_rover:
                    await base.send_message(
                        f"{closest_rover}@planet.local",
                        "mission",
                        str(mission_pos)
                    )

                    base.rovers[closest_rover]["status"] = "on_mission"
                    base.pending_missions.pop(0)
                    print(f"[{base.name}] Mission assigned to {closest_rover}: go to {mission_pos}")

            await asyncio.sleep(10)

    # -------------------------------------------------------------------------
    # SETUP
    # -------------------------------------------------------------------------
    async def setup(self):
        print(f"[{self.name}] Base operational at position {self.position}")
        self.add_behaviour(self.ReceiveMessages())
        self.add_behaviour(self.AssignMissions())
