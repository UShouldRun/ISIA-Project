import spade
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, CyclicBehaviour

class Rover(Agent):
    class ExploreTerrain(CyclicBehaviour): # Is this a cyclic behaviour
        async def on_start(self, location_start, location_end):
            """Path finding"""
            pass

        async def run(self):
            """Moves to goal location"""
            pass

        async def on_end(self):
            """Stops to analyze"""
            pass

    class AnalyzeSoil(OneShotBehaviour): # Is this an one shot behaviour
        async def run(self):
            pass

    class DetectResources(CyclicBehaviour):
        async def run(self):
            pass

    class Communicate(OneShotBehaviour):
        async def run(self):
            print("Hi")

    async def setup(self):
        self.add_behaviour(self.Communicate())
        self.add_behaviour(self.ExploreTerrain())
        self.add_behaviour(self.AnalyzeSoil())
        self.add_behaviour(self.DetectResources())
