import asyncio
from collections import deque
from math import sqrt
from typing import Tuple, List, Dict, Optional

import spade
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message

from world.world import World, WorldObject
from world.map import Map

class Base(Agent):
    def __init__(
        self,
        jid: str,
        password: str,
        position: WorldObject,
        world: World,
        known_drones: List[str],
        known_rovers: List[str],
        satellite_jid: str,
        base_radius: float = 100.0
    ) -> None:
        super().__init__(jid, password)
        self.position = position
        self.world = world
        self.base_radius = base_radius

        # Queues for fair (FIFO) scheduling
        self.drones_queue = deque(known_drones)
        self.rovers_queue = deque(known_rovers)

        # Mission tracking
        self.active_missions: Dict[str, Dict] = {}
        self.resource_reports: List[Dict] = []

    # -------------------------------------------------------------------------
    # UTILITIES
    # -------------------------------------------------------------------------
    async def send_msg(self, to: str, body: str, perf: str, content_type: str = "text"):
        """Unified FIPA-compliant message sending."""
        msg = Message(to=to)
        msg.set_metadata("performative", perf)
        msg.set_metadata("language", content_type)
        msg.body = body
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
    # BEHAVIOUR: Handle messages from Satellite / Drones / Rovers
    # -------------------------------------------------------------------------
    class ManageMissions(CyclicBehaviour):
        async def run(self):
            base = self.agent
            msg = await self.receive(timeout=5)
            if not msg:
                await asyncio.sleep(1)
                return

            perf = msg.metadata.get("performative", "")
            sender = str(msg.sender).split("@")[0]
            print(f"[{base.name}] Received ({perf}) from {sender}: {msg.body}")

            # Satellite requests mission allocation
            if perf == "request":
                mission_data = eval(msg.body)
                target = mission_data.get("target")
                print(f"[{base.name}] Mission request received for area {target}")

                # Assign a Drone and Rover using FIFO
                drone = base.select_drone()
                rover = base.select_rover()
                if not drone or not rover:
                    print(f"[{base.name}] No available agents for mission at {target}")
                    return

                base.active_missions[target] = {"drone": drone, "rover": rover}
                print(f"[{base.name}] Assigned Drone {drone} and Rover {rover} to {target}")

                await base.send_msg(
                    to=drone,
                    body=str({"target": target, "rover": rover}),
                    perf="inform",
                )

            # Drones inform mission completion
            elif perf == "inform_done":
                data = eval(msg.body)
                target = data.get("target")
                drone = sender
                print(f"[{base.name}] Drone {drone} completed mission at {target}")
                base.mark_drone_available(drone)

            # Rovers report mission completion
            elif perf == "inform_success":
                data = eval(msg.body)
                target = data.get("target")
                rover = sender
                print(f"[{base.name}] Rover {rover} finished mission at {target}")
                base.mark_rover_available(rover)

            # Drones or Rovers send resource discovery
            elif perf == "inform_resource":
                resource_data = eval(msg.body)
                base.resource_reports.append(resource_data)
                print(f"[{base.name}] Resource reported: {resource_data}")

            await asyncio.sleep(1)

    # -------------------------------------------------------------------------
    # SETUP
    # -------------------------------------------------------------------------
    async def setup(self):
        print(f"[{self.name}] Base online at position {self.position}")
        self.add_behaviour(self.ManageMissions())
