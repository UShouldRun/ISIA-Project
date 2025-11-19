import random
import asyncio
import spade
import logging
import json
import sys
from typing import Tuple, List, Dict, Any

from world.world import World, WorldObject
from world.map import Map
from agents.base import Base
from agents.drone import Drone
from agents.rover import Rover
from server import VisualizationServer, setup_logging, load_config, generate_world, random_pos_in_base, simulate_hazards

from settings import *

async def main():
    """
    Main entry point for the multi-agent system simulation.
    
    This version ONLY starts the visualization server and waits indefinitely.
    The simulation is started on-demand via WebSocket commands from the frontend.
    """
    print("[MAIN] Multi-Agent System Visualization Server")
    print("[MAIN] Starting WebSocket server...")
    
    # --- CREATE VISUALIZATION SERVER (without world_map initially) ---
    viz_server = VisualizationServer()
    runner = await viz_server.start_server()

    print("[MAIN] Visualization server READY on ws://localhost:8080/ws")
    print("[MAIN] Waiting for client connection and simulation commands...")
    print("[MAIN] Use the web interface to start a simulation with a config file.")
    
    # Keep the server running indefinitely
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n[MAIN] Shutting down server...")
        await runner.cleanup()
        print("[MAIN] Server stopped.")

if __name__ == "__main__":
    """
    Run the visualization server that can start simulations on demand.
    """
    spade.run(main())
