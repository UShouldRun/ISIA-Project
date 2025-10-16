import spade
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, CyclicBehaviour
from spade.message import Message
from spade.template import Template

class Drone(Agent):
    class MapTerrain(CyclicBehaviour): # Is this a cyclic behaviour
        async def on_start(self, location_start, location_end):
            """Path finding"""
            pass

        async def run(self):
            """Moves to goal location"""
            pass

        async def on_end(self):
            """Stops to analyze"""
            pass

    class Analyze(CyclicBehaviour):
        def run(self, world_data, agents_msg):
            return

    class Communicate(OneShotBehaviour):
        def decide_receiver(self, data, agents):
            return

        def create_message_body(data):
            return

        async def send_msg(self, data, agents):
            receiver = self.decide_receiver(data, agents)
            msg = Message(to = receiver).set_metadata("performative", "inform")
            msg.body = self.create_message_body(data)

            await self.send(msg)

        async def run(self, world_data, agents, timeout):
            agents_msg = await self.receive(timeout = timeout)
            self.send(await self.analyze(world_data, agents_msg), agents)

    async def setup(self):
        self.add_behaviour(self.Communicate(), Template().set_metadata("performative", "inform"))
        self.add_behaviour(self.Analyze())
        self.add_behaviour(self.MapTerrain())
