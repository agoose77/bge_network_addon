from network.decorators import requires_netmode
from network.enums import Netmodes
from network.replicable import Replicable
from network.type_flag import TypeFlag

from game_system.controllers import PlayerPawnController
from game_system.replication_info import PlayerReplicationInfo
from game_system.chat.irc import IRCClient
from game_system.signals import MessageReceivedSignal, LogicUpdateSignal


class IRCChatController(PlayerPawnController):

    def on_initialised(self):
        super().on_initialised()

        self.client_init_chat()

    @requires_netmode(Netmodes.client)
    def client_init_chat(self):
        self.chat_client = IRCClient()
        self.chat_client.start()

        self.channel = self.chat_client.join_channel("#TestGameChat_BGE")
        self.channel.on_message = self.on_message_received
        self.chat_client.on_private_message = self.on_message_received

        self.set_name("Player2")

    def on_message_received(self, message, sender):
        MessageReceivedSignal.invoke(message, sender)

    def send_message(self, message, info=None):
        if info is None:
            self.channel.say(message)

        else:
            self.chat_client.say(message)

        MessageReceivedSignal.invoke(message, self.info.name)

    @requires_netmode(Netmodes.client)
    def set_name(self, name):
        self._server_set_name(name)

        self.chat_client.nickname = name

    def _server_set_name(self, name: TypeFlag(str)) -> Netmodes.server:
        self.info.name = name

    @LogicUpdateSignal.on_global
    @requires_netmode(Netmodes.client)
    def on_updates(self, dt):
        self.chat_client.receive_messages()