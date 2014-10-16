from network.enums import Netmodes
from network.decorators import reliable, simulated, with_tag
from network.descriptors import Attribute
from network.type_flag import TypeFlag
from network.world_info import WorldInfo

from game_system import entities
from game_system.resources import ResourceManager

# Patch
import bge

bge.types.KX_PythonLogicLoop = type("", (), {})
from bge_game_system.definitions import BGEComponent

from collections import defaultdict
from json import load

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

SETUP_OBJECTS = []
SETUP_ACTORS = {}

classes = {}
configurations = {}
sorted_rpc_arguments = {}


@with_tag("addon")
class BGESetupComponent(BGEComponent):

    def __init__(self, config_section, entity, obj):
        """Initialise new network object

        :param obj: GameObject instance
        """
        self._obj = obj
        self._entity = entity

        name = obj.name
        self._rpc_args = sorted_rpc_arguments[name]

        create_unique_message_subjects(obj, entity.instance_id)

        entity.notify_handlers.append(self.notify_handler)
        entity.rpc_handlers.append(self.rpc_handler)
        # Transition to netmode state
        configuration = configurations[obj.name]
        transition_states(obj, configuration)

        SETUP_OBJECTS.append(obj)
        SETUP_ACTORS[entity] = obj

    def notify_handler(self, name):
        message_id = NOTIFICATION_PREFIX + combine_id_and_name(name, self._entity.instance_id)
        self._obj.sendMessage(message_id)

    def rpc_handler(self, name, data):
        arguments = self._rpc_args[name]

        for name_, value in zip(arguments, data):
            self._obj[name_] = value

        message_id = RPC_PREFIX + combine_id_and_name(name, self._entity.instance_id)
        self._obj.sendMessage(message_id, "", self._obj.name)


def combine_id_and_name(name, id_):
    return "{}#_#{}".format(name, id_)


def split_id_and_name(combined):
    name_str, id_str = combined.split("#_#")
    return name_str, eval(id_str)


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


register_locals = """local_dict = dict();local_dict=locals().copy()\n{}\nfunc_name = next(iter(set(locals())
                            .difference(local_dict)));cls_dict[func_name] = locals()[func_name]"""


def create_unique_message_subjects(obj, identifier):
    """Convert message sensors & actuators to use unique subjects

    :param identifier: unique identifier
    :param obj: game object
    """
    sensors = [s for s in obj.sensors if isinstance(s, bge.types.KX_NetworkMessageSensor)]
    actuators = [c for c in obj.actuators if isinstance(c, bge.types.KX_NetworkMessageActuator)]

    for message_handler in sensors + actuators:
        if not (message_handler.subject.startswith(RPC_PREFIX) or message_handler.subject.startswith(NOTIFICATION_PREFIX)):
            continue

        name = message_handler.subject[len(RPC_PREFIX):]
        message_handler.subject = RPC_PREFIX + combine_id_and_name(name, identifier)


def create_rpc(name, data):
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

    return """{reliable}{simulated}def {name}(self{args}) -> {returns}:\n\tself._dispatch_rpc('{name}', {all_args})"""\
        .format(reliable=reliable_decorator, simulated=simulated_decorator, name=name, args=args_declaration,
                returns=return_target, all_args=args_tuple)


def create_class(name, configuration):
    """Construct class from definition file

    :param name: name of class
    :param configuration: configuration data
    """
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
    """Load configuration data for GameObject

    :param name: name of GameObject
    """

    resource = ResourceManager[name]

    if resource is None:
        raise FileNotFoundError("No configuration exists for {}".format(name))

    config_path = ResourceManager.from_relative_path(resource['actor.definition'])

    with open(config_path, 'r') as file:
        loaded = load(file)

    loaded["states"] = {resolve_netmode(x): y for x, y in loaded["states"].items()}
    attributes = loaded["attributes"]
    for attr_name, data in attributes.items():
        data['type'] = resolve_type(data['type'])

    for function_name, data in loaded['rpc_calls'].items():
        data['arguments'] = {k: resolve_type(v) for k, v in data['arguments'].items()}
        data['target'] = resolve_netmode(data['target'])

    return loaded


def resolve_netmode(value):
    """Convert BPY netmode enum to constant

    :param value: enum value
    """
    if value.upper() == "SERVER":
        return Netmodes.server

    return Netmodes.client


def resolve_type(type_):
    """Convert BPY type enum to type class

    :param value: enum value
    """
    return dict(STRING=str, INT=int, BOOL=bool, FLOAT=float, TIMER=float)[type_]


def listener(cont):
    """Intercept RPC messages and route through network

    :param cont: controller instance
    """
    message_sens = next(c for c in cont.sensors if isinstance(c, bge.types.KX_NetworkMessageSensor))

    if not message_sens.positive:
        return
    
    messages = determine_rpc_calls(message_sens.subjects)

    for network_id, rpc_names in messages.items():

        try:
            actor = WorldInfo.get_replicable(network_id)
        
        except LookupError:
            continue
        
        obj = SETUP_ACTORS[actor]
        config = configurations[obj.name]
        
        rpc_info = config['rpc_calls']

        for rpc_name in rpc_names:
            rpc_args = rpc_info[rpc_name]['arguments']
            rpc_data = [obj[arg_name] for arg_name in rpc_args]
            
            getattr(actor, rpc_name)(*rpc_data)


def initialise_network_obj(obj):
    """Initialise new network object

    :param obj: GameObject instance
    """
    cls = classes[obj.name]

    Loader.pending_obj = obj

    # If we're static, this is not None
    network_id = obj.get("network_id")
    actor = cls(network_id, register_immediately=True)


def transition_states(obj, configuration):
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

        for i in range(30):
            state &= mask & ~(1 << i)
            

    obj.state = state | masks[netmode]


class ActorBase(entities.Actor):

    component_tags = tuple(entities.Actor.component_tags) + ("addon",)

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


def convert_data():
    for scene in bge.logic.getSceneList():
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

            classes[name] = create_class(name, configuration)

