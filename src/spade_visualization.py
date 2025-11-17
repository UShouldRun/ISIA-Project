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
        """Send message to all connected clients"""
        if self.clients:
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


# SPADE Agent with Visualization Integration
class VisualizationBehaviour(CyclicBehaviour):
    """Behaviour that sends agent state to visualization"""
    
    async def run(self):
        # Send agent update to visualization
        if hasattr(self.agent, 'viz_server'):
            await self.agent.viz_server.broadcast({
                "type": "agent_update",
                "agent": {
                    "id": self.agent.name.split("@")[0],
                    "type": self.agent.agent_type,
                    "x": self.agent.position[0],
                    "y": self.agent.position[1],
                    "battery": self.agent.battery,
                    "status": self.agent.status,
                    "color": self.agent.color
                }
            })
        
        await asyncio.sleep(0.1)  # Update frequency


class RoverAgent(Agent):
    def __init__(self, jid, password, viz_server=None):
        super().__init__(jid, password)
        self.viz_server = viz_server
        self.agent_type = "rover"
        self.position = [5, 5]
        self.battery = 100
        self.status = "exploring"
        self.color = "#3b82f6"
        
    async def setup(self):
        print(f"Rover agent {self.name} starting...")
        
        # Add visualization behaviour
        viz_behaviour = VisualizationBehaviour()
        self.add_behaviour(viz_behaviour)
        
        # Add your exploration behaviour
        exploration_behaviour = RoverExplorationBehaviour()
        self.add_behaviour(exploration_behaviour)


class RoverExplorationBehaviour(CyclicBehaviour):
    """Main exploration logic for rover"""
    
    async def run(self):
        # Your exploration logic here
        import random
        
        # Simple random movement
        if random.random() > 0.5:
            dx = random.choice([-1, 1])
            self.agent.position[0] = max(0, min(49, self.agent.position[0] + dx))
        else:
            dy = random.choice([-1, 1])
            self.agent.position[1] = max(0, min(49, self.agent.position[1] + dy))
        
        # Consume battery
        self.agent.battery = max(0, self.agent.battery - 0.1)
        
        # Mark cell as explored
        if self.agent.viz_server:
            await self.agent.viz_server.broadcast({
                "type": "cell_explored",
                "x": int(self.agent.position[0]),
                "y": int(self.agent.position[1])
            })
        
        # Check for resources (example)
        if random.random() > 0.99:  # 1% chance
            await self.discover_resource()
        
        await asyncio.sleep(0.1)
    
    async def discover_resource(self):
        """Report resource discovery"""
        import random
        resource = {
            "type": "resource_discovered",
            "resource": {
                "id": f"r_{int(self.agent.position[0])}_{int(self.agent.position[1])}",
                "type": random.choice(["water", "mineral"]),
                "x": int(self.agent.position[0]),
                "y": int(self.agent.position[1]),
                "discovered": True
            }
        }
        
        if self.agent.viz_server:
            await self.agent.viz_server.broadcast(resource)
            
            # Send message to log
            await self.agent.viz_server.broadcast({
                "type": "message",
                "from": self.agent.name.split("@")[0],
                "content": f"Discovered {resource['resource']['type']} at ({resource['resource']['x']}, {resource['resource']['y']})"
            })


class DroneAgent(Agent):
    def __init__(self, jid, password, viz_server=None):
        super().__init__(jid, password)
        self.viz_server = viz_server
        self.agent_type = "drone"
        self.position = [25, 25]
        self.battery = 100
        self.status = "scouting"
        self.color = "#f59e0b"
        
    async def setup(self):
        print(f"Drone agent {self.name} starting...")
        viz_behaviour = VisualizationBehaviour()
        self.add_behaviour(viz_behaviour)
        
        scout_behaviour = DroneScoutBehaviour()
        self.add_behaviour(scout_behaviour)


class DroneScoutBehaviour(CyclicBehaviour):
    """Scouting behaviour for drone"""
    
    async def run(self):
        import random
        
        # Drones move faster and cover more ground
        self.agent.position[0] = max(0, min(49, self.agent.position[0] + random.randint(-2, 2)))
        self.agent.position[1] = max(0, min(49, self.agent.position[1] + random.randint(-2, 2)))
        
        # Drones consume battery faster
        self.agent.battery = max(0, self.agent.battery - 0.2)
        
        # Mark larger exploration radius
        if self.agent.viz_server:
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    x = int(self.agent.position[0] + dx)
                    y = int(self.agent.position[1] + dy)
                    if 0 <= x < 50 and 0 <= y < 50:
                        await self.agent.viz_server.broadcast({
                            "type": "cell_explored",
                            "x": x,
                            "y": y
                        })
        
        await asyncio.sleep(0.1)


class BaseStationAgent(Agent):
    def __init__(self, jid, password, viz_server=None):
        super().__init__(jid, password)
        self.viz_server = viz_server
        self.agent_type = "base"
        self.position = [25, 5]
        self.battery = 100
        self.status = "active"
        self.color = "#8b5cf6"
        
    async def setup(self):
        print(f"Base station agent {self.name} starting...")
        viz_behaviour = VisualizationBehaviour()
        self.add_behaviour(viz_behaviour)


# Main execution
async def main():
    # Create visualization server
    viz_server = VisualizationServer()
    runner = await viz_server.start_server()
    
    # Create SPADE agents with visualization
    rover1 = RoverAgent("rover1@localhost", "password", viz_server)
    rover2 = RoverAgent("rover2@localhost", "password", viz_server)
    rover2.position = [45, 5]
    rover2.color = "#10b981"
    
    drone1 = DroneAgent("drone1@localhost", "password", viz_server)
    
    base1 = BaseStationAgent("base1@localhost", "password", viz_server)
    
    # Start all agents
    await rover1.start()
    await rover2.start()
    await drone1.start()
    await base1.start()
    
    print("All agents started. Visualization available at http://localhost:8080/ws")
    print("Press Ctrl+C to stop...")
    
    try:
        # Keep running
        while True:
            await asyncio.sleep(1)
            
            # Update stats periodically
            stats = {
                "type": "stats",
                "stats": {
                    "terrainMapped": 0,  # Calculate from explored cells
                    "resourcesFound": 0,  # Track resources
                    "totalEnergy": (rover1.battery + rover2.battery + drone1.battery) / 3,
                    "missionTime": 0  # Track mission time
                }
            }
            await viz_server.broadcast(stats)
            
    except KeyboardInterrupt:
        print("\nStopping agents...")
        await rover1.stop()
        await rover2.stop()
        await drone1.stop()
        await base1.stop()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())