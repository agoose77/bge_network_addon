from network.annotations.decorators import requires_netmode
from network.enums import Netmodes
from network.replicable import Replicable
from network.type_serialisers import TypeInfo

from game_system.replicables import PlayerPawnController, PlayerReplicationInfo
from game_system.chat.irc import IRCClient


class IRCChatController(PlayerPawnController):

    def __init__(self, scene, unique_id, is_static=False):
        super().__init__(scene, unique_id, is_static)

        self.client_init_chat()

    @requires_netmode(Netmodes.client)
    def client_init_chat(self):
        self.chat_client = IRCClient()
        self.chat_client.start()

        self.channel = self.chat_client.join_channel("#TestGameChat_BGE")
        self.channel.on_message = self.client_on_message_received
        self.chat_client.on_private_message = self.client_on_message_received

        self.set_name("Player2")

    def client_on_message_received(self, message, sender):
        if self.pawn:
            self.pawn.messenger.send("message_received", message=message, sender=sender)

    def send_message(self, message, info=None):
        if info is None:
            self.channel.say(message)

        else:
            self.chat_client.say(message, info.name)

        self.pawn.messenger.send("message_sent", message=message, sender=self.info.name)

    @requires_netmode(Netmodes.client)
    def set_name(self, name):
        self._server_set_name(name)

        self.chat_client.nickname = name

    def _server_set_name(self, name: str) -> Netmodes.server:
        self.info.name = name

    @requires_netmode(Netmodes.client)
    def on_tick(self):
        self.chat_client.receive_messages()
