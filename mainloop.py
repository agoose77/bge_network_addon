from network.annotations.decorators import reliable, simulated, get_annotation, set_annotation, requires_permission
from network.enums import Netmodes, Roles
from network.network import NetworkManager
from network.replicable import Replicable
from network.replication import Serialisable

from game_system.entity import MeshComponent
from game_system.fixed_timestep import FixedTimeStepManager, ForcedLoopExit
from game_system.resources import ResourceManager

from bge_game_system.entity.builder import EntityBuilder as _EntityBuilder
from bge_game_system.world import World as _World
from bge_game_system.scene import Scene as _Scene

from collections import defaultdict, OrderedDict, deque
from json import load
from os import path
from weakref import ref

from bge import logic, types
from actors import *
from messages import *


DATA_PATH = "network_data"
DELIMITER = ","

prefix_listener = lambda value: set_annotation("message_prefix")(value)
get_prefix_listener = lambda value: get_annotation("message_prefix")(value)


def safe_for_format(value):
    if isinstance(value, str):
        return "'{}'".format(value)

    return value


def convert_bpy_enum(value, enum):
    return getattr(enum, value.lower())


def eval_bpy_type(type_name):
    """Convert BPY type enum to type class
    :param value: enum value
    """
    return dict(STRING=str, INT=int, BOOL=bool, FLOAT=float, TIMER=float)[type_name]


def string_to_wrapped_int(string, boundary):
    value = 0

    for char in string:
        value = (value * 0x110000) + ord(char)
    return value % boundary


class ReplicableFactory:

    @classmethod
    def create_rpc_string(cls, name, data):
        """Construct RPC call from configuration data

        :param name: name of RPC call
        :param data: configuration data
        """
        arguments = data['arguments']
        argument_names = sorted(arguments)

        annotated_arguments = ["{}: {}".format(k, arguments[k].__name__) for k in argument_names]
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
        names_str = "{}{}".format(','.join(["'{}'".format(x) for x in attributes]), ',' if attributes else '')
        return """property_names = set(({}))""".format(names_str)

    @classmethod
    def create_conditions_string(cls, attributes):
        """Construct conditions generator from attribute names

        :param attributes: sequence of names of attributes
        """
        yield_by_conditions = defaultdict(list)

        for attr_name, data in attributes.items():
            conditions = []
            if data['initial_only']:
                conditions.append("is_initial")

            if data['ignore_owner']:
                conditions.append("not is_owner")

            conditions_key = tuple(conditions)
            yield_by_conditions[conditions_key].append(attr_name)

        body_statements = []
        for conditions, attr_names in yield_by_conditions.items():
            if conditions:
                body_statements.append("if {}:".format(" and ".join(conditions)))
                for attr_name in attr_names:
                    body_statements.append("    yield '{}'".format(attr_name))

            else:
                for attr_name in attr_names:
                    body_statements.append("yield '{}'".format(attr_name))

        yield_body = "\n    ".join(body_statements)
        return """def can_replicable(self, is_owner, is_initial):\n"""\
               """    yield from super().can_replicable(is_owner, is_initial)\n    {}""".format(yield_body)

    @classmethod
    def create_attribute_string(cls, name, data, is_raw=False):
        default = data['default']
        if not is_raw:
            default = safe_for_format(default)

        return "{} = Serialisable({}, notify_on_replicated=True)".format(name, default)

    @classmethod
    def load_base_class(cls, base_class_path):
        *module_path, class_name = base_class_path.split(".")

        try:
            module = __import__('.'.join(module_path), fromlist=[''])
        except ImportError as err:
            raise ImportError("Couldn't import template: {}".format(base_class_path)) from err

        try:
            new_cls = getattr(module, class_name)

        except AttributeError as err:
            raise AttributeError("Template module {}.py has no class {}".format(module.__name__, class_name)) \
                from err

        return new_cls

    @classmethod
    def from_configuration(cls, raw_name, configuration):
        """Construct class from definition file

        :param name: name of class
        :param configuration: configuration data
        """
        name = raw_name.replace(".", "_")
        assert name.isidentifier()

        class_lines = ["mesh = MeshComponent('{}')".format(raw_name)]

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

        base_class_import_path = configuration['template']
        if base_class_import_path is None:
            base_name = "SCAActor"
            namespace = {}
        else:
            base_class = cls.load_base_class(base_class_path=configuration['template'])
            base_name = base_class.__name__
            namespace = {base_name: base_class}

        class_declaration = "class {}({}):\n    ".format(name, base_name) + class_body

        print(class_declaration)
        exec(class_declaration, globals(), namespace)
        return namespace[name]


