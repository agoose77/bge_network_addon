from network.descriptors import Attribute
from network.decorators import with_tag, reliable, simulated, set_annotation, requires_permission
from network.enums import Netmodes, Roles
from network.network import Network
from network.replicable import Replicable
from network.signals import DisconnectSignal, Signal, SignalListener
from network.type_flag import TypeFlag
from network.world_info import WorldInfo

from game_system.game_loop import FixedTimeStepManager, OnExitUpdate
from game_system.resources import ResourceManager
from game_system.signals import LogicUpdateSignal, TimerUpdateSignal, PlayerInputSignal
from game_system.timer import Timer

# Dummy logic loop support for non-patched blender
from bge import logic, types
types.KX_PythonLogicLoop = type("", (), {})

from bge_game_system.inputs import BGEInputManager
from bge_game_system.physics import BGEPhysicsSystem
from bge_game_system.definitions import BGEComponent, BGEComponentLoader

from collections import defaultdict, OrderedDict, deque
from json import load, loads, dumps
from os import path, listdir
from math import log

from actors import *
from signals import *


DATA_PATH = "network_data"
DELIMITER = ","

replicables_to_game_objects = {}
game_objects_to_replicables = {}

classes = {}
configurations = {}
sorted_rpc_arguments = {}


def safe_for_format(value):
    if isinstance(value, str):
        return "'{}'".format(value)

    return value


class BpyResolver:

    @staticmethod
    def resolve_role(value):
        return getattr(Roles, value.lower())

    @staticmethod
    def resolve_netmode(value):
        """Convert BPY netmode enum to constant

        :param value: enum value
        """
        return getattr(Netmodes, value.lower())

    @staticmethod
    def resolve_type(type_):
        """Convert BPY type enum to type class

        :param value: enum value
        """
        return dict(STRING=str, INT=int, BOOL=bool, FLOAT=float, TIMER=float)[type_]


# Entity loader
class GameObjectInjector:
    """Inject GameObject into entity loader"""

    game_object = None
    _default_load = None

    _find_or_create_object = BGEComponentLoader.find_or_create_object

    @classmethod
    def find_or_create_object(cls, entity, definition):
        if cls.game_object is not None:
            _pending_obj, cls.game_object = cls.game_object, None
            return _pending_obj

        return cls._find_or_create_object(entity, definition)


BGEComponentLoader.find_or_create_object = GameObjectInjector.find_or_create_object
ResourceManager.data_path = logic.expandPath("//{}".format(DATA_PATH))


def string_to_wrapped_int(string, boundary):
    value = 0
    for char in string:
        value = (value * 0x110000) + ord(char)
    return value % boundary


def instantiate_actor_from_obj(obj):
    """Instantiate network actor from gameobject

    :param obj: KX_GameObject instance
    """
    cls = classes[obj.name]

    GameObjectInjector.game_object = obj

    if obj.name not in obj.scene.objectsInactive:
        network_id = string_to_wrapped_int(obj.name, Replicable._MAXIMUM_REPLICABLES + 1)
        print("Found static network object: {}, assigning ID: {}".format(obj.name, network_id))
        return cls(network_id, register_immediately=True, static=True)

    else:
        return cls(register_immediately=True)


def no_op_func(*args, **kwargs):
    return None


def load_configuration(name):
    """Load configuration data for GameObject

    :param name: name of GameObject
    """

    resource = ResourceManager[name]
    config_path = ResourceManager.get_absolute_path(resource['actor.definition'])

    with open(config_path, 'r') as file:
        loaded = load(file)

    loaded["states"] = {BpyResolver.resolve_netmode(x): y for x, y in loaded["states"].items()}

    for function_name, data in loaded['rpc_calls'].items():
        data['arguments'] = {k: BpyResolver.resolve_type(v) for k, v in data['arguments'].items()}
        data['target'] = BpyResolver.resolve_netmode(data['target'])

    loaded['remote_role'] = BpyResolver.resolve_role(loaded['remote_role'])

    return loaded


def load_object_definitions(scene):
    """Load definition files for all objects, in all scenes

    :param scene: scene to load for
    """
    for obj in list(scene.objects) + list(scene.objectsInactive):
        name = obj.name

        if name in classes:
            continue

        try:
            configuration = load_configuration(name)

        except FileNotFoundError:
            continue

        configurations[name] = configuration
        sorted_rpc_arguments[name] = {rpc_name: sorted(data['arguments']) for rpc_name, data in
                                      configuration['rpc_calls'].items()}

        classes[name] = ReplicableFactory.from_configuration(name, configuration)


