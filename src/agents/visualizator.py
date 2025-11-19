import asyncio

from typing import Tuple, List, Optional, Dict, Any

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour

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
