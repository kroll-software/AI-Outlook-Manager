# core/setup.py

from typing import List
from agents import Agent, handoff
from core.utils import *
from config import *
from myagents import *

_agents : List[BaseAgent] = []
_manager : BaseAgent = None

def get_manager():
    return _manager

def create_agents():
    global _manager

    _agents.clear()

    _manager = ManagerAgent()
    _agents.append(_manager)
    
    _agents.append(OutlookEmailAgent())
    _agents.append(OutlookEventsAgent()) 
    _agents.append(OutlookContactsAgent())
    _agents.append(OutlookTasksAgent())
    _agents.append(DistributionListsAgent())
    _agents.append(CreativeWriterAgent())
    _agents.append(MathAgent())    
    _agents.append(WebAgent())    
    _agents.append(FileManagerAgent())

    #_agents.append(MemoryTestAgent())
    
    for agent in _agents:
        handoffs = []
        for other in _agents:
            if agent is not other:
                handoffs.append(handoff(other.get_agent()))
        agent.get_agent().handoffs = handoffs.copy()

    '''
    handoffs = []
    for agent in _agents:
        handoffs.append(handoff(agent.get_agent()))

    _manager.get_agent().handoffs = handoffs    
    '''

def recreate_agents() -> Agent:
    for agent in _agents:
        agent.update_settings()
    #_manager.update_settings()
    return _manager
