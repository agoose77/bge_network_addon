from game_system.entity import Actor as _Actor

from messages import *

from math import log
from network.annotations.decorators import simulated
from network.enums import Netmodes, Roles
from functools import partial


class SCAActor(_Actor):
    """Interface for SCA_ system with network system"""

    property_names = set()

    states = None
    rpc_arguments = None
    game_object = None

    def __init__(self, scene, unique_id, is_static=False):
        """Initialise new network object

        :param obj: GameObject instance
        """
        self._convert_message_logic()

        scene.messenger.add_subscriber("sync_properties", self.sync_properties)

    def on_destroyed(self):
        self.scene.messenger.remove_subscriber("sync_properties", self.sync_properties)

        super().on_destroyed()

    def on_replicated(self, name):
        super().on_replicated(name)

        if name == "roles":
            print("ROELS")
            self.set_network_states()

        if name in self.property_names:
            self.set_property(name, getattr(self, name))

        self.receive_prefixed_message(message_prefixes_replicable['NOTIFICATION'], name)

    @property
    def is_alive(self):
        return not self.game_object.invalid

    @simulated
    def get_property(self, name):
        return self.game_object[name]

    @simulated
    def set_property(self, name, value):
        self.game_object[name] = value

    @simulated
    def receive_prefixed_message(self, prefix, subject):
        """Send message to a specific instance that won't be picked up as a broadcast

        :param prefix: prefix of subject
        :param subject: subject of message
        """
        modified_subject = encode_replicable_info(subject, self)
        self.game_object.sendMessage(prefix + modified_subject, "<invalid>", self.game_object.name)

    @simulated
    def _convert_message_logic(self):
        """Convert message sensors & actuators to use unique subjects

        :param identifier: unique identifier
        :param obj: game object
        """
        from bge import types

        message_self = message_prefixes_replicable["SELF_MESSAGE"]

        # Convert sensors
        sensors = [s for s in self.game_object.sensors if isinstance(s, types.KX_NetworkMessageSensor)]
        for message_handler in sensors:
            message_subject = message_handler.subject

            for prefix in message_prefixes_replicable.values():
                if message_subject.startswith(prefix):
                    break

            else:
                continue

            name = message_subject[len(prefix):]
            message_handler.subject = prefix + encode_replicable_info(name, self)

            # Subscribe to messages
            if prefix == message_self:
                self.messenger.add_subscriber(name, partial(self.receive_prefixed_message, prefix, name))

        # Convert actuators
        actuators = [c for c in self.game_object.actuators if isinstance(c, types.KX_NetworkMessageActuator)]
        for message_handler in actuators:
            message_subject = message_handler.subject

            for prefix in message_prefixes_replicable.values():
                if message_subject.startswith(prefix):
                    break

            else:
                continue

            name = message_subject[len(prefix):]
            message_handler.subject = prefix + encode_replicable_info(name, self)

    @simulated
    def set_network_states(self, just_initialised=False):
        """Unset any states from other netmodes, then set correct states
        """
        states = self.states
        state = 0

        simulated_proxy = Roles.simulated_proxy
        netmode = self.scene.world.netmode

        try:
            roles = self.roles

        except AttributeError:
            pass

        # Set active states if simulated
        else:
            local_role = roles.local
            state_data = states[netmode]

            # Autonomous proxy but first run
            not_sure_autonomous_proxy = local_role == Roles.autonomous_proxy and just_initialised

            simulated_states = state_data['simulated_states']
            active_states = state_data['states']

            for i, (state_bit, simulated_bit) in enumerate(zip(active_states, simulated_states)):
                # Permission checks
                if (local_role > simulated_proxy and not not_sure_autonomous_proxy) or \
                        (simulated_bit and local_role == simulated_proxy):
                    state |= state_bit << i

        if not state:
            all_states = (1 << i for i in range(30))
            used_states = {c.state for c in self.game_object.controllers}

            try:
                state = next(c for c in all_states if c not in used_states)
                state_index = int(log(state, 2)) + 1
                print("{}: Using default state of {}".format(self.game_object.name, state_index))

            except ValueError:
                print("{}: Required a default empty state, none available".format(self.game_object.name))

        self.game_object.state = state

    @simulated
    def dispatch_rpc(self, event_name, data):
        arguments = self.rpc_arguments[event_name]

        for name_, value in zip(arguments, data):
            self.game_object[name_] = value

        self.receive_prefixed_message(message_prefixes_replicable['RPC_INVOKE'], event_name)

    @simulated
    def invoke_rpc(self, rpc_name):
        obj = self.game_object

        rpc_args = self.rpc_arguments[rpc_name]
        rpc_data = [obj[arg_name] for arg_name in rpc_args]

        getattr(self, rpc_name)(*rpc_data)

    @simulated
    def sync_properties(self):
        if not self.is_alive:
            return

        if self.roles.local == Roles.authority:
            get_property = self.get_property
            for attr_name in self.property_names:
                setattr(self, attr_name, get_property(attr_name))
