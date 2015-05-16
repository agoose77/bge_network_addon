from network.world_info import WorldInfo
from network.replicable import Replicable
from network.rules import ReplicationRulesBase

from game_system.controllers import PawnController, PlayerPawnController
from game_system.entities import Actor
from game_system.replication_info import ReplicationInfo

from controllers import IRCChatController
from mainloop import ControllerPendingAssignmentSignal


class Rules(ReplicationRulesBase):
    
    def pre_initialise(self, addr, netmode):
        return
    
    def post_disconnect(self, conn, replicable):
        replicable.deregister()
    
    def post_initialise(self, replication_stream):
        cont = IRCChatController()
        ControllerPendingAssignmentSignal.invoke(cont)
        return cont
            
    def is_relevant(self, connection, replicable):
        if isinstance(replicable, PawnController):
            return False
        
        elif isinstance(replicable, Actor):
            return True
        
        elif isinstance(replicable, ReplicationInfo):
            return True

        elif replicable.always_relevant:
            return True


def init():
    rules = Rules()

    WorldInfo.rules = rules