from network.decorators import set_annotation, get_annotation
from inspect import getmembers

prefix_listener = lambda value: set_annotation("message_prefix")(value)
get_prefix_listener = lambda value: get_annotation("message_prefix")(value)


message_subjects = dict(CONTROLLER_REQUEST="CONTROLLER_REQUEST")

# Prefixes for messages associated with replicables
message_prefixes_unique = dict(
    CONTROLLER_ASSIGN="CONTROLLER_ASSIGN_",
    CONTROLLER_REASSIGN="CONTROLLER_REASSIGN_",
    INITIALISER="ON_INIT_",

    RPC_INVOKE="RPC_",
    NOTIFICATION="NOTIFY_",
    TARGETED_SIGNAL="SIGNAL_",
    GLOBAL_SIGNAL="GLOBAL_SIGNAL_",
    METHOD_INVOKE="CALL_",
    )

message_prefixes_global = dict(SET_NETMODE="SET_NETMODE_")


class MessageDispatcher:

    def __init__(self):
        self.listeners = defaultdict(list)

        for name, value in getmembers(self):
            prefix = get_prefix_listener(value)
            if prefix is not None:
                self.listeners[prefix].append(value)

    @staticmethod
    def get_bound_prefix(prefix, subject, instance_id):
        return prefix + dumps((subject, instance_id))

    def handle_messages(self, subjects):
        prefix_listeners = self.listeners
        global_prefixes = set(message_prefixes_global.values())

        for subject in subjects:
            starts_with = subject.startswith

            for prefix, listeners in prefix_listeners.items():
                if starts_with(prefix):
                    following_prefix = subject[len(prefix):]

                    if prefix in global_prefixes:
                        for listener in listeners:
                            listener(following_prefix)

                    else:
                        payload, recipient_id = loads(following_prefix)
                        for listener in listeners:
                            listener(recipient_id, payload)

    @prefix_listener(message_prefixes_global['SET_NETMODE'])
    def message_listener_set_netmode(self, netmode_name):
        try:
            netmode = getattr(Netmodes, netmode_name)

        except AttributeError:
            print("Couldn't set netmode as {}".format(netmode_name))
            return

        NetmodeAssignedSignal.invoke(netmode)


    @prefix_listener(message_prefixes_unique['METHOD_INVOKE'])
    def message_listener_invoke_method(self, network_id, method_name):
        """Handle RPC messages"""
        try:
            replicable = WorldInfo.get_replicable(network_id)

        except LookupError:
            return

        getattr(replicable, method_name)()

    @prefix_listener(message_prefixes_unique['RPC_INVOKE'])
    def message_listener_rpc(self, network_id, rpc_name):
        """Handle RPC messages"""
        try:
            replicable = WorldInfo.get_replicable(network_id)

        except LookupError:
            return

        obj = replicables_to_game_objects[replicable]
        obj_class_name = obj.name

        rpc_args = sorted_rpc_arguments[obj_class_name][rpc_name]
        rpc_data = [obj[arg_name] for arg_name in rpc_args]

        getattr(replicable, rpc_name)(*rpc_data)

    @prefix_listener(message_prefixes_unique['CONTROLLER_ASSIGN'])
    def message_listener_controller_assignment(self, network_id, replicable_class_name):
        """Handle connection controller initial pawn assignment"""
        ControllerAssignedSignal.invoke(replicable_class_name, network_id)

    @prefix_listener(message_prefixes_unique['CONTROLLER_REASSIGN'])
    def message_listener_controller_reassignment(self, network_id, replicable_class_name):
        """Handle connection controller subsequent pawn assignment"""
        ControllerReassignedSignal.invoke(replicable_class_name, network_id)

    @prefix_listener(message_prefixes_unique['INITIALISER'])
    def message_listener_on_initialised(self, network_id, message_name):
        """Handle connection controller subsequent pawn assignment"""
        OnInitialisedMessageSignal.invoke(message_name, network_id)


