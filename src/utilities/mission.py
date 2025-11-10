from enum import Enum

import asyncio
import random

class MissionType(Enum):
    ROVER_COLLECT_SAMPLES = 1
    DRONE_SCAN_AREA = 2
    AVOID_DANGER = 3
    TOW_CRASHED_AGENT = 4

class Mission():
    def __init__(self, missionType: MissionType, agentType: int, goal: tuple, nearestBase: tuple, expectedEnergyUsage: int):
        super().__init__()
        self.type = missionType
        self.agentType = agentType
        self.goal = goal
        self.nearestBase = nearestBase
        self.expectedEnergyUsage = expectedEnergyUsage