class ControllerManager:

    def __init__(self, scene):
        self.pending_controllers = deque()
        self._instigator_to_pawn = {}
        self.scene = scene

    @staticmethod
    def request_assignment():
        logic.sendMessage(message_subjects['CONTROLLER_REQUEST'], '<internal>')

    def on_new_controller(self, controller):
        self.pending_controllers.append(controller)

        # Assume no code will listen for multiple messages
        self.request_assignment()

    def on_reassigned_pawn(self, old_pawn, replicable_class_name):
        try:
            replicable_cls = Replicable[replicable_class_name]

        except KeyError:
            print("Controller pawn assignment requires valid object name, not {}".format(replicable_class_name))
            return

        controller = old_pawn.root

        if controller is None:
            print("Cannot reassign pawn from network object with no controller")
            return

        assert old_pawn is controller.pawn
        controller.release_control()

        # We know old pawn has game object
        bge_obj = old_pawn.game_object

        self._assign_new_pawn(controller, bge_obj, replicable_cls)

        # Remove old pawn
        self.scene.remove_replicable(old_pawn)

    def on_assigned_pawn(self, bge_obj, replicable_class_name):
        controller = self.pending_controllers.popleft()
        replicable_cls = Replicable[replicable_class_name]

        self._assign_new_pawn(controller, bge_obj, replicable_cls)

        # If still waiting, trigger controller
        if self.pending_controllers:
            self.request_assignment()

    def send_to_new_pawn(self, instigator, message):
        pawn = self._instigator_to_pawn[instigator]
        pawn.receive_prefixed_message(message_prefixes_replicable['SELF_MESSAGE'], message)

    def _assign_new_pawn(self, instigator, controller, replicable_cls):
        pawn = self.scene.add_replicable(replicable_cls)
        controller.take_control(pawn)

        # Remember who created this pawn
        self._instigator_to_pawn[instigator] = pawn

        # Send ONLY to this object (avoid positive feedback)
        self.send_to_new_pawn(instigator, "init")
        return pawn


class EntityBuilder(_EntityBuilder):

    def __init__(self, bge_scene, empty_name="Empty", camera_name="Camera"):
        super().__init__(bge_scene, empty_name, camera_name)

        self.entity_configuration_info = {}
        self.sorted_rpc_argument_info = {}

    def create_object(self, entity, object_name):
        obj = super().create_object(entity, object_name)

        # Set network states
        configuration = self.entity_configuration_info[object_name]

        entity.rpc_arguments = self.sorted_rpc_argument_info[object_name]
        entity.states = configuration['states']
        entity.game_object = obj
        entity.set_network_states(just_initialised=True)

        obj["_entity"] = ref(entity)

        return obj

    def unload_entity(self, entity):
        obj = self.entity_to_game_obj[entity]
        del obj["_entity"]

        super().unload_entity(entity)


