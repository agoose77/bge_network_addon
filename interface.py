from network.enums import Netmodes
from network.decorators import reliable, simulated
from network.descriptors import Attribute
from network.network import Network
from network.replicable import Replicable
from network.signals import SignalValue, DisconnectSignal, Signal
from network.type_flag import TypeFlag
from network.world_info import WorldInfo

from game_system import entities
from game_system.resources import ResourceManager
from game_system.signals import LogicUpdateSignal, TimerUpdateSignal, PlayerInputSignal
from game_system.timer import Timer

# Patch
import bge

bge.types.KX_PythonLogicLoop = type("", (), {})
import bge_game_system

from collections import defaultdict
from json import load
from time import clock

RPC_PREFIX = "RPC_"
NOTIFICATION_PREFIX = "NOTIFY_"

DATA_PATH = "network_data"
ResourceManager.data_path = bge.logic.expandPath("//{}".format(DATA_PATH))

BGEComponentLoader = entities.ComponentLoader().__class__


# Entity loader
class Loader:

    pending_obj = None

    @classmethod
    def load(cls, definition):
        if cls.pending_obj is not None:
            _pending_obj, cls.pending_obj = cls.pending_obj, None
            return _pending_obj

        return cls._default_load(definition)

    _default_load = BGEComponentLoader.create_object


BGEComponentLoader.create_object = Loader.load


def combine_id_and_name(name, id_):
    return "{}#_#{}".format(name, id_)


def split_id_and_name(combined):
    name_str, id_str = combined.split("#_#")
    return name_str, eval(id_str)


def get_object(actor):
    return actor._BGE_OBJECT


def get_configuration(obj):
    pass


def determine_rpc_calls(subjects):
    messages = defaultdict(list)
    for subject in subjects:
        if not subject.startswith(RPC_PREFIX):
            continue

        combined = subject[len(RPC_PREFIX):]
        name, id_ = split_id_and_name(combined)
        messages[id_].append(name)

    return messages


classes = {}
configurations = {}
sorted_rpc_arguments = {}

register_locals = """local_dict = dict();local_dict=locals().copy()\n{}\nfunc_name = next(iter(set(locals())
                            .difference(local_dict)));cls_dict[func_name] = locals()[func_name]"""


def convert_message_listeners(actor, obj):
    sensors = [s for s in obj.sensors if isinstance(s, bge.types.KX_NetworkMessageSensor)]
    actuators = [c for c in obj.actuators if isinstance(c, bge.types.KX_NetworkMessageActuator)]

    instance_id = actor.instance_id

    for message_handler in sensors + actuators:
        if not (message_handler.subject.startswith(RPC_PREFIX) or message_handler.subject.startswith(NOTIFICATION_PREFIX)):
            continue

        name = message_handler.subject[len(RPC_PREFIX):]
        message_handler.subject = RPC_PREFIX + combine_id_and_name(name, instance_id)


def create_rpc(name, data):
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

    return """{reliable}{simulated}def {name}(self{args}) -> {returns}:\n\tself._dispatch_rpc('{name}', {all_args})"""\
        .format(reliable=reliable_decorator, simulated=simulated_decorator, name=name, args=args_declaration,
                returns=return_target, all_args=args_tuple)


def create_class(name, configuration):
    base_paths = configuration['templates']

    bases = [ActorBase]
    for class_path in base_paths:
        *module_path, class_name = class_path.split(".")
        try:
            module = __import__('.'.join(module_path))
        except ImportError as err:
            raise ImportError("Couldn't import template: {}".format(class_path)) from err
        
        try:
            cls = getattr(module, class_name)
        except AttributeError as err:
            raise AttributeError("Template module {}.py has no class {}".format(module.__name__, class_name)) from err
            
        bases.append(cls)

    cls_dict = {}

    attributes = configuration['attributes']

    for attribute_name, data in attributes.items():
        cls_dict[attribute_name] = Attribute(type_of=data['type'], notify=data['notify'])

    for function_name, data in configuration['rpc_calls'].items():
        rpc_definition = create_rpc(function_name, data)
        register_string = register_locals.format(rpc_definition)

        exec(register_string)
    
    return type(name, tuple(bases), cls_dict)


def load_configuration(name):
    config_path = ResourceManager.from_relative_path(ResourceManager[name]['actor.definition'])

    with open(config_path, 'r') as file:
        loaded = load(file)

    loaded["states"] = {int(x): y for x, y in loaded["states"].items()}

    attributes = loaded["attributes"]
    for attr_name, data in attributes.items():
        data['type'] = resolve_type(data['type'])

    for function_name, data in loaded['rpc_calls'].items():
        data['arguments'] = {k: resolve_type(v) for k, v in data['arguments'].items()}
        data['target'] = resolve_netmode(data['target'])

    return loaded