class PawnInitialisationManager(SignalListener):
    """Handle initialisation of recently spawned pawns"""

    def __init__(self):
        self.initialisers_to_pawn = {}
        self.register_signals()

    def associate_pawn_with_initialiser(self, initialiser, pawn):
        self.initialisers_to_pawn[initialiser] = pawn

    @OnInitialisedMessageSignal.on_global
    def forward_initialisation_message(self, subject, initialiser):
        try:
            pawn = self.initialisers_to_pawn[initialiser]

        except KeyError:
            print("Unable to associate network id: {} with a spawned object".format(initialiser))
            return

        # Send ONLY to this object (avoid positive feedback)
        pawn.bge_interface.receive_prefixed_message(message_prefixes_unique['INITIALISER'], subject)


def listener(cont):
    """Dispatch messages to listeners

    :param cont: controller instance
    """
    message_sens = next(c for c in cont.sensors if isinstance(c, types.KX_NetworkMessageSensor))

    if not message_sens.positive:
        return

    subjects = message_sens.subjects
    message_dispatcher.handle_messages(subjects)


def update_graphs():
    """Update isolated resource graphs"""
    Replicable.update_graph()
    Signal.update_graph()


def signal_to_message(*args, signal, target, **kwargs):
    """Produce message representation of signal"""
    signal_name = signal.__name__

    if isinstance(target, SCAActor):
        modified_subject = MessageDispatcher.get_bound_prefix(message_prefixes_unique['TARGETED_SIGNAL'], signal_name,
                                                              target.instance_id)
        logic.sendMessage(modified_subject)

    else:
        subject = message_prefixes_unique['GLOBAL_SIGNAL'] + signal_name
        logic.sendMessage(subject)


class StateManager(SignalListener):
    """Manages SCA state machine transitions"""

    def __init__(self):
        self.register_signals()

        self.callbacks = []

    @RegisterStateSignal.on_global
    def handle_signal(self, callback):
        self.callbacks.append(callback)

    def set_states(self):
        for callback in self.callbacks:
            callback()

        self.callbacks.clear()


class SignalForwarder(SignalListener):
    """Forward all globally available signals to handler"""

    def __init__(self, handler):
        self.register_signals()

        self._handler = handler

    @Signal.on_global
    def handle_signal(self, *args, signal, target, **kwargs):
        self._handler(signal, *args, signal=signal, target=target, **kwargs)


class ReplicableFactory:

    @classmethod
    def create_rpc_string(cls, name, data):
        """Construct RPC call from configuration data

        :param name: name of RPC call
        :param data: configuration data
        """
        arguments = data['arguments']
        argument_names = sorted(arguments)

        annotated_arguments = ["{}:TypeFlag({})".format(k, arguments[k].__name__) for k in argument_names]
        argument_declarations = ", {}".format(','.join(annotated_arguments)) if argument_names else ""
        arguments = "({}{})".format(','.join(argument_names), ',' if argument_names else '')

        is_reliable = data['reliable']
        is_simulated = data['simulated']
        return_target = data['target']

        decorator_list = []

        if is_reliable:
            decorator_list.append("@reliable")

        if is_simulated:
            decorator_list.append("@simulated")

        decorators = '\n'.join(decorator_list)

        func_body = \
"""
{decorators}
def {name}(self{args}) -> {returns}:
    self.bge_interface.dispatch_rpc('{name}', {all_args})
"""
        return func_body.format(decorators=decorators, name=name, args=argument_declarations, returns=return_target,
                                all_args=arguments)

    @classmethod
    def create_property_synchronisation(cls, attributes):
        setter_lines = ["self.{name} = self.bge_interface.get_property('{name}')".format(name=name) for name in attributes]
        getter_lines = ["self.bge_interface.set_property('{name}', self.{name})".format(name=name) for name in attributes]

        setter_line = "\n        ".join(setter_lines)
        getter_line = "\n        ".join(getter_lines)

        func_body = \
