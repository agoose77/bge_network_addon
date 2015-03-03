from network.descriptors import Attribute
from network.decorators import with_tag, reliable, simulated, set_annotation, requires_permission
from network.enums import Netmodes, Roles
from network.network import Network
from network.replicable import Replicable
from network.signals import SignalValue, DisconnectSignal, Signal, SignalListener
from network.type_flag import TypeFlag
from network.world_info import WorldInfo

from game_system.resources import ResourceManager
from game_system.entities import Actor as _Actor
from game_system.signals import LogicUpdateSignal, TimerUpdateSignal, PlayerInputSignal
from game_system.timer import Timer

from collections import defaultdict, OrderedDict, deque
from json import load, loads, dumps
from os import path, listdir
from time import clock
from math import log


try:
    import bge

except ImportError:
    WITH_BGE = False

else:
    WITH_BGE = True


CONTROLLER_ASSIGN_PREFIX = "CONTROLLER_ASSIGN_"
CONTROLLER_REASSIGN_PREFIX = "CONTROLLER_REASSIGN_"
CONTROLLER_REQUEST_MESSAGE = "CONTROLLER_REQUEST"

RPC_PREFIX = "RPC_"
NOTIFICATION_PREFIX = "NOTIFY_"
TARGETED_SIGNAL_PREFIX = "SIGNAL_"
GLOBAL_SIGNAL_PREFIX = "GLOBAL_SIGNAL_"
UNIQUE_PREFIXES = RPC_PREFIX, NOTIFICATION_PREFIX, TARGETED_SIGNAL_PREFIX, CONTROLLER_REASSIGN_PREFIX
DATA_PATH = "network_data"

DELIMITER = ","


SETUP_REPLICABLES = {}
classes = {}
configurations = {}
sorted_rpc_arguments = {}


def safe_for_format(value):
    if isinstance(value, str):
        return "'{}'".format(value)

    return value


class ControllerPendingAssignmentSignal(Signal):
    pass


class ControllerAssignedSignal(Signal):
    pass


class RegisterStateSignal(Signal):
    pass


class SCA_Actor(_Actor):
    """Interface for SCA_ system with network system"""

    component_tags = tuple(_Actor.component_tags) + ("bge_addon",)

    def on_notify(self, name):
        super().on_notify(name)

        self.bge_addon.on_notify(name)

    def dispatch_rpc(self, name, data):
        self.bge_addon.dispatch_rpc(name, data)

    def update(self, dt):
        pass


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

    @classmethod
    def load(cls, definition):
        if cls.game_object is not None:
            _pending_obj, cls.game_object = cls.game_object, None
            return _pending_obj

        return cls._default_load(definition)


def get_prefixed_messages(subjects, prefix):
    """Yield messages with prefix stripped"""
    for subject in subjects:
        if not subject.startswith(prefix):
            continue

        yield subject[len(prefix):]


def get_bound_messages(subjects, prefix):
    """Return dictionary of identifier to body for bound messages"""
    messages = defaultdict(list)
    for combined in get_prefixed_messages(subjects, prefix):
        name, id_ = loads(combined)
        messages[id_].append(name)

    return messages


def find_assigned_pawn_class(subjects):
    """Return message for controller assignment"""
    for subject in subjects:
        if not subject.startswith(CONTROLLER_ASSIGN_PREFIX):
            continue

        return subject[len(CONTROLLER_ASSIGN_PREFIX):]


def instantiate_actor_from_obj(obj):
    """Instantiate network actor from gameobject

    :param obj: KX_GameObject instance
    """
    cls = classes[obj.name]

    GameObjectInjector.game_object = obj
    # If we're static, this is not None
    network_id = obj.get("network_id")
    return cls(network_id, register_immediately=True)


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


def message_listener_rpc(subjects):
    """Handle RPC messages"""
    rpc_messages = get_bound_messages(subjects, RPC_PREFIX)

    for network_id, rpc_names in rpc_messages.items():

        try:
            replicable = WorldInfo.get_replicable(network_id)

        except LookupError:
            continue

        obj = SETUP_REPLICABLES[replicable]
        obj_name = obj.name
        sorted_rpc_args = sorted_rpc_arguments[obj_name]

        for rpc_name in rpc_names:
            rpc_args = sorted_rpc_args[rpc_name]
            rpc_data = [obj[arg_name] for arg_name in rpc_args]

            getattr(replicable, rpc_name)(*rpc_data)


def message_listener_controller_assignment(subjects):
    """Handle connection controller initial pawn assignment"""
    replicable_class_name = find_assigned_pawn_class(subjects)

    if replicable_class_name is not None:
        ControllerAssignedSignal.invoke(replicable_class_name)


