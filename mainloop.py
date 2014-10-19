from network.descriptors import Attribute
from network.decorators import with_tag, reliable, simulated
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


from collections import defaultdict, OrderedDict
from json import load, loads, dumps
from os import path, listdir
from time import clock


try:
    import bge

except ImportError:
    WITH_BGE = False

else:
    WITH_BGE = True


RPC_PREFIX = "RPC_"
NOTIFICATION_PREFIX = "NOTIFY_"
TARGETED_SIGNAL_PREFIX = "SIGNAL_"
GLOBAL_SIGNAL_PREFIX = "GLOBAL_SIGNAL_"
UNIQUE_PREFIXES = RPC_PREFIX, NOTIFICATION_PREFIX, TARGETED_SIGNAL_PREFIX
DATA_PATH = "network_data"

DELIMITER = ","


SETUP_REPLICABLES = {}
classes = {}
configurations = {}
sorted_rpc_arguments = {}


class SCA_Actor(_Actor):
    """Interface for SCA_ system with network system"""

    component_tags = tuple(_Actor.component_tags) + ("addon",)

    def on_notify(self, name):
        for handler in self.notify_handlers:
            handler(name)

    def on_initialised(self):
        super().on_initialised()

        self.rpc_handlers = []
        self.notify_handlers = []

    def _dispatch_rpc(self, name, data):
        for handler in self.rpc_handlers:
            handler(name, data)

    def update(self, delta_time):
        pass


class BpyResolver:

    @staticmethod
    def resolve_netmode(value):
        """Convert BPY netmode enum to constant

        :param value: enum value
        """
        if value.upper() == "SERVER":
            return Netmodes.server

        return Netmodes.client

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


def determine_rpc_calls(subjects):
    """Extract message subjects which belong to RPC calls

    :param subjects: message subjects
    """
    messages = defaultdict(list)
    for subject in subjects:
        if not subject.startswith(RPC_PREFIX):
            continue

        combined = subject[len(RPC_PREFIX):]
        name, id_ = loads(combined)
        messages[id_].append(name)

    return messages


def instantiate_actor_from_obj(obj):
    cls = classes[obj.name]

    GameObjectInjector.game_object = obj
    # If we're static, this is not None
    network_id = obj.get("network_id")
    return cls(network_id, register_immediately=True)


def load_configuration(name):
    """Load configuration data for GameObject

    :param name: name of GameObject
    """

    resource = ResourceManager[name]

    if resource is None:
        raise FileNotFoundError("No configuration exists for {}".format(name))

    config_path = ResourceManager.from_relative_path(resource['actor.definition'])

    with open(config_path, 'r') as file:
        loaded = load(file)

    loaded["states"] = {BpyResolver.resolve_netmode(x): y for x, y in loaded["states"].items()}

    for function_name, data in loaded['rpc_calls'].items():
        data['arguments'] = {k: BpyResolver.resolve_type(v) for k, v in data['arguments'].items()}
        data['target'] = BpyResolver.resolve_netmode(data['target'])

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