"""
@simulated
@PropertySynchroniseSignal.on_global
def update(self, delta_time):
    if not self.bge_interface.is_alive:
        return

    if self.roles.local == Roles.authority:
        {}
    else:
        {}"""

        return func_body.format(setter_line, getter_line)

    @classmethod
    def create_conditions_string(cls, attributes):
        """Construct conditions generator from attribute names

        :param attributes: sequence of names of attributes
        """
        yield_statements = []
        for attr_name, data in attributes.items():
            conditions = []
            if data['initial_only']:
                conditions.append("is_initial")

            if not data['to_owner']:
                conditions.append("not is_owner")

            if conditions:
                yield_statements.append("if {}:".format(" and ".join(conditions)))
                yield_statements.append("    yield '{}'".format(attr_name))

            else:
                yield_statements.append("yield '{}'".format(attr_name))

        yield_body = "\n    ".join(yield_statements)
        return """def conditions(self, is_owner, is_complaint, is_initial):\n"""\
               """    yield from super().conditions(is_owner, is_complaint, is_initial)\n    {}""".format(yield_body)

    @classmethod
    def create_attribute_string(cls, name, data, is_raw=False):
        default = data['default']
        if not is_raw:
            default = safe_for_format(default)

        return "{} = Attribute({}, notify={})".format(name, default, data['notify'])

    @classmethod
    def parse_bases(cls, base_paths):
        namespace = OrderedDict()
        for class_path in base_paths:
            *module_path, class_name = class_path.split(".")
            try:
                module = __import__('.'.join(module_path), fromlist=[''])
            except ImportError as err:
                raise ImportError("Couldn't import template: {}".format(class_path)) from err

            try:
                new_cls = getattr(module, class_name)

            except AttributeError as err:
                raise AttributeError("Template module {}.py has no class {}".format(module.__name__, class_name)) \
                    from err

            namespace[class_name] = new_cls

        return namespace

    @classmethod
    def from_configuration(cls, name, configuration):
        """Construct class from definition file

        :param name: name of class
        :param configuration: configuration data
        """
        base_namespaces = cls.parse_bases(configuration['templates'])

        class_lines = []

        attributes = configuration['attributes']
        attribute_definitions = [cls.create_attribute_string(attr_name, data) for attr_name, data
                                 in attributes.items()]
        # Add remote role
        remote_role = configuration['remote_role']
        roles_data = dict(default="Roles(Roles.authority, {})".format(remote_role), notify=True)
        attribute_definitions.append(cls.create_attribute_string("roles", roles_data, is_raw=True))

        class_lines.extend(attribute_definitions)

        rpc_calls = configuration['rpc_calls']
        rpc_definitions = [cls.create_rpc_string(function_name, data) for function_name, data in rpc_calls.items()]
        class_lines.extend([y for c in rpc_definitions for y in c.split("\n")])

        conditions_definition = cls.create_conditions_string(attributes)
        class_lines.extend(conditions_definition.split("\n"))

        if attributes:
            sync_definition = cls.create_property_synchronisation(attributes)
            class_lines.extend(sync_definition.split("\n"))

        default_values = configuration['defaults']
        class_lines.extend(["{} = {}".format(name, "'" + value + "'" if isinstance(value, str) else value)
                            for name, value in default_values.items()])

        class_body = "\n    ".join(class_lines)
        bases_string = ", ".join(base_namespaces.keys())
        class_declaration = "class {}({}):\n    ".format(name, bases_string) + class_body

        exec(class_declaration, globals(), base_namespaces)
        print(class_declaration)
        return base_namespaces[name]


class ControllerManager(SignalListener):

    def __init__(self, initialisation_manager):
        self.pending_controllers = deque()
        self.initialisation_manager = initialisation_manager

        self.register_signals()

    @staticmethod
    def request_assignment():
        logic.sendMessage(message_subjects['CONTROLLER_REQUEST'])

    @ControllerReassignedSignal.on_global
    def on_reassigned(self, replicable_name, original_id):
        try:
            replicable_cls = Replicable.from_type_name(replicable_name)

        except KeyError:
            print("Controller pawn assignment requires valid object name, not {}".format(replicable_name))
            return

        current_pawn = Replicable[original_id]
        controller = current_pawn.uppermost

        if controller is None:
            print("Cannot reassign pawn from network object with no controller")
            return

        new_pawn = replicable_cls(register_immediately=True)
        controller.possess(new_pawn)

        # Associate network object with this initialiser
        self.initialisation_manager.associate_pawn_with_initialiser(original_id, new_pawn)

        # Deregister old pawn
        current_pawn.deregister()

    @ControllerPendingAssignmentSignal.on_global
    def on_connection(self, controller):
        self.pending_controllers.append(controller)

        # Assume no code will listen for multiple messages
        self.request_assignment()

    @ControllerAssignedSignal.on_global
    def on_assigned(self, replicable_name, initialiser_id):
        controller = self.pending_controllers.popleft()
        cls = Replicable.from_type_name(replicable_name)
        replicable = cls(register_immediately=True)
        controller.possess(replicable)
        # Associate network object with this initialiser
        self.initialisation_manager.associate_pawn_with_initialiser(initialiser_id,  replicable)

        # If still waiting, trigger controller
        if self.pending_controllers:
            self.request_assignment()


