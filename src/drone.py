import spade
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour

class Drone(Agent):
    class Communicate(OneShotBehaviour):
        async def run(self):
            print("Hi")

    async def setup(self):
        self.add_behaviour(self.Communicate())
