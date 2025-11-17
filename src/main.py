import random
import asyncio
import spade
import logging
import json
import sys
from typing import Tuple, List, Dict, Any

from world.setting import TAG
from world.world import World, WorldObject
from world.map import Map
from agents.base import Base
from agents.drone import Drone
from agents.rover import Rover
from agents.visualizator import VisualizationServer

def setup_logging(config: Dict[str, Any]):
    """Configure logging based on config file."""
    log_config = config.get("logging", {})
    
    base_level = log_config.get("base_level", "INFO")
    logging.basicConfig(level=getattr(logging, base_level))
    
    xmpp_level = log_config.get("spade_xmpp_level", "DEBUG")
    logging.getLogger("spade.xmpp").setLevel(getattr(logging, xmpp_level))
    
    agent_level = log_config.get("spade_agent_level", "DEBUG")
    logging.getLogger("spade.agent").setLevel(getattr(logging, agent_level))

def load_config(config_path: str) -> Dict[str, Any]:
    """Load and parse the JSON configuration file."""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        print(f"[CONFIG] Loaded configuration from: {config_path}")
        return config
    except FileNotFoundError:
        print(f"[ERROR] Configuration file not found: {config_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON in configuration file: {e}")
        sys.exit(1)

def random_pos_in_base(world: World, base_name: str, base_centers: Dict[str, Tuple[float, float]], base_radii: Dict[str, float]):
    """Generate a random position within the specified base radius, ensuring no collisions."""
    if base_name not in base_centers:
        print(f"[WARNING] Base '{base_name}' not found, using default position")
        return (100, 100)
    
    base_center = base_centers[base_name]
    base_radius = base_radii.get(base_name, 50)
    
    max_attempts = 100
    for _ in range(max_attempts):
        x = random.uniform(base_center[0] - base_radius, base_center[0] + base_radius)
        y = random.uniform(base_center[1] - base_radius, base_center[1] + base_radius)
        if all(((x - o.pos[0]) ** 2 + (y - o.pos[1]) ** 2) ** 0.5 > 10 for o in world.objects):
            return (x, y)
    # Fallback if collision-free position not found
    print("[WARNING] Could not find collision-free position, using fallback")
    return (base_center[0], base_center[1])

def generate_world(config: Dict[str, Any], tag: str) -> Tuple[World, Map, Dict[str, Tuple[float, float]], List[Tuple[float, float]]]:
    """Generate the world based on configuration."""
    world_config = config.get("world", {})
    base_configs = config.get("bases", [])
    rover_configs = config.get("rovers", [])
    drone_configs = config.get("drones", [])
    
    map_limit = tuple(world_config.get("map_limit", [1000, 1000]))
    
    world_map = Map(map_limit)
    world = World([])
    
    # Dictionary to store base centers by base name
    base_centers = {}
    base_radii = {}
    
    # --- Create base objects ---
    for base_config in base_configs:
        base_name = base_config.get("name", base_config["jid"])
        base_center = tuple(base_config.get("center", [100, 100]))
        base_radius = base_config.get("radius", 50)
        
        base_centers[base_name] = base_center
        base_radii[base_name] = base_radius
        world.objects.append(WorldObject(f"{base_config["jid"]}@{tag}", base_center))
        
    # --- Process rover positions ---
    rover_positions = []
    for rover_config in rover_configs:
        pos = rover_config.get("position", "random_in_base")
        if pos == "random_in_base":
            # Get the base this rover belongs to
            rover_base = rover_config.get("base")
            if not rover_base and base_configs:
                rover_base = base_configs[0].get("name", base_configs[0]["jid"])
            pos = random_pos_in_base(world, rover_base, base_centers, base_radii)
        else:
            pos = tuple(pos)
        rover_positions.append(pos)
    
    # --- Register rover world objects ---
    for i, (rover_config, pos) in enumerate(zip(rover_configs, rover_positions), start=1):
        rover_name = rover_config.get("name", f"rover{i}")
        world.objects.append(WorldObject(f"{rover_config["jid"]}@{tag}", pos))
    
    # --- Process drone positions ---
    drone_positions = []
    for drone_config in drone_configs:
        pos = tuple(drone_config.get("position", [500, 500]))
        drone_positions.append(pos)
        drone_name = drone_config.get("name", drone_config["jid"])
        world.objects.append(WorldObject(f"{drone_config["jid"]}@{tag}", pos))
    
    return world, world_map, base_centers, rover_positions, drone_positions

async def simulate_hazards(world_map: Map, interval: int = 10):
    def clear_storm() -> bool:
        """Resets the storm flag on all cells and returns True if any storm was cleared."""
        was_cleared = False
        for i in range(world_map.columns):
            for j in range(world_map.rows):
                cell = world_map.get_cell(i, j)
                if cell.dust_storm:
                    cell.dust_storm = False
                    was_cleared = True
        return was_cleared

    while True:
        await asyncio.sleep(interval)
        
        if clear_storm():
            print("[HAZARD] Previous storm subsided. Map cells reset.")
        
        # 3. Randomly introduce a new storm (e.g., 10% chance)
        if random.random() < STORM_CHANCE: 
            # Choose a center for the storm

            center_x = random.randint(0, world_map.columns - 1)
            center_y = random.randint(0, world_map.rows - 1)

            # Choose a radius (in map units)
            radius = random.randint(50, 200)

            print(f"[HAZARD] New dust storm forming at ({center_x}, {center_y}) with radius {radius}.")

            # Update the affected MapCells
            for i in range(world_map.columns):
                for j in range(world_map.rows):
                    cell = world_map.get_cell(i, j)
                    
                    # Calculate distance
                    dist = ((cell.x - center_x) ** 2 + (cell.y - center_y) ** 2) ** 0.5
                    
                    if dist < radius:
                        cell.dust_storm = True
            
            print(f"[HAZARD] Map updated. Agents will calculate new paths.")
        
        else:
            print("[HAZARD] All clear. No new storm detected.")

