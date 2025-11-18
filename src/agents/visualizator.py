import asyncio
import json
import aiohttp

from typing import Tuple, List, Optional, Dict, Any

from aiohttp import web

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour

from world.map import Map

# WebSocket Server for Visualization
class VisualizationServer:
    def __init__(self):
        self.app = web.Application()
        self.clients = set()

        # WebSocket route
        self.app.router.add_get('/ws', self.websocket_handler)
        self.client_connected = asyncio.Event()  # Event to signal connection
        self.map_data = []

    async def websocket_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self.clients.add(ws)
        self.client_connected.set()  # Signal that client is connected
        
        print(f"Client connected. Total clients: {len(self.clients)}")
        
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
            self.client_connected.clear()
        
        return ws
    
    async def handle_command(self, data: str):
        """Handle commands from the visualization interface"""
        print(f"Received command: {data}")
        # You can forward commands to specific agents here
        # This would integrate with your SPADE agent system
        
    async def broadcast(self, message: str):
        if not self.clients:
            print(f"No Client found")
            return

        """Send message to all connected clients"""
        await asyncio.gather(
            *[client.send_json(message) for client in self.clients],
            return_exceptions=True
        )
    
    async def start_server(self, host: str = '0.0.0.0', port: int = 8080):
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        print(f"WebSocket server started on ws://{host}:{port}/ws")
        return runner

    async def wait_for_client(self, timeout=None):
        """Wait for a client to connect to the WebSocket."""
        try:
            await asyncio.wait_for(self.client_connected.wait(), timeout=timeout)
            print("[WEBSOCKET] Client connection established")
            return True
        except asyncio.TimeoutError:
            print("[WEBSOCKET] Timeout waiting for client connection")
            return False

    # -------------------------------------------------------------
    # HIGH-LEVEL MESSAGE HELPERS (CALLED BY MIXIN)
    # -------------------------------------------------------------
    def initialize_map(self, planet_map: Map):
        """
        Receives the actual Map object from the main world generation and
        prepares the flat list format for the visualization client.
        """
        flat_map = []
        
        # Scaling factor: assuming your map is 1000x1000 and visualization is 100x100
        # If the map size is the same (100x100), factor is 1.
        scale_factor = planet_map.columns / 100 

        # Only iterate over the first 100x100 cells for the fixed visualization view
        max_viz_x = min(planet_map.columns, 100)
        max_viz_y = min(planet_map.rows, 100)
        
        # Iterate over the grid (columns, then rows) and flatten it
        for x in range(max_viz_x):
            for y in range(max_viz_y):
                # Use the cell from the simulation's map
                cell = planet_map.grid[x][y]
                # Scale coordinates if necessary, but for a 100x100 view, we often use the base index
                
                # To scale down coordinates if the map is >100x100:
                # If your map is 1000x1000, we'd need to sample and map x/y values differently.
                # For simplicity, we assume the simulation map is 100x100 and use indices 0-99.
                
                # If your map is larger, you might average or pick the top-left cell for a 10:1 reduction.
                
                # For now, let's assume the Map is 100x100 and use its data directly.
                cell_dict = cell.to_dict()
                flat_map.append(cell_dict)
                
        self.map_data = flat_map
        self.map_initialized = True
        print(f"Server map data initialized from simulation world: {len(flat_map)} cells.")

    async def send_full_map(self, ws):
        """Send the entire pre-generated map data to a specific client"""
        # The map data is a list of dictionaries, one for each cell
        message = {
            "type": "full_map_init",
            "map_cells": self.map_data
        }
        await ws.send_json(message)

    async def send_map_cell_data(self, x, y, terrain, dust_storm=False):
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
        Handles bulk updates of cell properties (like dust_storm status).
        """
        print("HERE")
        self.map_data = map_data
        await self.broadcast({
            "type": "update_map",
            "map_cells": map_data
        })

    async def send_agent_update(self, agent_id: str, agent_type: str, x: float, y: float, battery: float, status: str, color: Optional[str], radius: int):
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

    async def send_resource_discovered(self, resource_id: str, x: float, y: float):
        await self.broadcast({
            "type": "resource_discovered",
            "resource": {
                "id": resource_id,
                "x": x,
                "y": y
            }
        })

    async def send_hazard_detected(self, hazard_id: str, x: float, y: float, radius: float):
        await self.broadcast({
            "type": "hazard_detected",
            "hazard": {
                "id": hazard_id,
                "x": x,
                "y": y,
                "radius": radius
            }
        })

    async def send_cell_explored(self, x: float, y: float):
        await self.broadcast({
            "type": "cell_explored",
            "x": x,
            "y": y
        })

    async def send_message(self, sender: str, content: str):
        await self.broadcast({
            "type": "log_message",
            "sender": sender,
            "content": content
        })

class VisualizationMixin:
    """
    Mixin class that adds visualization capabilities to SPADE agents.
    
    Usage:
        class YourAgent(VisualizationMixin, Agent):
            def __init__(self, jid, password, viz_server):
                super().__init__(jid, password)
                self.setup_visualization(viz_server, agent_type='rover')
    """
    
    def setup_visualization(
        self,
        viz_server,
        agent_type: str,
        agent_jid: str,
        position: Tuple[float, float],
        battery: float = 100.0,
        color: Optional[str] = None,
        radius: int = 5
    ):
        """
        Setup visualization for this agent
        
        Args:
            viz_server: VisualizationServer instance
            agent_type: Type of agent ('rover', 'drone', 'satellite', 'base')
            color: Optional custom color for the agent
        """
        self.viz_server = viz_server

        self.agent_jid = agent_jid
        self.viz_agent_type = agent_type
        self.viz_color = color
        self.viz_radius = radius

        self.viz_position = position
        self.viz_battery = battery
        self.viz_status = "initializing"
    
    async def viz_update_position(self, pos: Tuple[float, float]):
        """Update agent position in visualization"""
        self.viz_position = (float(pos[0]), float(pos[1]))
    
    async def viz_update_battery(self, battery: float = 100.0):
        """Update agent battery level"""
        self.viz_battery = float(battery)
    
    async def viz_update_status(self, status: str):
        """Update agent status"""
        self.viz_status = status
    
    async def viz_send_update(self):
        """Send complete agent update to visualization"""
        if hasattr(self, 'viz_server') and self.viz_server:
            await self.viz_server.send_agent_update(
                agent_id=self.agent_jid.split("@")[0],
                agent_type=self.viz_agent_type,
                x=self.viz_position[0],
                y=self.viz_position[1],
                battery=self.viz_battery,
                status=self.viz_status,
                color=self.viz_color,
                radius=self.viz_radius
            )
    
    async def viz_report_resource(self, resource_id: str, x: float, y: float):
        """Report resource discovery"""
        if hasattr(self, 'viz_server') and self.viz_server:
            await self.viz_server.send_resource_discovered(
                resource_id=resource_id,
                x=float(x),
                y=float(y)
            )
            await self.viz_server.send_message(
                sender=self.agent_jid.split("@")[0],
                content=f"Discovered {resource_id} at ({x:.1f}, {y:.1f})"
            )
    
    async def viz_report_hazard(self, hazard_id: str, x: float, y: float, radius: float = 5):
        """Report hazard detection"""
        if hasattr(self, 'viz_server') and self.viz_server:
            await self.viz_server.send_hazard_detected(
                hazard_id=hazard_id,
                x=float(x),
                y=float(y),
                radius=float(radius)
            )
            await self.viz_server.send_message(
                sender=self.agent_jid.split("@")[0],
                content=f"Hazard detected: {hazard_id} at ({x:.1f}, {y:.1f})"
            )
    
    async def viz_mark_explored(self, x: float, y: float):
        """Mark a cell as explored"""
        if hasattr(self, 'viz_server') and self.viz_server:
            await self.viz_server.send_cell_explored(int(x), int(y))
    
    async def viz_send_message(self, content: str):
        """Send a message to the communication log"""
        if hasattr(self, 'viz_server') and self.viz_server:
            await self.viz_server.send_message(
                sender=self.agent_jid.split("@")[0],
                content=content
            )

# SPADE Agent with Visualization Integration
class VisualizationBehaviour(CyclicBehaviour):
    """Behaviour that sends agent state to visualization"""
    
    async def run(self):
        # Send agent update to visualization
        if hasattr(self.agent, 'viz_server'):
            await self.agent.viz_send_update()  # Let mixin handle it!
        
        await asyncio.sleep(0.1)  # Update frequency
