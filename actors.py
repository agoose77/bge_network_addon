from game_system.entity import Actor as _Actor

from json import dumps
from messages import *

from math import log
from network.annotations.decorators import simulated
from network.enums import Netmodes, Roles
from functools import partial


def get_bound_prefix(prefix, subject, instance_id):
    return prefix + dumps((subject, instance_id))


class SCAActor(_Actor):
    """Interface for SCA_ system with network system"""

    property_names = set()

    def __init__(self, scene, unique_id, is_static=False):
        """Initialise new network object

        :param obj: GameObject instance
        """
        self._obj = self.transform._game_object

        self.states = {}
        self.simulated_states = {}
        self.rpc_arguments = {}

        self.convert_message_logic()

        scene.messenger.add_subscriber("sync_properties", self.sync_properties)

    def on_destroyed(self):
        self.scene.messenger.remove_subscriber("sync_properties", self.sync_properties)

        super().on_destroyed()

    def on_replicated(self, name):
        super().on_replicated(name)
        print("NAMe")
        if name == "roles":
            print("ROELS")
            self.set_network_state()

        if name in self.property_names:
            self.set_property(name, getattr(self, name))

        self.receive_prefixed_message(message_prefixes_unique['NOTIFICATION'], name)

    @property
    def is_alive(self):
        return not self._obj.invalid

    def get_property(self, name):
        return self._obj[name]

    def set_property(self, name, value):
        self._obj[name] = value

    def _class_receive_no_broadcast(self, subject):
        """Send message that won't be picked up as a broadcast"""
        self._obj.sendMessage(subject, "", self._obj.name)

    def send_message(self, subject, body="", target=""):
        """Send message to game objects

        :param subject: message subject
        :param body: message body
        :param target: name of objects to receive message
        """
        self._obj.sendMessage(subject, body, target)

    def receive_prefixed_message(self, prefix, subject):
        """Send message to a specific instance that won't be picked up as a broadcast

        :param prefix: prefix of subject
        :param subject: subject of message
        """
        modified_subject = get_bound_prefix(prefix, subject, self.unique_id)
        self._class_receive_no_broadcast(modified_subject)

    def convert_message_logic(self):
        """Convert message sensors & actuators to use unique subjects

        :param identifier: unique identifier
        :param obj: game object
        """
        from bge import types

        instance_id = self.unique_id
        message_self = message_prefixes_unique["SELF_MESSAGE"]

        sensors = [s for s in self._obj.sensors if isinstance(s, types.KX_NetworkMessageSensor)]

        for message_handler in sensors:
            message_subject = message_handler.subject

            for prefix in message_prefixes_unique.values():
                if message_subject.startswith(prefix):
                    break

            else:
                continue

            name = message_subject[len(prefix):]
            message_handler.subject = get_bound_prefix(prefix, name, instance_id)

            # Subscribe to messages
            if prefix == message_self:
                self.messenger.add_subscriber(name, partial(self.receive_prefixed_message, prefix, name))

        actuators = [c for c in self._obj.actuators if isinstance(c, types.KX_NetworkMessageActuator)]
        for message_handler in actuators:
            message_subject = message_handler.subject

            for prefix in message_prefixes_unique.values():
                if message_subject.startswith(prefix):
                    break

            else:
                continue

            name = message_subject[len(prefix):]
            message_handler.subject = get_bound_prefix(prefix, name, instance_id)

    @staticmethod
    def get_state_mask(states):
        mask = 0
        for i, value in enumerate(states):
            mask |= value << i

        return mask

    def set_network_state(self, just_initialised=False):
        """Unset any states from other netmodes, then set correct states
        """
        states = self.states
        simulated_states = self.simulated_states

        state = self._obj.state
        get_mask = self.get_state_mask

        for mask_netmode, netmode_states in states.items():
            state &= ~get_mask(netmode_states)

        simulated_proxy = Roles.simulated_proxy
        netmode = self.scene.world.netmode

        try:
            roles = self.roles

        except AttributeError:
            pass

        # Set active states if simulated
        else:
            local_role = roles.local
            active_states = states[netmode]

            # On creation, we don't know if we are the autonomous proxy or not, so regress to simulated_proxy until then?
        # TODO
            not_sure_autonomous_proxy = local_role == Roles.autonomous_proxy and just_initialised

            for i, (state_bit, simulated_bit) in enumerate(zip(active_states, simulated_states)):
                # Permission checks
                if (local_role > simulated_proxy and not not_sure_autonomous_proxy) or \
                        (simulated_bit and local_role == simulated_proxy):
                    state |= state_bit << i

        if not state:
            all_states = (1 << i for i in range(30))
            used_states = {c.state for c in self._obj.controllers}

            try:
                state = next(c for c in all_states if c not in used_states)
                state_index = int(log(state, 2)) + 1
                print("{}: Using default state of {}".format(self._obj.name, state_index))

            except ValueError:
                print("{}: Required a default empty state, none available".format(self._obj.name))

        self._obj.state = state

    def dispatch_rpc(self, event_name, data):
        arguments = self.rpc_arguments[event_name]

        for name_, value in zip(arguments, data):
            self._obj[name_] = value

        self.receive_prefixed_message(message_prefixes_unique['RPC_INVOKE'], event_name)

    def invoke_rpc(self, rpc_name):
        obj = self._obj

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