class Scene(_Scene):

    def __init__(self, world, name):
        super().__init__(world, name)

        self.entity_builder = EntityBuilder(self.bge_scene)
        self.entity_classes = {}

        self.controller_manager = ControllerManager(self)

        self._load_configuration_files()
        self._convert_message_logic()

    def cull_invalid_objects(self):
        to_remove = []
        for entity in self.entity_builder.entity_to_game_obj.keys():
            if not entity.is_alive:
                to_remove.append(entity)

        for entity in to_remove:
            self.remove_replicable(entity)

    def _convert_message_logic(self):
        objects = list(self.bge_scene.objects)
        objects.extend(self.bge_scene.objectsInactive)

        for obj in objects:
            self._convert_object_message_logic(obj)

    def _convert_object_message_logic(self, obj):
        from bge import types

        message_scene = message_prefixes_scene["SCENE_MESSAGE"]

        # Convert sensors
        sensors = [s for s in obj.sensors if isinstance(s, types.KX_NetworkMessageSensor)]
        for message_handler in sensors:
            message_subject = message_handler.subject

            for prefix in message_prefixes_scene.values():
                if message_subject.startswith(prefix):
                    break

            else:
                continue

            name = message_subject[len(prefix):]
            message_handler.subject = prefix + encode_scene_info(name, self)

            # Subscribe to messages
            if prefix == message_scene:
                self.messenger.add_subscriber(name, partial(self.receive_prefixed_message, prefix, name))

        # Convert actuators
        actuators = [c for c in obj.actuators if isinstance(c, types.KX_NetworkMessageActuator)]
        for message_handler in actuators:
            message_subject = message_handler.subject

            for prefix in message_prefixes_scene.values():
                if message_subject.startswith(prefix):
                    break

            else:
                continue

            name = message_subject[len(prefix):]
            message_handler.subject = prefix + encode_object(encode_scene_info(name, self), obj)

    def receive_prefixed_message(self, prefix, subject):
        """Send message to a specific instance that won't be picked up as a broadcast

        :param prefix: prefix of subject
        :param subject: subject of message
        """
        modified_subject = encode_scene_info(subject, self)
        logic.sendMessage(prefix + modified_subject, "<invalid>")

    def _load_configuration_files(self):
        bge_scene = self.bge_scene
        open_json = self.resource_manager.open_json

        sorted_rpc_argument_info = self.entity_builder.sorted_rpc_argument_info
        entity_configuration_info = self.entity_builder.entity_configuration_info
        entity_classes = self.entity_classes

        for obj in list(bge_scene.objects) + list(bge_scene.objectsInactive):
            name = obj.name

            definition_path = "{}/actor.definition".format(name)

            try:
                actor_definition = open_json(definition_path)

            except FileNotFoundError:
                continue

            configuration = self._parse_configuration(actor_definition)
            entity_configuration_info[name] = configuration
            sorted_rpc_argument_info[name] = {rpc_name: sorted(data['arguments']) for rpc_name, data in
                                              configuration['rpc_calls'].items()}

            entity_classes[name] = ReplicableFactory.from_configuration(name, configuration)

    @staticmethod
    def _parse_configuration(actor_definition):
        definition = actor_definition.copy()

        definition["states"] = {convert_bpy_enum(x, Netmodes): y for x, y in definition["states"].items()}

        for function_name, data in definition['rpc_calls'].items():
            data['arguments'] = {k: eval_bpy_type(v) for k, v in data['arguments'].items()}
            data['target'] = convert_bpy_enum(data['target'], Netmodes)

        definition['remote_role'] = convert_bpy_enum(definition['remote_role'], Roles)

        return definition


class World(_World):

    scene_class = Scene