def resolve_netmode(value):
    if value == "SERVER":
        return Netmodes.server

    return Netmodes.client


def resolve_type(type_):
    return dict(STRING=str, INT=int, BOOL=bool, FLOAT=float, TIMER=float)[type_]


def listener(cont):
    message_sens = next(c for c in cont.sensors if isinstance(c, bge.types.KX_NetworkMessageSensor))

    if not message_sens.positive:
        return
    
    messages = determine_rpc_calls(message_sens.subjects)

    for network_id, rpc_names in messages.items():

        try:
            actor = WorldInfo.get_replicable(network_id)
        
        except LookupError:
            continue
        
        obj = get_object(actor)
        config = configurations[obj.name]
        
        rpc_info = config['rpc_calls']

        for rpc_name in rpc_names:
            rpc_args = rpc_info[rpc_name]['arguments']
            rpc_data = [obj[arg_name] for arg_name in rpc_args]
            
            getattr(actor, rpc_name)(*rpc_data)


def initialise_network_obj(own):
    name = own.name

    if name in classes:
        cls = classes[name]

    else:
        configuration = load_configuration(name)
        configurations[name] = configuration
        cls = classes[name] = create_class(name, configuration)

        sorted_rpc_arguments[name] = {rpc_name: sorted(data['arguments']) for rpc_name, data in
                                      configuration['rpc_calls'].items()}

    Loader.pending_obj = own

    # If we're static, this is not None
    network_id = own.get("network_id")
    actor = cls(network_id)

    def notify_handler(name):
        message_id = NOTIFICATION_PREFIX + combine_id_and_name(name, actor.instance_id)
        own.sendMessage(message_id)

    rpc_args = sorted_rpc_arguments[name]

    def rpc_handler(name, data):
        arguments = rpc_args[name]

        for name_, value in zip(arguments, data):
            own[name_] = value

        message_id = RPC_PREFIX + combine_id_and_name(name, actor.instance_id)
        own.sendMessage(message_id, "", own.name)

    convert_message_listeners(actor, own)

    actor.notify_handlers.append(notify_handler)
    actor.rpc_handlers.append(rpc_handler)

    actor._BGE_OBJECT = own
    own.state = configuration['states'][WorldInfo.netmode]


def update_graphs():
    """Update isolated resource graphs"""
    Replicable.update_graph()
    Signal.update_graph()


class ActorBase(entities.Actor):

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


def main():
    # Load configuration
    file_path = bge.logic.expandPath("//{}/{}".format(DATA_PATH, "main.definition"))
    with open(file_path, "r") as file:
        data = load(file)

    host = data['host']
    port = data['port']
    network_tick_rate = data['tick_rate']
    metric_interval = data['metric_interval']

    scenes_data = data['scenes']

    WorldInfo.netmode = Netmodes.server if data['netmode'] == "SERVER" else Netmodes.client
    WorldInfo.tick_rate = bge.logic.getLogicTicRate()

    network = Network(host, port)

    # Main loop
    accumulator = 0.0
    last_time = last_sent_time = clock()

    requires_exit = SignalValue(False)
    handled_ids = []

    # Fixed time-step
    while not requires_exit.value:
        current_time = clock()

        # Determine delta time
        step_time = 1 / bge.logic.getLogicTicRate()
        delta_time = current_time - last_time
        last_time = current_time

        # Set upper bound
        if delta_time > 0.25:
            delta_time = 0.25

        accumulator += delta_time

        # Whilst we have enough time in the buffer
        while accumulator >= step_time:

            exit_key = bge.logic.getExitKey()

            if bge.logic.keyboard.events[exit_key] == bge.logic.KX_INPUT_JUST_ACTIVATED:
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

            scene = bge.logic.getCurrentScene()
            scene_data = scenes_data[scene.name]

            uninitialised_objects = [o for o in scene.objects if o.name in scene_data and not id(o) in handled_ids]

            for obj in uninitialised_objects:
                initialise_network_obj(obj)
                handled_ids.append(id(obj))

            network.receive()
            update_graphs()

            # Update Timers
            TimerUpdateSignal.invoke(delta_time)

            # Update Player Controller inputs for client
            if WorldInfo.netmode != Netmodes.server:
                PlayerInputSignal.invoke(delta_time)
                update_graphs()

            # Update main logic (Replicable update)
            LogicUpdateSignal.invoke(delta_time)
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


if __name__ == "__main__":
    main()