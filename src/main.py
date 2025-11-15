import random
import asyncio
import spade

import logging
# Set the logging level to DEBUG for SPADE's core components
logging.basicConfig(level=logging.INFO) # Start with INFO
logging.getLogger("spade.xmpp").setLevel(logging.DEBUG) 
logging.getLogger("spade.agent").setLevel(logging.DEBUG)

from world.setting import TAG
from world.world import World, WorldObject
from world.map import Map
from agents.base import Base
from agents.drone import Drone
from agents.rover import Rover
from agents.satellite import Satellite

from typing import Tuple, List

def generate_world(
    map_limit: Tuple[int, int] = (1000, 1000),
    base_center: Tuple[int, int] = (100, 100),
    base_radius: float = 50
) -> Tuple[World, Map, WorldObject, List[Tuple[float, float]], List[Tuple[float, float]], Tuple[float, float]]:
    """Generate the world and assign initial non-colliding positions for all agents."""
    world_map = Map(map_limit)
    world = World([])

    # --- Base object ---
    world.objects.append(WorldObject("base", base_center))

    def random_pos_in_base():
        """Generate a random position within the base radius, ensuring no collisions."""
        while True:
            x = random.uniform(base_center[0] - base_radius, base_center[0] + base_radius)
            y = random.uniform(base_center[1] - base_radius, base_center[1] + base_radius)
            if all(((x - o.pos[0]) ** 2 + (y - o.pos[1]) ** 2) ** 0.5 > 10 for o in world.objects):
                return (x, y)

    # --- Generate initial positions ---
    rover_positions = [random_pos_in_base() for _ in range(2)]
    drone_positions = [random_pos_in_base() for _ in range(2)]

    # --- Register all world objects with unique IDs ---
    for i, pos in enumerate(rover_positions, start=1):
        world.objects.append(WorldObject(f"rover{i}_obj", pos))
    for i, pos in enumerate(drone_positions, start=1):
        world.objects.append(WorldObject(f"drone{i}_obj", pos))

    # --- Satellite position (not colliding) ---
    satellite_pos = (500, 500)
    world.objects.append(WorldObject("satellite_obj", satellite_pos))

    return world, world_map, base_center, rover_positions, drone_positions, satellite_pos

async def main():
    # --- WORLD INITIALIZATION ---
    world, world_map, base_center, rover_positions, drone_positions, satellite_pos = generate_world()

    # --- JIDs ---
    base_jid = f"base@{TAG}"
    satellite_jid = f"satellite@{TAG}"
    rover_jids = [f"rover{i}@{TAG}" for i in range(1, len(rover_positions) + 1)]
    drone_jids = [f"drone{i}@{TAG}" for i in range(1, len(drone_positions) + 1)]

    # --- AGENTS CREATION ---

    # Base knows all other agents
    base = Base(
        base_jid,
        "base",
        base_center,
        rover_jids,
        drone_jids
    )
    print("Initialized Base...")

    # Satellite knows bases
    satellite = Satellite(
        satellite_jid, "satellite",
        world, world_map,
        satellite_pos,
        known_bases=[base_jid]
    )
    print("Initialized Satellite...")

    # Pair drones and rovers (1-to-1)
    rovers = []
    drones = []
    for i, (r_pos, d_pos) in enumerate(zip(rover_positions, drone_positions), start=1):
        rover_jid = f"rover{i}@{TAG}"
        drone_jid = f"drone{i}@{TAG}"

        # Create Rover
        rover = Rover(
            rover_jid, f"rover{i}",
            r_pos, world,
            assigned_drone=drone_jid,
            base_jid=base_jid
        )
        rovers.append(rover)

        # Create Drone
        drone = Drone(
            drone_jid, f"drone{i}",
            d_pos, world, world_map,
            assigned_rover=rover_jid
        )
        drones.append(drone)
    print("Initialized Drones and Rovers...")

    # --- START AGENTS ---

    agents_to_start = rovers + drones + [base, satellite]
    started_agents = []

    for agent in agents_to_start:
        print(f"[MAIN] Starting {agent.name} agent...")
        
        future = agent.start()
        await future
        
        print(f"[MAIN] {agent.name} agent started.")
        started_agents.append(agent)

    print("[MAIN] All agents started and world initialized.")

    await asyncio.sleep(600)

if __name__ == "__main__":
    print(f"Connecting to domain: {TAG}")
    spade.run(main())