if WITH_BGE:
    from bge import logic, types

    types.KX_PythonLogicLoop = type("", (), {})
    from bge_game_system.definitions import BGEComponent, BGEComponentLoader

    GameObjectInjector._default_load, BGEComponentLoader.create_object = (BGEComponentLoader.create_object,
                                                                          GameObjectInjector.load)
    ResourceManager.data_path = bge.logic.expandPath("//{}".format(DATA_PATH))

    def listener(cont):
        """Intercept RPC messages and route through network

        :param cont: controller instance
        """
        message_sens = next(c for c in cont.sensors if isinstance(c, types.KX_NetworkMessageSensor))

        if not message_sens.positive:
            return

        messages = determine_rpc_calls(message_sens.subjects)
        for network_id, rpc_names in messages.items():

            try:
                replicable = WorldInfo.get_replicable(network_id)

            except LookupError:
                continue

            obj = SETUP_REPLICABLES[replicable]
            config = configurations[obj.name]

            rpc_info = config['rpc_calls']

            for rpc_name in rpc_names:
                rpc_args = rpc_info[rpc_name]['arguments']
                rpc_data = [obj[arg_name] for arg_name in rpc_args]

                getattr(replicable, rpc_name)(*rpc_data)

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

    class SignalForwarder(SignalListener):
        """Forward all globally available signals to handler"""

        def __init__(self, handler):
            self.register_signals()

            self._handler = handler

        @Signal.global_listener
        def handle_signal(self, *args, signal, target, **kwargs):
            self._handler(signal, *args, signal=signal, target=target, **kwargs)

    @with_tag("addon")
    class BGESetupComponent(BGEComponent):

        def __init__(self, config_section, entity, obj):
            """Initialise new network object

            :param obj: GameObject instance
            """
            self._rpc_args = sorted_rpc_arguments[obj.name]
            self._entity = entity
            self._obj = obj

            entity.notify_handlers.append(self.notify_handler)
            entity.rpc_handlers.append(self.rpc_handler)

            # Transition to netmode state
            configuration = configurations[obj.name]

            self.set_network_state(obj, configuration)
            self.convert_message_logic(obj, entity.instance_id)

            SETUP_REPLICABLES[entity] = obj

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
        def set_network_state(obj, configuration):
            """Unset any states from other netmodes, then set correct states

            :param obj: GameObject
            :param configuration: configuration data
            """
            masks = configuration['states']
            netmode = WorldInfo.netmode

            state = obj.state
            for mask_netmode, mask in masks.items():
                if mask_netmode == netmode:
                    continue

                state &=~ mask

            obj.state = state | masks[netmode]

        def notify_handler(self, event_name):
            message_id = NOTIFICATION_PREFIX + dumps((event_name, self._entity.instance_id))
            self._obj.sendMessage(message_id)
            logic.sendMessage(message_id, "")

        def rpc_handler(self, event_name, data):
            arguments = self._rpc_args[event_name]

            for name_, value in zip(arguments, data):
                self._obj[name_] = value

            message_id = RPC_PREFIX + dumps((event_name, self._entity.instance_id))
            self._obj.sendMessage(message_id, "", self._obj.name)

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
            args_declaration = ", {}".format(','.join(annotated_arguments)) if argument_names else ""
            args_tuple = "({}{})".format(','.join(argument_names), ',' if argument_names else '')

            is_reliable = data['reliable']
            is_simulated = data['simulated']
            return_target = data['target']

            reliable_decorator = "@reliable\n" if is_reliable else ""
            simulated_decorator = "@simulated\n" if is_simulated else ""

            return """{reliable}{simulated}def {name}(self{args}) -> {returns}:\n\t"""\
                   """self._dispatch_rpc('{name}', {all_args})"""\
                .format(reliable=reliable_decorator, simulated=simulated_decorator, name=name, args=args_declaration,
                        returns=return_target, all_args=args_tuple)

        @classmethod
        def create_property_synchronisation(cls, attributes):
            setter_lines = ["self.{name} = self.addon.get('{name}')".format(name=name) for name in attributes]
            getter_lines = ["self.addon.set('{name}', self.{name})".format(name=name) for name in attributes]
            switch = "if self.roles.local == Roles.authority:\n\t\t" + "\n\t\t".join(setter_lines)
            switch += "\n\telse:\n\t\t" + "\n\t\t".join(getter_lines)

            return """@simulated\n@LogicUpdateSignal.global_listener\ndef update(self, delta_time):"""\
                   """\n\t{}\n\tsuper().update(delta_time)"""\
                .format(switch)

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
        def create_attribute_string(cls, name, data):
            return "{} = Attribute({}, notify={})".format(name, data['default'], data['notify'])

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

            namespace['SCA_Actor'] = SCA_Actor
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
            class_lines.extend(attribute_definitions)
            rpc_calls = configuration['rpc_calls']
            rpc_definitions = [cls.create_rpc_string(function_name, data) for function_name, data in rpc_calls.items()]
            class_lines.extend([y for c in rpc_definitions for y in c.split("\n")])

            conditions_definition = cls.create_conditions_string(attributes)
            class_lines.extend(conditions_definition.split("\n"))

            if attributes:
                sync_definition = cls.create_property_synchronisation(attributes)
                class_lines.extend(sync_definition.split("\n"))

            class_body = "\n\t".join(class_lines)

            bases_string = ", ".join(base_namespaces.keys())
            class_declaration = "class {}({}):\n\t".format(name, bases_string) + class_body

            exec(class_declaration, globals(), base_namespaces)

            return base_namespaces[name]

    def main():
        # Load configuration
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

        network = Network(host, port)
        signal_forwarder = SignalForwarder(signal_to_message)

        # Main loop
        accumulator = 0.0
        last_time = last_sent_time = clock()

        requires_exit = SignalValue(False)

        for scene in logic.getSceneList():
            load_object_definitions(scene)

        # Fixed time-step
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

                exit_key = logic.getExitKey()

                if logic.keyboard.events[exit_key] == logic.KX_INPUT_JUST_ACTIVATED:
                    # Exit immediately!
                    if WorldInfo.netmode == Netmodes.server:
                        requires_exit.value = True

                    else:
                        quit_func = lambda: setattr(requires_exit, "value", True)
                        DisconnectSignal.invoke(quit_func)
                        # Else abort
                        timeout = Timer(0.6)
                        timeout.on_target = quit_func

                # Handle this outside of usual update
                WorldInfo.update_clock(step_time)

                scene = logic.getCurrentScene()

                uninitialised_objects = [o for o in scene.objects if o.name in configuration_file_names
                                         and not o in SETUP_REPLICABLES.values()]

                for obj in uninitialised_objects:
                    instantiate_actor_from_obj(obj)

                network.receive()
                update_graphs()

                # Update Timers
                TimerUpdateSignal.invoke(step_time)

                # Update Player Controller inputs for client
                if WorldInfo.netmode != Netmodes.server:
                    PlayerInputSignal.invoke(step_time)
                    update_graphs()

                # Update main logic (Replicable update)
                LogicUpdateSignal.invoke(step_time)
                update_graphs()

                bge.logic.NextFrame()

                # Transmit new state to remote peer
                is_full_update = ((current_time - last_sent_time) >= (1 / network_tick_rate))

                if is_full_update:
                    last_sent_time = current_time

                network.send(is_full_update)

                network_metrics = network.metrics
                if network_metrics.sample_age >= metric_interval:
                    network_metrics.reset_sample_window()

                current_time += step_time
                accumulator -= step_time