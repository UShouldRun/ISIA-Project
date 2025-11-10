import asyncio
import random
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour
from spade.message import Message
from typing import Tuple, List

from world.world import World, WorldObject
from world.map import Map

class Satellite(Agent):
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

        self.known_bases = known_bases
        self.orbit_height = orbit_height
        self.scan_radius = scan_radius

        self.scanned_areas: List[Tuple[float, float]] = []
        self.areas_of_interest: List[Tuple[float, float]] = []
        self.current_scan_position = list(self.position)

    # -------------------------------------------------------------------------
    # COMMUNICATION (FIPA-Compliant)
    # -------------------------------------------------------------------------
    async def send_msg(self, to: str, performative: str, ontology: str, body: str):
        msg = Message(to=to)
        msg.set_metadata("performative", performative)
        msg.set_metadata("ontology", ontology)
        msg.body = body
        await self.send(msg)
        print(f"[{self.name}] → Sent {performative}/{ontology} to {to}: {body}")

    # -------------------------------------------------------------------------
    # BEHAVIOURS
    # -------------------------------------------------------------------------
    class ScanTerrain(CyclicBehaviour):
        async def on_start(self):
            print(f"[{self.agent.name}] Starting terrain scanning...")

        async def run(self):
            satellite = self.agent

            # Move scanning window
            satellite.current_scan_position[0] += 100
            if satellite.current_scan_position[0] > satellite.map.length:
                satellite.current_scan_position[0] = 0
                satellite.current_scan_position[1] += 100

            if satellite.current_scan_position[1] > satellite.map.height:
                satellite.current_scan_position[1] = 0

            scan_pos = tuple(satellite.current_scan_position)

            if scan_pos not in satellite.scanned_areas:
                satellite.scanned_areas.append(scan_pos)
                print(f"[{satellite.name}] Scanning area {scan_pos}")

                # 30% chance to detect an area of interest
                if random.random() < 0.3:
                    satellite.areas_of_interest.append(scan_pos)
                    print(f"[{satellite.name}] Area of interest detected at {scan_pos}")
                    satellite.add_behaviour(
                        satellite.RequestMission(scan_pos)
                    )

            await asyncio.sleep(3)

    class RequestMission(OneShotBehaviour):
        def __init__(self, target_position: Tuple[float, float]):
            super().__init__()
            self.target_position = target_position

        async def run(self):
            satellite = self.agent
            for base_jid in satellite.known_bases:
                await satellite.send_msg(
                    base_jid,
                    performative="request",
                    ontology="mission_assignment",
                    body=str(self.target_position),
                )
                print(f"[{satellite.name}] Requested mission at {self.target_position} from {base_jid}")

    class ReceiveMessages(CyclicBehaviour):
        async def run(self):
            satellite = self.agent
            msg = await self.receive(timeout=5)

            if msg:
                performative = msg.metadata.get("performative")
                ontology = msg.metadata.get("ontology")
                sender = str(msg.sender).split("@")[0]

                print(f"[{satellite.name}] Received {performative}/{ontology} from {sender}")

                if performative == "inform" and ontology == "rover_assignment":
                    assignment = eval(msg.body)
                    rover_jid = assignment.get("rover")
                    target = assignment.get("target")

                    if rover_jid:
                        await satellite.send_msg(
                            f"{rover_jid}@localhost",
                            performative="request",
                            ontology="exploration_mission",
                            body=str(target),
                        )
                        print(f"[{satellite.name}] Sent exploration mission to {rover_jid} for {target}")
                    else:
                        print(f"[{satellite.name}] No available rover for mission {target}")

                elif performative == "inform" and ontology == "resource_report":
                    resource_data = eval(msg.body)
                    print(f"[{satellite.name}] Confirmed resource at {resource_data}")

            await asyncio.sleep(1)

    class MonitorMissions(CyclicBehaviour):
        async def run(self):
            satellite = self.agent
            print(
                f"[{satellite.name}] Status: {len(satellite.scanned_areas)} scanned, "
                f"{len(satellite.areas_of_interest)} interest zones"
            )
            await asyncio.sleep(30)

    async def setup(self):
        print(f"[{self.name}] Satellite online at orbit height {self.orbit_height} km")
        self.add_behaviour(self.ScanTerrain())
        self.add_behaviour(self.ReceiveMessages())
        self.add_behaviour(self.MonitorMissions())
