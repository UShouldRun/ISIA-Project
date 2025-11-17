import asyncio
import json
from aiohttp import web
import aiohttp
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour

# WebSocket Server for Visualization
class VisualizationServer:
    def __init__(self):
        self.app = web.Application()
        self.clients = set()

        # WebSocket route
        self.app.router.add_get('/ws', self.websocket_handler)
        
    async def websocket_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self.clients.add(ws)
        
        print(f"Client connected. Total clients: {len(self.clients)}")
        
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
        
        return ws
    
    async def handle_command(self, data):
        """Handle commands from the visualization interface"""
        print(f"Received command: {data}")
        # You can forward commands to specific agents here
        # This would integrate with your SPADE agent system
        
    async def broadcast(self, message):
        if not self.clients:
            print(f"No Client found")
            return

        """Send message to all connected clients"""
        await asyncio.gather(
            *[client.send_json(message) for client in self.clients],
            return_exceptions=True
        )
    
    async def start_server(self, host='0.0.0.0', port=8080):
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        print(f"WebSocket server started on ws://{host}:{port}/ws")
        return runner

    # -------------------------------------------------------------
    # HIGH-LEVEL MESSAGE HELPERS (CALLED BY MIXIN)
    # -------------------------------------------------------------
    async def send_agent_update(self, agent_id, agent_type, x, y, battery, status, color):
        await self.broadcast({
            "type": "agent_update",
            "agent": {
                "id": agent_id,
                "type": agent_type,
                "x": x,
                "y": y,
                "battery": battery,
                "status": status,
                "color": color
            }
        })

    async def send_resource_discovered(self, resource_id, resource_type, x, y):
        await self.broadcast({
            "type": "resource_discovered",
            "resource": {
                "id": resource_id,
                "type": resource_type,
                "x": x,
                "y": y
            }
        })

    async def send_hazard_detected(self, hazard_id, hazard_type, x, y, radius):
        await self.broadcast({
            "type": "hazard_detected",
            "hazard": {
                "id": hazard_id,
                "type": hazard_type,
                "x": x,
                "y": y,
                "radius": radius
            }
        })

    async def send_cell_explored(self, x, y):
        await self.broadcast({
            "type": "cell_explored",
            "x": x,
            "y": y
        })

    async def send_message(self, sender, content):
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
    
    def setup_visualization(self, viz_server, agent_type='rover', color=None):
        """
        Setup visualization for this agent
        
        Args:
            viz_server: VisualizationServer instance
            agent_type: Type of agent ('rover', 'drone', 'satellite', 'base')
            color: Optional custom color for the agent
        """
        self.viz_server = viz_server
        self.viz_agent_type = agent_type
        self.viz_color = color

        self.viz_position = [0, 0]
        self.viz_battery = 100
        self.viz_status = "initializing"
    
    async def viz_update_position(self, x, y):
        """Update agent position in visualization"""
        self.viz_position = [float(x), float(y)]
        await self.viz_send_update()
    
    async def viz_update_battery(self, battery):
        """Update agent battery level"""
        self.viz_battery = float(battery)
        await self.viz_send_update()
    
    async def viz_update_status(self, status):
        """Update agent status"""
        self.viz_status = status
        await self.viz_send_update()
    
    async def viz_send_update(self):
        """Send complete agent update to visualization"""
        if hasattr(self, 'viz_server') and self.viz_server:
            await self.viz_server.send_agent_update(
                agent_id=self.name.split("@")[0],
                agent_type=self.viz_agent_type,
                x=self.viz_position[0],
                y=self.viz_position[1],
                battery=self.viz_battery,
                status=self.viz_status,
                color=self.viz_color
            )
    
    async def viz_report_resource(self, resource_id, resource_type, x, y):
        """Report resource discovery"""
        if hasattr(self, 'viz_server') and self.viz_server:
            await self.viz_server.send_resource_discovered(
                resource_id=resource_id,
                resource_type=resource_type,
                x=float(x),
                y=float(y)
            )
            await self.viz_server.send_message(
                sender=self.name.split("@")[0],
                content=f"Discovered {resource_type} at ({x:.1f}, {y:.1f})"
            )
    
    async def viz_report_hazard(self, hazard_id, hazard_type, x, y, radius=5):
        """Report hazard detection"""
        if hasattr(self, 'viz_server') and self.viz_server:
            await self.viz_server.send_hazard_detected(
                hazard_id=hazard_id,
                hazard_type=hazard_type,
                x=float(x),
                y=float(y),
                radius=float(radius)
            )
            await self.viz_server.send_message(
                sender=self.name.split("@")[0],
                content=f"Hazard detected: {hazard_type} at ({x:.1f}, {y:.1f})"
            )
    
    async def viz_mark_explored(self, x, y):
        """Mark a cell as explored"""
        if hasattr(self, 'viz_server') and self.viz_server:
            await self.viz_server.send_cell_explored(int(x), int(y))
    
    async def viz_send_message(self, content):
        """Send a message to the communication log"""
        if hasattr(self, 'viz_server') and self.viz_server:
            await self.viz_server.send_message(
                sender=self.name.split("@")[0],
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