@with_tag("bge_interface")
class BGESetupComponent(BGEComponent):

    def __init__(self, config_section, entity, obj):
        """Initialise new network object

        :param obj: GameObject instance
        """
        self._rpc_args = sorted_rpc_arguments[obj.name]
        self._entity = entity
        self._obj = obj
        self._configuration = configurations[obj.name]

        self.convert_message_logic(obj, entity.instance_id)

        # Associate object with replicable
        replicables_to_game_objects[entity] = obj
        game_objects_to_replicables[obj] = entity

        RegisterStateSignal.invoke(self.set_network_state)

    @property
    def game_object(self):
        return self._obj

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
        modified_subject = MessageDispatcher.get_bound_prefix(prefix, subject, self._entity.instance_id)
        self._class_receive_no_broadcast(modified_subject)

    @staticmethod
    def convert_message_logic(obj, instance_id):
        """Convert message sensors & actuators to use unique subjects

        :param identifier: unique identifier
        :param obj: game object
        """
        sensors = [s for s in obj.sensors if isinstance(s, types.KX_NetworkMessageSensor)]
        actuators = [c for c in obj.actuators if isinstance(c, types.KX_NetworkMessageActuator)]

        for message_handler in sensors + actuators:
            message_subject = message_handler.subject

            for prefix in message_prefixes_unique.values():
                if message_subject.startswith(prefix):
                    break

            else:
                continue

            name = message_subject[len(prefix):]
            message_handler.subject = MessageDispatcher.get_bound_prefix(prefix, name, instance_id)

    @staticmethod
    def get_state_mask(states):
        mask = 0
        for i, value in enumerate(states):
            mask |= value << i

        return mask

    def set_network_state(self):
        """Unset any states from other netmodes, then set correct states
        """
        states = self._configuration['states']
        simulated_states = self._configuration['simulated_states']

        netmode = WorldInfo.netmode
        state = self._obj.state
        get_mask = self.get_state_mask

        for mask_netmode, netmode_states in states.items():
            state &= ~get_mask(netmode_states)

        simulated_proxy = Roles.simulated_proxy

        try:
            roles = self._entity.roles

        except AttributeError:
            pass

        # Set active states if simulated
        else:
            local_role = roles.local
            active_states = states[netmode]
            for i, (state_bit, simulated_bit) in enumerate(zip(active_states, simulated_states)):
                # Permission checks
                if local_role > simulated_proxy or (simulated_bit and local_role == simulated_proxy):
                    state |= state_bit << i

        if not state:
            all_states = (1 << i for i in range(30))
            used_states = {c.state for c in self._obj.controllers}

            try:
                state = next(c for c in all_states if not c in used_states)
                state_index = int(log(state, 2)) + 1
                print("{}: Using default state of {}".format(self._obj.name, state_index))

            except ValueError:
                print("{}: Required a default empty state, none available".format(self._obj.name))

        self._obj.state = state

    def on_notify(self, event_name):
        self.receive_prefixed_message(message_prefixes_unique['NOTIFICATION'], event_name)

    def dispatch_rpc(self, event_name, data):
        arguments = self._rpc_args[event_name]

        for name_, value in zip(arguments, data):
            self._obj[name_] = value

        self.receive_prefixed_message(message_prefixes_unique['RPC_INVOKE'], event_name)


message_dispatcher = MessageDispatcher()


