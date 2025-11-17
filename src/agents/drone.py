import spade

from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, CyclicBehaviour
from spade.message import Message
from spade.template import Template

from world.map import Map
from world.world import World
from visualization_mixin import VisualizationMixin, VisualizationBehaviour

<<<<<<< Updated upstream
class Drone(Agent):
    class MapTerrain(CyclicBehaviour): # Is this a cyclic behaviour?
        def a_star(self, map: Map, goal: Tuple[int, int]):
            pass
=======
class Drone(VisualizationMixin, Agent):
    def __init__(
        self,
        jid: str,
        password: str,
        world: World,
        map: Map,
        base_position: Tuple[float, float],
        assigned_rover: str,
        move_step: float = 10.0,
        energy_consump_rate: float = 0.5,
        viz_server=None
    ) -> None:
        super().__init__(jid, password)
        self.world = world
        self.map = map
        self.position = base_position
        self.base_position = base_position
        self.assigned_rover = assigned_rover
        self.move_step = move_step
        self.energy_consump_rate = energy_consump_rate
        if viz_server:
            self.setup_visualization(
                viz_server=viz_server,
                agent_type='drone',
                color='#3b82f6'
            )
>>>>>>> Stashed changes

        async def on_start(self, map: Map, world: World):
            """Initial Scan"""
            map.add(world.objects)
 
        async def run(self, map: Map, goal: Tuple[int, int]):
            """Moves to goal location"""
           return self.a_star(map, goal)

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
<<<<<<< Updated upstream
        self.add_behaviour(self.Communicate(), Template().set_metadata("performative", "inform"))
        self.add_behaviour(self.Analyze())
        self.add_behaviour(self.MapTerrain())
=======
        print(f"[{self.name}] Drone initialized at {self.position}, waiting for missions.")
        if hasattr(self, 'viz_server'):
            viz_behaviour = VisualizationBehaviour(update_interval=0.1)
            self.add_behaviour(viz_behaviour)
        self.add_behaviour(self.DroneControl())
>>>>>>> Stashed changes
