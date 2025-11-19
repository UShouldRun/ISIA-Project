import asyncio
import json
import aiohttp
import logging
import sys
import random

from typing import Tuple, List, Optional, Dict, Any
from collections import defaultdict

from aiohttp import web

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour

from world.world import World, WorldObject
from world.map import Map
from agents.base import Base
from agents.drone import Drone
from agents.rover import Rover

from settings import *

def setup_logging(config: Dict[str, Any]):
    """
    Configure logging based on the configuration dictionary.

    Args:
        config (Dict[str, Any]): Configuration dictionary containing logging settings.
    """
    log_config = config.get("logging", {})
    
    base_level = log_config.get("base_level", "INFO")
    logging.basicConfig(level=getattr(logging, base_level))
    
    xmpp_level = log_config.get("spade_xmpp_level", "DEBUG")
    logging.getLogger("spade.xmpp").setLevel(getattr(logging, xmpp_level))
    
    agent_level = log_config.get("spade_agent_level", "DEBUG")
    logging.getLogger("spade.agent").setLevel(getattr(logging, agent_level))

def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load and parse the JSON configuration file.

    Args:
        config_path (str): Path to the JSON configuration file.

    Returns:
        Dict[str, Any]: Parsed configuration dictionary.

    Raises:
        SystemExit: If the file is not found or JSON is invalid.
    """
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        print(f"[CONFIG] Loaded configuration from: {config_path}")
        return config
    except FileNotFoundError:
        print(f"[ERROR] Configuration file not found: {config_path}")
        raise
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON in configuration file: {e}")
        raise

def random_pos_in_base(world: World, base_name: str, base_centers: Dict[str, Tuple[float, float]], base_radii: Dict[str, float]):
    """
    Generate a random collision-free position within a specified base radius.

    Args:
        world (World): The world object containing all existing objects.
        base_name (str): Name of the base to generate the position within.
        base_centers (Dict[str, Tuple[float, float]]): Dictionary mapping base names to their centers.
        base_radii (Dict[str, float]): Dictionary mapping base names to their radii.

    Returns:
        Tuple[float, float]: Random collision-free coordinates within the base.
    """
    if base_name not in base_centers:
        print(f"[WARNING] Base '{base_name}' not found, using default position")
        return (100, 100)
    
    base_center = base_centers[base_name]
    base_radius = base_radii.get(base_name, 50)
    
    max_attempts = 100
    for _ in range(max_attempts):
        x = random.uniform(base_center[0] - 0.15 * base_radius, base_center[0] + 0.15 * base_radius)
        y = random.uniform(base_center[1] - 0.15 * base_radius, base_center[1] + 0.15 * base_radius)
        if all(((x - o.pos[0]) ** 2 + (y - o.pos[1]) ** 2) ** 0.5 > COLLISION_RADIUS for o in world.objects):
            return (x, y)
    
    print("[WARNING] Could not find collision-free position, using fallback")
    return (base_center[0], base_center[1])

def generate_world(config: Dict[str, Any], tag: str) -> Tuple[World, Map, Dict[str, Tuple[float, float]], List[Tuple[float, float]]]:
    """
    Generate the world environment, map, and initial positions of rovers and drones.

    Args:
        config (Dict[str, Any]): Simulation configuration.
        tag (str): Tag used to construct agent JIDs.

    Returns:
        Tuple[World, Map, Dict[str, Tuple[float, float]], List[Tuple[float, float]], List[Tuple[float, float]]]:
        - World object containing all agents and objects.
        - Map object representing terrain.
        - Dictionary of base centers by name.
        - List of rover positions.
        - List of drone positions.
    """
    world_config = config.get("world", {})
    base_configs = config.get("bases", [])
    rover_configs = config.get("rovers", [])
    drone_configs = config.get("drones", [])
    
    map_limit = tuple(world_config.get("map_limit", [100, 100]))
    
    world_map = Map(map_limit)
    world = World([])
    
    base_centers = {}
    base_radii = {}
    
    # --- Create base objects ---
    for base_config in base_configs:
        base_name = base_config.get("name", base_config["jid"])
        base_center = tuple(base_config.get("center", [100, 100]))
        base_radius = base_config.get("radius", 50)
        
        base_centers[base_name] = base_center
        base_radii[base_name] = base_radius
        world.objects.append(WorldObject(f"{base_config['jid']}@{tag}", base_center))
        
    # --- Process rover positions ---
    rover_positions = []
    for rover_config in rover_configs:
        pos = rover_config.get("position", "random_in_base")
        if pos == "random_in_base":
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
        world.objects.append(WorldObject(f"{rover_config['jid']}@{tag}", pos))
    
    # --- Process drone positions ---
    drone_positions = []
    for drone_config in drone_configs:
        pos = tuple(drone_config.get("position", [500, 500]))
        drone_positions.append(pos)
        drone_name = drone_config.get("name", drone_config["jid"])
        world.objects.append(WorldObject(f"{drone_config['jid']}@{tag}", pos))
    
    return world, world_map, base_centers, rover_positions, drone_positions

async def simulate_hazards(world_map: Map, viz_server: Any, interval: int = 10):
    """
    Continuously simulate dust storms in the environment and update the visualization.

    Args:
        world_map (Map): The map object representing terrain.
        viz_server (Any): Visualization server to push updates.
        interval (int, optional): Time in seconds between hazard checks. Defaults to 10.
    """
    async def clear_storm(world_map: Map):
        """
        Clears any active dust storms on the map and sends updates to visualization.

        Args:
            world_map (Map): The map object.
        """
        logging.info("[HAZARD] clearing for new storm...")
        for i in range(world_map.columns):
            for j in range(world_map.rows):
                cell = world_map.get_cell(i, j)
                if cell.dust_storm:
                    world_map.clear_dust_cell(i, j)

        flat_map  = [] 
        max_viz_x = min(world_map.columns, 100)
        max_viz_y = min(world_map.rows, 100)
        
        for x in range(max_viz_x):
            for y in range(max_viz_y):
                cell = world_map.grid[x][y]
                flat_map.append(cell.to_dict())
                
        await viz_server.send_map_updates(flat_map)

    while True:
        try:
            await asyncio.sleep(interval // 6)
        except asyncio.CancelledError:
            logging.info("[HAZARD] Task cancelled, clearing storm...")
            await clear_storm(world_map)
            raise
        
        logging.info("[HAZARD] Checking for new storm...")
        await clear_storm(world_map)
        logging.info("[HAZARD] Previous storm subsided. Map cells reset.")
        
        if random.random() < STORM_CHANCE: 
            center_x = random.randint(0, world_map.columns - 1)
            center_y = random.randint(0, world_map.rows - 1)
            radius = random.randint(int(0.15 * world_map.columns), int(0.40 * world_map.columns))

            logging.warning(f"[HAZARD] New dust storm forming at ({center_x}, {center_y}) with radius {radius}.")

            for i in range(world_map.columns):
                for j in range(world_map.rows):
                    cell = world_map.get_cell(i, j)
                    dist = ((cell.x - center_x) ** 2 + (cell.y - center_y) ** 2) ** 0.5
                    if dist < radius:
                        world_map.make_dust_cell(i,j)

            flat_map = [] 
            max_viz_x = min(world_map.columns, 100)
            max_viz_y = min(world_map.rows, 100)
            
            for x in range(max_viz_x):
                for y in range(max_viz_y):
                    cell = world_map.grid[x][y]
                    flat_map.append(cell.to_dict())

            print(f"Any cell with dust? {any(cell['dust_storm'] for cell in flat_map)}")
            await viz_server.send_map_updates(flat_map)
            await viz_server.send_hazard_detected("dust_storm", center_x, center_y, radius)
            logging.warning(f"[HAZARD] Map updated.")

            await asyncio.sleep(interval)
        
        else:
            logging.info("[HAZARD] All clear. No new storm detected.")

class VisualizationServer:
    """
    WebSocket server responsible for streaming map data, agent updates,
    logs, and environmental events to the visualization frontend.

    This server manages connected WebSocket clients, broadcasts updates,
    and exposes a command channel for frontend-to-agent communication.
    """
    def __init__(self, world_map: Map = None):
        """Initialize the WebSocket app, routes, state containers, and sync events."""
        self.app = web.Application()
        self.clients = set()
        self.app.router.add_get('/ws', self.websocket_handler)
        self.client_connected = asyncio.Event()

        self.world_map = world_map
        self.map_data = []

        self.number_of_rovers = 0
        self.rovers_energy = defaultdict(lambda: 100.0)

        self.stats = {
            "terrainMapped": 0.0,
            "resourcesFound": {},
            "totalEnergy": 100.0,
            "missionTime": 0,
            "hazards": 0
        }
        
        # Track simulation state
        self.simulation_running = False
        self.simulation_task = None
        self.simulation_paused = False  # ADD THIS
        self.pause_event = asyncio.Event()  # ADD THIS
        self.pause_event.set()  # Initially not paused (set means "go")

    async def websocket_handler(self, request):
        """
        Handle incoming WebSocket connections, process messages, and
        automatically send the full map when a client connects.

        Args:
            request: aiohttp request instance for the WS upgrade.

        Returns:
            WebSocketResponse: active WebSocket channel.
        """
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self.clients.add(ws)
        self.client_connected.set()
        print(f"Client connected. Total clients: {len(self.clients)}")

        # Send initial map if available
        if self.map_data:
            await self.send_full_map(ws)

        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    await self.handle_command(data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    print(f'WebSocket error: {ws.exception()}')
        finally:
            self.clients.discard(ws)
            print(f"Client disconnected. Total clients: {len(self.clients)}")
            if not self.clients:
                self.client_connected.clear()
        return ws

    async def handle_command(self, data: Dict[str, Any]):
        """
        Process incoming commands from the visualization interface.

        Args:
            data (Dict[str, Any]): Parsed JSON payload sent by the frontend.
        """
        print(f"Received command: {data}")

        cmd_type = data.get("type")
        
        if cmd_type == "request_stats_and_map_data":
            await self.send_stats()
            if self.world_map:
                self.initialize_map(self.world_map)
                await self.broadcast({
                    "type": "full_map_init",
                    "map_cells": self.map_data
                })
            return
        elif cmd_type == "start_simulation":
            config_file = data.get("config_file")
            if not config_file:
                await self.send_message("server", "[ERROR] No config_file provided")
                return
            
            if self.simulation_running:
                await self.send_message("server", "[ERROR] Simulation already running")
                return
                
            await self.send_message("server", f"[INFO] Starting simulation with {config_file}...")
            self.simulation_task = asyncio.create_task(self.start_simulation(config_file))

        elif cmd_type == "stop_simulation":
            if self.simulation_running and self.simulation_task:
                self.simulation_task.cancel()
                await self.send_message("server", "[INFO] Simulation stopped by user")
                self.simulation_running = False
            else:
                await self.send_message("server", "[INFO] No simulation is currently running")

        elif cmd_type == "pause_simulation":
            if self.simulation_running:
                self.simulation_paused = True
                self.pause_event.clear()  # Block execution
                await self.send_message("server", "[INFO] Simulation paused")
                await self.broadcast({"type": "simulation_paused"})
            else:
                await self.send_message("server", "[INFO] No simulation is currently running")

        elif cmd_type == "resume_simulation":
            if self.simulation_running and self.simulation_paused:
                self.simulation_paused = False
                self.pause_event.set()  # Resume execution
                await self.send_message("server", "[INFO] Simulation resumed")
                await self.broadcast({"type": "simulation_resumed"})
            else:
                await self.send_message("server", "[INFO] Simulation is not paused")


    async def start_simulation(self, config_path: str):
        """
        Starts the simulation from a config file.
        This is basically your current `main()` function, refactored to run on demand.
        """
        started_agents = []
        hazard_task = None
        
        try:
            self.simulation_running = True
            config = load_config(config_path)

            # --- EXTRACT CONFIG VALUES ---
            sim_config = config.get("simulation", {})
            duration = sim_config.get("duration_seconds", 600)
            tag = sim_config.get("tag", "spade")

            base_configs = config.get("bases", [])
            drone_configs = config.get("drones", [])
            rover_configs = config.get("rovers", [])

            # --- WORLD INITIALIZATION ---
            world, world_map, base_centers, rover_positions, drone_positions = generate_world(config, tag)
            
            # Update server's world_map reference
            self.world_map = world_map
            self.initialize_map(world_map)
            await self.broadcast({
                "type": "full_map_init",
                "map_cells": self.map_data
            })

            # --- SETUP LOGGING ---
            setup_logging(config)

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

                rovers_for_this_base = [
                    rover_jids[r["jid"]] 
                    for r in rover_configs 
                    if r.get("base", base_configs[0].get("name") if base_configs else None) == base_name
                ]
                drones_for_this_base = [drone_jids[d["jid"]] for d in drone_configs]

                base = Base(
                    base_jid,
                    base_name,
                    base_center,
                    rovers_for_this_base,
                    drones_for_this_base,
                    radius=base_config.get("radius", 50),
                    viz_server=self
                )
                bases[base_jid] = base
                agents_to_start.append(base)

            # Create Drones
            drones = {}
            for drone_config, drone_pos in zip(drone_configs, drone_positions):
                drone_jid = drone_jids[drone_config["jid"]]
                known_base_names = drone_config.get("known_bases", [])
                known_base_jids = [base_jids[b] for b in known_base_names if b in base_jids]

                drone = Drone(
                    drone_jid,
                    drone_config.get("name", drone_config["jid"]),
                    world,
                    world_map,
                    drone_pos,
                    known_bases=known_base_jids,
                    scan_radius=drone_config.get("scan_radius", 20.0),
                    viz_server=self
                )
                drones[drone_jid] = drone
                agents_to_start.append(drone)

            # Create Rovers
            rovers = {}
            for rover_config, rover_pos in zip(rover_configs, rover_positions):
                rover_jid = rover_jids[rover_config["jid"]]
                rover_base_name = rover_config.get("base", base_configs[0].get("name") if base_configs else None)
                rover_base_jid = base_jids.get(rover_base_name)

                rover = Rover(
                    rover_jid,
                    rover_config.get("name", rover_config["jid"]),
                    rover_pos,
                    world,
                    world_map,
                    base_jid=rover_base_jid,
                    base_radius=bases[rover_base_jid].radius if rover_base_jid else 50,
                    viz_server=self
                )
                rovers[rover_jid] = rover
                agents_to_start.append(rover)

            # --- START AGENTS ---
            for agent in agents_to_start:
                await agent.start()
                started_agents.append(agent)
            
            await self.send_message("server", "[INFO] All agents started")

            # Start hazards task
            hazard_task = asyncio.create_task(simulate_hazards(world_map, self, interval=10))

            # --- RUN SIMULATION ---
            try:
                start_time = asyncio.get_event_loop().time()
                while asyncio.get_event_loop().time() - start_time < duration:
                    await self.pause_event.wait()  # Wait if paused
                    await asyncio.sleep(1)  # Check every second
            except asyncio.CancelledError:
                logging.info("[SIMULATION] Cancel received, stopping simulation immediately.")
                raise  # propagate so the finally block handles cleanup


            # Normal completion
            await self.send_message("server", "[INFO] Simulation completed.")
            await self.broadcast({"type": "simulation_completed"})
            
        except asyncio.CancelledError:
            # Simulation was stopped/reset
            await self.send_message("server", "[INFO] Simulation stopped")
            await self.broadcast({"type": "simulation_stopped"})
            raise  # Re-raise to properly handle cancellation
            
        except FileNotFoundError as e:
            await self.send_message("server", f"[ERROR] Config file not found: {config_path}")
            await self.broadcast({"type": "error", "message": f"Config file not found: {config_path}"})
        except Exception as e:
            logging.exception("Error during simulation")
            await self.send_message("server", f"[ERROR] Simulation failed: {str(e)}")
            await self.broadcast({"type": "error", "message": str(e)})
        finally:
            # CLEANUP - Always stop agents and hazard task
            if hazard_task:
                hazard_task.cancel()
                try:
                    await hazard_task
                except asyncio.CancelledError:
                    pass
                    
            for agent in started_agents:
                try:
                    await agent.stop()
                except Exception as e:
                    logging.error(f"Error stopping agent: {e}")
            
            self.simulation_running = False
            self.simulation_paused = False
            self.pause_event.set()  # Reset pause state
            await self.send_message("server", "[INFO] All agents stopped. Ready for new simulation.")

    async def broadcast(self, message: Dict[str, Any]):
        """
        Broadcast a JSON-serializable message to all connected clients.

        Args:
            message (Dict[str, Any]): The message dictionary to send.
        """
        if not self.clients:
            return

        await asyncio.gather(
            *[client.send_json(message) for client in self.clients],
            return_exceptions=True
        )

    async def send_stats(self) -> None:
        """Send current statistics to all clients."""
        if not self.clients:
            return

        message = {
            "type": "stats",
            "stats": self.stats
        }
        await asyncio.gather(
            *[client.send_json(message) for client in self.clients],
            return_exceptions=True
        )
            
    async def start_server(self, host: str = '0.0.0.0', port: int = 8080):
        """
        Start the aiohttp WebSocket server.

        Args:
            host (str): Host to bind.
            port (int): Port to bind.

        Returns:
            AppRunner: server runner handle.
        """
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        print(f"WebSocket server started on ws://{host}:{port}/ws")
        return runner

    async def wait_for_client(self, timeout=None):
        """
        Block until a client connects or a timeout expires.

        Args:
            timeout (float | None): Optional timeout duration.

        Returns:
            bool: True if a client connected, False if timed out.
        """
        try:
            await asyncio.wait_for(self.client_connected.wait(), timeout=timeout)
            print("[WEBSOCKET] Client connection established")
            return True
        except asyncio.TimeoutError:
            print("[WEBSOCKET] Timeout waiting for client connection")
            return False

    def initialize_map(self, world_map: Map):
        """
        Convert the map grid into a flat list of serializable dicts and
        cache them for streaming to visualization clients.

        Args:
            world_map (Map): Simulation world map.
        """
        flat_map = []
        max_viz_x = min(world_map.columns, 100)
        max_viz_y = min(world_map.rows, 100)

        for x in range(max_viz_x):
            for y in range(max_viz_y):
                cell = world_map.grid[x][y]
                flat_map.append(cell.to_dict())

        self.map_data = flat_map
        print(f"Server map data initialized from simulation world: {len(flat_map)} cells.")

    async def send_full_map(self, ws):
        """
        Send the full map snapshot to a specific WebSocket client.

        Args:
            ws: WebSocketResponse instance.
        """
        await ws.send_json({
            "type": "full_map_init",
            "map_cells": self.map_data
        })

    async def send_map_cell_data(self, x, y, terrain, dust_storm=False):
        """Broadcast a single cell update."""
        await self.broadcast({
            "type": "map_cell_update",
            "cell": {
                "x": int(x),
                "y": int(y),
                "terrain": float(terrain),
                "dust_storm": dust_storm
            }
        })

    async def send_map_updates(self, map_data):
        """
        Broadcast a bulk map update (terrain or dust storm changes).

        Args:
            map_data (list): Updated cell list.
        """
        self.map_data = map_data
        await self.broadcast({
            "type": "update_map",
            "map_cells": map_data
        })

    async def send_agent_update(self, agent_id: str, agent_type: str, x: float, y: float, battery: float, status: str, color: Optional[str], radius: int):
        """Broadcast agent state information to all clients."""
        self.rovers_energy[agent_id] = battery
        self.stats["totalEnergy"] = sum(value for _, value in self.rovers_energy.items()) / len(self.rovers_energy)

        await self.broadcast({
            "type": "agent_update",
            "agent": {
                "id": agent_id,
                "type": agent_type,
                "x": x,
                "y": y,
                "battery": battery,
                "status": status,
                "color": color,
                "radius": radius
            }
        })
        await self.send_stats()

    async def send_resource_discovered(self, resource_id: str, x: float, y: float):
        """Notify clients of a newly discovered resource."""
        if resource_id not in self.stats["resourcesFound"].keys():
            self.stats["resourcesFound"][resource_id] = 1
        else:
            self.stats["resourcesFound"][resource_id] += 1

        await self.broadcast({
            "type": "resource_discovered",
            "resource": {
                "id": resource_id,
                "x": x,
                "y": y
            }
        })
        await self.send_stats()

    async def send_hazard_detected(self, hazard_id: str, x: float, y: float, radius: float):
        """Notify clients of a detected hazard."""
        await self.broadcast({
            "type": "hazard_detected",
            "hazard": {
                "id": hazard_id,
                "x": x,
                "y": y,
                "radius": radius
            }
        })
        self.stats["hazards"] += 1
        await self.send_stats()

    async def send_cell_explored(self, x: float, y: float):
        """Mark a grid cell as explored in visualization."""
        self.stats["terrainMapped"] += 1 / (self.world_map.rows * self.world_map.columns)
        await self.broadcast({
            "type": "cell_explored",
            "x": x,
            "y": y
        })
        await self.send_stats()

    async def send_message(self, sender: str, content: str):
        """Send a log/communication message to all visualization clients."""
        await self.broadcast({
            "type": "log_message",
            "sender": sender,
            "content": content
        })
