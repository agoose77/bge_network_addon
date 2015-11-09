from network.replicable import Replicable
from network.rules import ReplicationRulesBase

from game_system.replicables import PawnController, PlayerPawnController, ReplicationInfo
from game_system.entity import Actor

from controllers import IRCChatController
from mainloop import ControllerPendingAssignmentSignal


class Rules(ReplicationRulesBase):
    
    def pre_initialise(self, connection_info):
        return
    
    # def post_disconnect(self, conn, replicable):
    #     replicable.deregister()
    
    def post_initialise(self, replication_manager):
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