def message_listener_controller_reassignment(subjects):
    """Handle connection controller subsequent pawn assignment"""
    reassignment_messages = get_bound_messages(subjects, CONTROLLER_REASSIGN_PREFIX)
    for network_id, replicable_names in reassignment_messages.items():
        replicable_name = next(replicable_names)
        print("PLS")
        try:
            replicable_cls = Replicable.from_type_name(replicable_name)

        except KeyError:
            print("Controller pawn assignment requires valid object name, not {}".format(replicable_name))
            continue

        current_pawn = Replicable[network_id]
        controller = current_pawn.uppermost

        if controller is None:
            print("Cannot reassign pawn from network object with no controller")
            continue

        new_pawn = replicable_cls(register_immediately=True)
        controller.possess(new_pawn)

message_subject_handlers = [message_listener_controller_assignment, message_listener_rpc]


def listener(cont):
    """Dispatch messages to listeners

    :param cont: controller instance
    """
    message_sens = next(c for c in cont.sensors if isinstance(c, types.KX_NetworkMessageSensor))

    if not message_sens.positive:
        return

    subjects = message_sens.subjects
    for handler in message_subject_handlers:
        handler(subjects)


def update_graphs():
    """Update isolated resource graphs"""
    Replicable.update_graph()
    Signal.update_graph()


def signal_to_message(*args, signal, target, **kwargs):
    """Produce message representation of signal"""
    signal_name = signal.__name__

    if target is not None and isinstance(target, Replicable):
        subject = TARGETED_SIGNAL_PREFIX + dumps((signal_name, target.instance_id))

    else:
        subject = GLOBAL_SIGNAL_PREFIX + signal_name

    logic.sendMessage(subject, "")


class StateManager(SignalListener):
    """Manages SCA state machine transitions"""

    def __init__(self):
        self.register_signals()

        self.callbacks = []

    @RegisterStateSignal.on_global
    def handle_signal(self, callback):
        self.callbacks.append(callback)

    def update(self):
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
    self.dispatch_rpc('{name}', {all_args})
"""
        return func_body.format(decorators=decorators, name=name, args=argument_declarations, returns=return_target,
                                all_args=arguments)

    @classmethod
    def create_property_synchronisation(cls, attributes):
        setter_lines = ["self.{name} = self.bge_addon.get('{name}')".format(name=name) for name in attributes]
        getter_lines = ["self.bge_addon.set('{name}', self.{name})".format(name=name) for name in attributes]

        setter_line = "\n    ".join(setter_lines)
        getter_line = "\n    ".join(getter_lines)

        func_body = \
"""
@simulated
@LogicUpdateSignal.on_global
def update(self, delta_time):
    if not self.bge_addon.alive:
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
        yield_statements = ["yield '{}'".format(attr) for attr in attributes]
        yield_body = "\n".join(yield_statements)
        return """def conditions(self, is_owner, is_complaint, is_initial):\n\t"""\
               """yield from super().conditions(is_owner, is_complaint, is_initial)\n\t{}""".format(yield_body)

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
        roles_data = dict(default="Roles(Roles.authority, {})".format(remote_role), notify=False)
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

        class_body = "\n\t".join(class_lines)

        bases_string = ", ".join(base_namespaces.keys())
        class_declaration = "class {}({}):\n\t".format(name, bases_string) + class_body

        exec(class_declaration, globals(), base_namespaces)

        return base_namespaces[name]


class ConnectionManager(SignalListener):

    def __init__(self):
        self.register_signals()

        self.pending_controllers = deque()

    @staticmethod
    def request_assignment():
        logic.sendMessage(CONTROLLER_REQUEST_MESSAGE)

    @ControllerPendingAssignmentSignal.on_global
    def on_connection(self, controller):
        self.pending_controllers.append(controller)

        # Assume no code will listen for multiple messages
        self.request_assignment()

    @ControllerAssignedSignal.on_global
    def on_assigned(self, replicable_name):
        controller = self.pending_controllers.popleft()
        cls = Replicable.from_type_name(replicable_name)
        replicable = cls(register_immediately=True)
        controller.possess(replicable)

        # If still waiting, trigger controller
        if self.pending_controllers:
            self.request_assignment()