class GameLoop(FixedTimeStepManager):

    def __init__(self):
        super().__init__()

        self.pending_exit = False

        # Set default step function
        self.on_step = self.step_default

        print("Waiting for netmode assignment message")

        self.world = None

        self.listeners = defaultdict(list)
        self._messages = []

        self.add_global_listener('SET_NETMODE', self._on_set_netmode)

    def set_netmode(self, netmode):
        # Load configuration
        print("Loading network information from {}".format(DATA_PATH))
        file_path = logic.expandPath("//{}".format(DATA_PATH))
        # self.configuration_file_names = {path.splitext(f)[0] for f in listdir(file_path)}
        main_definition_path = path.join(file_path, "main.definition")

        # Load network information
        with open(main_definition_path, "r") as file:
            world_settings = load(file)

        self.network_update_interval = 1 / world_settings['tick_rate']
        self.metric_interval = world_settings['metric_interval']

        self.world = World(netmode, logic.getLogicTicRate(), file_path)
        logic.world = self.world

        self.network_manager = NetworkManager(self.world, "",
                                              (world_settings['port'] if netmode==Netmodes.server else 0))

        # Time since last sent
        self.time_since_sent = 0.0

        # Set network as active update function
        self.on_step = self.step_network
        self.cleanup = lambda: self.network_manager.stop()

        self.add_replicable_listener('METHOD_INVOKE', self._on_invoke_method)
        self.add_replicable_listener('RPC_INVOKE', self._on_invoke_rpc)
        self.add_replicable_listener('CONTROLLER_REASSIGN', self._on_controller_reassign)
        self.add_replicable_listener('SELF_MESSAGE', self._on_self_message)

        self.add_scene_listener('SCENE_MESSAGE', self._on_scene_message)
        self.add_scene_listener('CONTROLLER_ASSIGN', self._on_controller_assign)

        self.add_global_listener('CONNECT_TO', self._on_connect_to)

        # Set network state
        self._update_network_state()

        logic.sendMessage("NETWORK_INIT", "<invalid>")

        print("Network started")

    def add_replicable_listener(self, name, func):
        prefix = message_prefixes_replicable[name]
        self.listeners[prefix].append(func)

    def add_scene_listener(self, name, func):
        prefix = message_prefixes_scene[name]
        self.listeners[prefix].append(func)

    def add_global_listener(self, name, func):
        prefix = message_prefixes_global[name]
        self.listeners[prefix].append(func)

    def handle_messages(self, messages):
        self._messages.extend(messages)

    def _process_messages(self):
        messages = self._messages[:]
        self._messages.clear()

        prefix_listeners = self.listeners
        world = self.world

        global_prefixes = set(message_prefixes_global.values())
        replicable_prefixes = set(message_prefixes_replicable.values())

        # Lower priority
        non_global_messages = []

        for subject, body in messages:
            starts_with = subject.startswith

            # Ignore internal messages
            if body == "<internal>":
                continue

            for prefix, listeners in prefix_listeners.copy().items():
                if starts_with(prefix):
                    following_prefix = subject[len(prefix):]

                    if prefix in global_prefixes:
                        for listener in listeners:
                            listener(following_prefix)

                    elif prefix in replicable_prefixes:
                        subject, replicable = decode_replicable_info(world, following_prefix)

                        non_global_messages.append((listeners, (replicable, subject)))

                    # Scene message
                    else:
                        encoded_scene_info, obj = decode_object(following_prefix)

                        subject, scene = decode_scene_info(world, encoded_scene_info)

                        non_global_messages.append((listeners, (scene, obj, subject)))

        for listeners, args in non_global_messages:
            for listener in listeners:
                listener(*args)

    def _on_connect_to(self, target):
        ip_address, port = target.split("::")
        if not ip_address:
            ip_address = "localhost"

        port = int(port)

        self.network_manager.connect_to(ip_address, port)
        print("CONNECT")

    def _on_set_netmode(self, netmode_name):
        try:
            netmode = getattr(Netmodes, netmode_name)

        except AttributeError:
            print("Couldn't set netmode as {}".format(netmode_name))
            return

        if self.world is not None:
            print("Netmode is already set!")
            return

        self.set_netmode(netmode)

    def _on_scene_message(self, scene, from_obj, message_name):
        scene.messenger.send(message_name)

    def _on_controller_assign(self, scene, from_obj, replicable_class_name):
        """Handle connection controller initial pawn assignment"""
        scene.controller_manager.on_assigned_pawn(from_obj, replicable_class_name)

    def _on_self_message(self, replicable, method_name):
        replicable.messenger.send(method_name)

    def _on_invoke_method(self, replicable, method_name):
        """Handle RPC messages"""
        getattr(replicable, method_name)()

    def _on_invoke_rpc(self, replicable, rpc_name):
        """Handle RPC messages"""
        replicable.invoke_rpc(rpc_name)

    def _on_controller_reassign(self, replicable, replicable_class_name):
        """Handle connection controller subsequent pawn assignment"""
        replicable.scene.controller_manager.on_reassigned_pawn(replicable, replicable_class_name)

    def _on_new_pawn(self, replicable, message_name):
        replicable.scene.controller_manager.send_to_new_pawn(replicable, message_name)

    @property
    def time_step(self):
        return 1 / logic.getLogicTicRate()

    def post_initialise(self, replication_manager):
        logic.sendMessage('CREATE_PAWN', '<invalid>')

    def check_exit(self):
        # Handle exit
        exit_key = logic.getExitKey()

        # Check if exit key is pressed
        if logic.keyboard.events[exit_key] == logic.KX_INPUT_JUST_ACTIVATED:

            # Exit immediately!
            if not self.world or (self.world.netmode == Netmodes.server):
                raise ForcedLoopExit("Exit key pressed")

            else:
                self.world.messenger.send("pending_disconnect") # TODO trigger disconnect request

                def quit_game():
                    raise ForcedLoopExit("Disconnect timed out")

                # Else abort
                timeout = self.world.timer_manager.add_timer(0.6)
                timeout.on_elapsed = quit_game

    def step_default(self, delta_time):
        logic.NextFrame()

        # Process received messages from logic.NextFrame()
        self._process_messages()

        # Check if exit is required
        self.check_exit()

    def _update_network_state(self):
        # Initialise network objects if they're added
        for bge_scene in logic.getSceneList():
            scene_name = bge_scene.name

            # Initialise scene if it doesn't exist
            try:
                scene = self.world.scenes[scene_name]

            except KeyError:
                scene = self.world.add_scene(scene_name)

            to_create_dynamic = []
            to_create_static = []

            for obj in bge_scene.objects:
                if "_entity" in obj:
                    continue

                obj_name = obj.name
                if obj_name in scene.entity_classes:
                    if obj_name in bge_scene.objectsInactive:
                        to_create_dynamic.append(obj_name)

                    else:
                        to_create_static.append(obj_name)

            # Create static replicables
            to_create_static.sort()

            for i, new_obj_name in enumerate(to_create_static):
                replicable_cls = scene.entity_classes[new_obj_name]
                scene.add_replicable(replicable_cls, unique_id=i)

            for new_obj_name in to_create_dynamic:
                replicable_cls = scene.entity_classes[new_obj_name]
                scene.add_replicable(replicable_cls)

            scene.cull_invalid_objects()

    def step_network(self, delta_time):
        self.time_since_sent += delta_time

        self.network_manager.receive()

        # Update BGE gameloop
        logic.NextFrame()

        self._update_network_state()

        # Process received messages from logic.NextFrame()
        self._process_messages()

        self.world.tick()

        # Transmit new state to remote peer
        is_full_update = (self.time_since_sent >= self.network_update_interval)

        self.network_manager.send(is_full_update)

        if is_full_update:
            self.time_since_sent = 0.0

        # Update network metrics
        network_metrics = self.network_manager.metrics
        if network_metrics.sample_age >= self.metric_interval:
            network_metrics.reset_sample_window()

        # Check if exit is required
        self.check_exit()


def main():
    game_loop = GameLoop()
    logic.game_loop = game_loop
    game_loop.run()


def listener(cont):
    """Dispatch messages to listeners

    :param cont: controller instance
    """
    message_sens = next(c for c in cont.sensors if isinstance(c, types.KX_NetworkMessageSensor))

    if not message_sens.positive:
        return

    subjects = message_sens.subjects
    bodies = message_sens.bodies
    messages = list(zip(subjects, bodies))

    logic.game_loop.handle_messages(messages)


