import asyncio
import json
import aiohttp

from typing import Tuple, List, Optional, Dict, Any

from aiohttp import web

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour

from world.map import Map

class VisualizationServer:
    """
    WebSocket server responsible for streaming map data, agent updates,
    logs, and environmental events to the visualization frontend.

    This server manages connected WebSocket clients, broadcasts updates,
    and exposes a command channel for frontend-to-agent communication.
    """
    def __init__(self):
        """Initialize the WebSocket app, routes, state containers, and sync events."""
        self.app = web.Application()
        self.clients = set()
        self.app.router.add_get('/ws', self.websocket_handler)
        self.client_connected = asyncio.Event()
        self.map_data = []

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
        """
        Process incoming commands from the visualization interface.

        Args:
            data (str): Parsed JSON payload sent by the frontend.
        """
        print(f"Received command: {data}")

    async def broadcast(self, message: str):
        """
        Broadcast a JSON-serializable message to all connected clients.

        Args:
            message (str): The JSON message to send.
        """
        if not self.clients:
            print("No Client found")
            return

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
        self.map_initialized = True
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
        """Notify clients of a newly discovered resource."""
        await self.broadcast({
            "type": "resource_discovered",
            "resource": {
                "id": resource_id,
                "x": x,
                "y": y
            }
        })

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

    async def send_cell_explored(self, x: float, y: float):
        """Mark a grid cell as explored in visualization."""
        await self.broadcast({
            "type": "cell_explored",
            "x": x,
            "y": y
        })

    async def send_message(self, sender: str, content: str):
        """Send a log/communication message to all visualization clients."""
        await self.broadcast({
            "type": "log_message",
            "sender": sender,
            "content": content
        })

class VisualizationMixin:
    """
    Mixin adding visualization capabilities to SPADE agents.

    Stores tracked attributes (position, battery, status, etc.) and provides
    helper methods to send structured updates to the visualization server.
    """
    def setup_visualization(self, viz_server, agent_type: str, agent_jid: str, position: Tuple[float, float], battery: float = 100.0, color: Optional[str] = None, radius: int = 5):
        """
        Initialize visualization properties for the agent.

        Args:
            viz_server (VisualizationServer): The visualization backend.
            agent_type (str): Category of agent ('rover', 'drone', etc.).
            agent_jid (str): Agent identifier.
            position (Tuple[float, float]): Initial coordinates.
            battery (float): Initial battery level.
            color (str | None): Custom color.
            radius (int): Rendering radius.
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
        """Update agent position in visualization."""
        self.viz_position = (float(pos[0]), float(pos[1]))

    async def viz_update_battery(self, battery: float = 100.0):
        """Update agent battery level."""
        self.viz_battery = float(battery)

    async def viz_update_status(self, status: str):
        """Update agent status string."""
        self.viz_status = status

    async def viz_send_update(self):
        """Push the agent's complete state update to the server."""
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
        """Report a discovered resource to the visualization layer."""
        if hasattr(self, 'viz_server') and self.viz_server:
            await self.viz_server.send_resource_discovered(resource_id, float(x), float(y))
            await self.viz_server.send_message(
                sender=self.agent_jid.split("@")[0],
                content=f"Discovered {resource_id} at ({x:.1f}, {y:.1f})"
            )

    async def viz_report_hazard(self, hazard_id: str, x: float, y: float, radius: float = 5):
        """Report a detected hazard at a location."""
        if hasattr(self, 'viz_server') and self.viz_server:
            await self.viz_server.send_hazard_detected(hazard_id, float(x), float(y), float(radius))
            await self.viz_server.send_message(
                sender=self.agent_jid.split("@")[0],
                content=f"Hazard detected: {hazard_id} at ({x:.1f}, {y:.1f})"
            )

    async def viz_mark_explored(self, x: float, y: float):
        """Mark a cell as explored visually."""
        if hasattr(self, 'viz_server') and self.viz_server:
            await self.viz_server.send_cell_explored(int(x), int(y))

    async def viz_send_message(self, content: str):
        """Send a log message to visualization."""
        if hasattr(self, 'viz_server') and self.viz_server:
            await self.viz_server.send_message(
                sender=self.agent_jid.split("@")[0],
                content=content
            )

class VisualizationBehaviour(CyclicBehaviour):
    """Behaviour that periodically sends visualization updates."""

    async def run(self):
        if hasattr(self.agent, 'viz_server'):
            await self.agent.viz_send_update()
        await asyncio.sleep(0.1)