class GameLoop(FixedTimeStepManager, SignalListener):

    def __init__(self):
        super().__init__()

        self.pending_exit = False
        # Set default step function
        self.on_step = self.step_default

        print("Waiting for netmode assignment message")

        self.register_signals()
        update_graphs()

    def enable_network(self, netmode):
        # Load configuration
        print("Loading network information from {}".format(DATA_PATH))
        file_path = logic.expandPath("//{}".format(DATA_PATH))
        main_definition_path = path.join(file_path, "main.definition")

        # Load network information
        with open(main_definition_path, "r") as file:
            data = load(file)

        self.configuration_file_names = {path.splitext(f)[0] for f in listdir(file_path)}
        self.network_update_interval = 1 / data['tick_rate']
        self.metric_interval = data['metric_interval']
        self.network_scene = next(s for s in logic.getSceneList() if s.name == data['scene'])
        BGEComponentLoader.scene = self.network_scene

        WorldInfo.netmode = netmode
        print("Running as a {}".format(Netmodes[WorldInfo.netmode]))

        # If is server
        if WorldInfo.netmode == Netmodes.server:
            self.initialisation_manager = PawnInitialisationManager()
            self.connection_manager = ControllerManager(self.initialisation_manager)

            WorldInfo.tick_rate = logic.getLogicTicRate()
            port = data['port']

        else:
            port = 0

        # Initialise systems
        self.network = Network("", port)
        self.physics_manager = BGEPhysicsSystem(no_op_func, no_op_func)
        self.input_manager = BGEInputManager()
        self.signal_forwarder = SignalForwarder(signal_to_message)
        self.state_manager = StateManager()

        # Time since last sent
        self.time_since_sent = 0.0

        # Load object definitions
        print("Loading definitions from scene objects")
        for scene in logic.getSceneList():
            load_object_definitions(scene)

        # Update any subscriptions
        update_graphs()

        # Set network as active update function
        self.on_step = self.step_network
        self.cleanup = lambda: self.network.stop()

        print("Network started")

    @property
    def time_step(self):
        return 1 / logic.getLogicTicRate()

    def check_exit(self):
        # Handle exit
        exit_key = logic.getExitKey()

        # Check if exit key is pressed
        if logic.keyboard.events[exit_key] == logic.KX_INPUT_JUST_ACTIVATED:
            quit_game = lambda: setattr(self, "pending_exit", True)
            # Exit immediately!
            if WorldInfo.netmode == Netmodes.server:
                raise OnExitUpdate()

            else:
                DisconnectSignal.invoke(quit_game)
                # Else abort
                timeout = Timer(0.6)
                timeout.on_target = quit_game

        # If we're pending exit
        if self.pending_exit:
            raise OnExitUpdate()

    @NetmodeAssignedSignal.on_global
    def on_netmode_assigned(self, netmode):
        """Callback when netmode has been assigned

        :param netmode: netmode to assign
        """
        self.enable_network(netmode)

    def step_default(self, delta_time):
        logic.NextFrame()

        # Check if exit is required
        self.check_exit()

    def step_network(self, delta_time):
        # Handle this outside of usual update
        if WorldInfo.netmode == Netmodes.server:
            WorldInfo.update_clock(delta_time)

        scene = self.network_scene

        # Initialise network objects if they're added
        configuration_file_names = self.configuration_file_names
        for obj in scene.objects:
            if obj.name not in configuration_file_names or obj in replicables_to_game_objects.values():
                continue

            instantiate_actor_from_obj(obj)

        update_graphs()

        self.network.receive()
        update_graphs()

        # Set network states
        self.state_manager.set_states()

        # Update BGE gameloop
        logic.NextFrame()

        # Catch any deleted BGE objects from BGE
        for actor in WorldInfo.subclass_of(SCAActor):
            if not actor.bge_interface.is_alive:
                actor.deregister(immediately=True)

        # Update Timers
        TimerUpdateSignal.invoke(delta_time)

        # Update Player Controller inputs for client
        self.input_manager.update()

        if WorldInfo.netmode != Netmodes.server:
            PlayerInputSignal.invoke(delta_time, self.input_manager.state)
            update_graphs()

        # Update main logic (Replicable update)
        PropertySynchroniseSignal.invoke(delta_time)
        LogicUpdateSignal.invoke(delta_time)
        update_graphs()

        self.physics_manager.update(delta_time)

        # Transmit new state to remote peer
        self.time_since_sent += delta_time
        is_full_update = (self.time_since_sent >= self.network_update_interval)

        self.network.send(is_full_update)

        if is_full_update:
            self.time_since_sent = 0.0

        network_metrics = self.network.metrics
        if network_metrics.sample_age >= self.metric_interval:
            network_metrics.reset_sample_window()

        # Check if exit is required
        self.check_exit()


def main():
    mainloop = GameLoop()
    mainloop.delegate()