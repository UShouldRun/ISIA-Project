import asyncio
import spade

from satellite import Satellite
from base import Base
from rover import Rover
from drone import Drone

async def main():
    print("\nStarting multi-agent planetary exploration simulation...\n")

    satellite = Satellite("satellite@localhost", "satellite_pass")
    base = Base("base@localhost", "base_pass", position=(0, 0))
    rover1 = Rover("rover1@localhost", "rover1_pass", position=(0, 0), base_position=(0, 0))
    drone1 = Drone("drone1@localhost", "drone1_pass", position=(5, 5), base_position=(0, 0))

    await satellite.start(auto_register=True)
    await base.start(auto_register=True)
    await rover1.start(auto_register=True)
    await drone1.start(auto_register=True)

    print("All agents started. Simulation running...\n")

    await asyncio.sleep(60)

    print("\nSimulation complete — stopping agents...\n")

    await drone1.stop()
    await rover1.stop()
    await base.stop()
    await satellite.stop()

    print("All agents stopped successfully.")

if __name__ == "__main__":
    spade.run(main())