if WITH_BGE:
    from bge import logic, types

    types.KX_PythonLogicLoop = type("", (), {})

    from bge_game_system.inputs import BGEInputManager
    from bge_game_system.physics import BGEPhysicsSystem
    from bge_game_system.definitions import BGEComponent, BGEComponentLoader

    GameObjectInjector._default_load, BGEComponentLoader.create_object = (BGEComponentLoader.create_object,
                                                                          GameObjectInjector.load)
    ResourceManager.data_path = bge.logic.expandPath("//{}".format(DATA_PATH))

    @with_tag("bge_addon")
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
            SETUP_REPLICABLES[entity] = obj

            RegisterStateSignal.invoke(self.set_network_state)

        @property
        def alive(self):
            return not self._obj.invalid

        def get(self, name):
            return self._obj[name]

        def set(self, name, value):
            self._obj[name] = value

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

                for prefix in UNIQUE_PREFIXES:
                    if message_subject.startswith(prefix):
                        break

                else:
                    continue

                name = message_subject[len(prefix):]
                message_handler.subject = prefix + dumps((name, instance_id))

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
                all_states = {1 << i for i in range(30)}
                used_states = {c.state for c in self._obj.controllers}
                try:
                    state = (all_states - used_states).pop()
                    state_index = int(log(state, 2)) + 1
                    print("{}: Using default state of {}".format(self._obj.name, state_index))
                except ValueError:
                    print("{}: Required a default empty state, none available".format(self._obj.name))

            self._obj.state = state

        def on_notify(self, event_name):
            message_id = NOTIFICATION_PREFIX + dumps((event_name, self._entity.instance_id))
            self._obj.sendMessage(message_id)
            logic.sendMessage(message_id, "")

        def dispatch_rpc(self, event_name, data):
            arguments = self._rpc_args[event_name]

            for name_, value in zip(arguments, data):
                self._obj[name_] = value

            message_id = RPC_PREFIX + dumps((event_name, self._entity.instance_id))
            self._obj.sendMessage(message_id, "", self._obj.name)

    def main():
        print("Networking enabled")

        # Load configuration
        print("Loading network information from {}".format(DATA_PATH))
        file_path = logic.expandPath("//{}".format(DATA_PATH))
        main_definition_path = path.join(file_path, "main.definition")

        with open(main_definition_path, "r") as file:
            data = load(file)

        host = data['host']
        port = data['port']
        network_tick_rate = data['tick_rate']
        metric_interval = data['metric_interval']

        configuration_file_names = [path.splitext(f)[0] for f in listdir(file_path)]

        WorldInfo.netmode = BpyResolver.resolve_netmode(data['netmode'])
        WorldInfo.tick_rate = logic.getLogicTicRate()

        print("Running as a {}".format(Netmodes[WorldInfo.netmode]))

        network = Network(host, port)
        physics_manager = BGEPhysicsSystem(no_op_func, no_op_func)
        input_manager = BGEInputManager()

        if WorldInfo.netmode == Netmodes.server:
            connection_manager = ConnectionManager()

        signal_forwarder = SignalForwarder(signal_to_message)
        state_manager = StateManager()

        print("Loading definitions from scene objects")
        for scene in logic.getSceneList():
            load_object_definitions(scene)

        # Update any subscriptions
        update_graphs()

        # Main loop
        accumulator = 0.0
        last_time = last_sent_time = clock()

        print("Game started")
        requires_exit = SignalValue(False)
        while not requires_exit.value:
            current_time = clock()

            # Determine delta time
            step_time = 1 / logic.getLogicTicRate()
            delta_time = current_time - last_time
            last_time = current_time

            # Set upper bound
            if delta_time > 0.25:
                delta_time = 0.25

            accumulator += delta_time

            # Whilst we have enough time in the buffer
            while accumulator >= step_time:
                current_time += step_time
                accumulator -= step_time
                exit_key = logic.getExitKey()

                if logic.keyboard.events[exit_key] == logic.KX_INPUT_JUST_ACTIVATED:
                    # Exit immediately!
                    if WorldInfo.netmode == Netmodes.server:
                        requires_exit.value = True

                    else:
                        quit_func = requires_exit.create_setter(True)
                        DisconnectSignal.invoke(quit_func)
                        # Else abort
                        timeout = Timer(0.6)
                        timeout.on_target = quit_func

                # Handle this outside of usual update
                if WorldInfo.netmode == Netmodes.server:
                    WorldInfo.update_clock(step_time)

                scene = logic.getCurrentScene()

                uninitialised_objects = [o for o in scene.objects if o.name in configuration_file_names
                                         and not o in SETUP_REPLICABLES.values()]

                for obj in uninitialised_objects:
                    instantiate_actor_from_obj(obj)

                network.receive()
                update_graphs()

                state_manager.update()

                bge.logic.NextFrame()

                # Catch any deleted BGE objects from BGE
                for actor in WorldInfo.subclass_of(SCA_Actor):
                    if not actor.bge_addon.alive:
                        actor.deregister(immediately=True)

                # Update Timers
                TimerUpdateSignal.invoke(step_time)

                # Update Player Controller inputs for client
                input_manager.update()

                if WorldInfo.netmode != Netmodes.server:
                    PlayerInputSignal.invoke(step_time, input_manager.state)
                    update_graphs()

                # Update main logic (Replicable update)
                LogicUpdateSignal.invoke(step_time)
                update_graphs()

                physics_manager.update(step_time)

                # Transmit new state to remote peer
                is_full_update = ((current_time - last_sent_time) >= (1 / network_tick_rate))

                if is_full_update:
                    last_sent_time = current_time

                network.send(is_full_update)

                network_metrics = network.metrics
                if network_metrics.sample_age >= metric_interval:
                    network_metrics.reset_sample_window()