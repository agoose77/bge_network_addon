from network.replicable import Replicable

from game_system.replicables import PawnController, PlayerPawnController, ReplicationInfo
from game_system.entity import Actor

from bge import logic


class Rules:

    def pre_initialise(self, connection_info):
        return
    
    # def post_disconnect(self, conn, replicable):
    #     replicable.deregister()
    
    def post_initialise(self, replication_manager):
        # Ask for a pawn to be spawned
        logic.game.create_new_player(replication_manager)
            
    def is_relevant(self, replication_manager, replicable):
        if isinstance(replicable, PawnController):
            return False
        
        elif isinstance(replicable, Actor):
            return True
        
        elif isinstance(replicable, ReplicationInfo):
            return True

        elif replicable.always_relevant:
            return True


# TODO allow BGE (logic bricks) scene to handle incoming controller - spawn in right scene
