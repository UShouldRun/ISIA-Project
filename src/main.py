from os import environ

from drone import Drone
# from rover import Rover

import spade

async def main() -> None:
    drone1 = Drone("drone1@localhost", "drone1")
    await drone1.start()

if __name__ == "__main__":
    spade.run(main())