async def main():
    # --- LOAD CONFIGURATION ---
    if len(sys.argv) < 2:
        print("[ERROR] Usage: python main.py <config_file.json>")
        sys.exit(1)
    
    config_path = sys.argv[1]
    config = load_config(config_path)
    
    # --- SETUP LOGGING ---
    setup_logging(config)
    
    # --- CREATE VISUALIZATION SERVER ---
    viz_server = VisualizationServer()
    runner = await viz_server.start_server()

    # --- EXTRACT CONFIG VALUES ---
    sim_config = config.get("simulation", {})
    duration = sim_config.get("duration_seconds", 600)
    tag = sim_config.get("tag", TAG)
    
    base_configs = config.get("bases", [])
    drone_configs = config.get("drones", [])
    rover_configs = config.get("rovers", [])
    
    # --- WORLD INITIALIZATION ---
    world, world_map, base_centers, rover_positions, drone_positions = generate_world(config, tag)
    
    # --- BUILD JID MAPS ---
    base_jids = {b["jid"]: f"{b['jid']}@{tag}" for b in base_configs}
    drone_jids = {d["jid"]: f"{d['jid']}@{tag}" for d in drone_configs}
    rover_jids = {r["jid"]: f"{r['jid']}@{tag}" for r in rover_configs}
    
    # --- CREATE AGENTS ---
    agents_to_start = []
    
    # Create Bases
    bases = {}
    for base_config in base_configs:
        base_jid = base_jids[base_config["jid"]]
        base_name = base_config.get("name", base_config["jid"])
        base_center = base_centers[base_name]
        
        # Find all rovers assigned to this base
        rovers_for_this_base = [
            rover_jids[r["jid"]] 
            for r in rover_configs 
            if r.get("base", base_configs[0].get("name") if base_configs else None) == base_name
        ]
        drones_for_this_base = [
            drone_jids[d["jid"]]
            for d in drone_configs
        ]
        
        base = Base(
            base_jid,
            base_name,
            base_center,
            rovers_for_this_base,
            drones_for_this_base
        )
        bases[base_jid] = base
        agents_to_start.append(base)
        print(f"[INIT] Initialized Base '{base_name}' at {base_center} with {len(rovers_for_this_base)} rovers")
    
    # Create Drones
    drones = {}
    for i, (drone_config, drone_pos) in enumerate(zip(drone_configs, drone_positions)):
        drone_jid = drone_jids[drone_config["jid"]]
        drone_name = drone_config.get("name", drone_config["jid"])
        
        # Get known bases for this drone
        known_base_names = drone_config.get("known_bases", [])
        known_base_jids = [base_jids[b] for b in known_base_names if b in base_jids]
        
        drone = Drone(
            drone_jid,
            drone_name,
            world,
            world_map,
            drone_pos,
            known_bases=known_base_jids
        )
        drones[drone_jid] = drone
        agents_to_start.append(drone)
        print(f"[INIT] Initialized Drone '{drone_name}' at {drone_pos} knowing {len(known_base_jids)} bases")
    
    # Create Rovers
    rovers = {}
    for i, (rover_config, rover_pos) in enumerate(zip(rover_configs, rover_positions)):
        rover_jid = rover_jids[rover_config["jid"]]
        rover_name = rover_config.get("name", rover_config["jid"])
        
        # Get assigned drone
        assigned_drone_name = rover_config.get("assigned_drone")
        assigned_drone_jid = drone_jids.get(assigned_drone_name) if assigned_drone_name else None
        
        # Get base
        rover_base_name = rover_config.get("base")
        if not rover_base_name and base_configs:
            rover_base_name = base_configs[0].get("name", base_configs[0]["jid"])
        rover_base_jid = base_jids.get(rover_base_name)
        
        rover = Rover(
            rover_jid,
            rover_name,
            rover_pos,
            world,
            world_map,
            base_jid=rover_base_jid,
            base_position=bases[base_jid].position
        )
        rovers[rover_jid] = rover
        agents_to_start.append(rover)
        print(f"[INIT] Initialized Rover '{rover_name}' at {rover_pos} (Base: {rover_base_name}, Drone: {assigned_drone_name})")
    
    # --- START AGENTS ---
    print(f"\n[MAIN] Starting {len(agents_to_start)} agents...")
    started_agents = []
    for agent in agents_to_start:
        print(f"[MAIN] Starting {agent.name} agent...")
        
        future = agent.start()
        await future
        
        print(f"[MAIN] {agent.name} agent started.")
        started_agents.append(agent)
    
    print(f"\n[MAIN] All agents started. Running simulation for {duration} seconds...")
    print(f"[MAIN] Summary: {len(bases)} bases, {len(drones)} drones, {len(rovers)} rovers\n")
    
    # --- RUN SIMULATION ---
    await asyncio.sleep(duration)
    
    print("\n[MAIN] Simulation complete. Stopping agents...")
    for agent in started_agents:
        await agent.stop()
    
    print("[MAIN] All agents stopped.")

if __name__ == "__main__":
    print(f"[MAIN] Multi-Agent System Simulation")
    spade.run(main())
