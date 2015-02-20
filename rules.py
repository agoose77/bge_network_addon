from network.world_info import WorldInfo
from network.rules import ReplicationRulesBase
from network.enums import Roles
from network.replicable import Replicable

from game_system.controllers import PawnController, PlayerPawnController
from game_system.entities import Actor
from game_system.replication_info import ReplicationInfo

from mainloop import ControllerPendingAssignmentSignal


class Rules(ReplicationRulesBase):
    
    def pre_initialise(self, addr, netmode):
        return
    
    def post_disconnect(self, conn, replicable):
        replicable.deregister()
    
    def post_initialise(self, replication_stream):
        cont = PlayerPawnController(register_immediately=True)
        ControllerPendingAssignmentSignal.invoke(cont)
        return cont
            
    def is_relevant(self, connection, replicable):
        if isinstance(replicable, PawnController):
            return False
        
        elif isinstance(replicable, Actor):
            return True
        
        elif isinstance(replicable, ReplicationInfo):
            return True


def init():
    rules = Rules()

    WorldInfo.rules = rules
