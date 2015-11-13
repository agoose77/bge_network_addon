from network.annotations.decorators import reliable, simulated, requires_permission
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

from collections import defaultdict, deque
from functools import partial
from json import load
from os import path
from weakref import ref

from bge import logic, types
from actors import *
from messages import *
from rules import Rules


DATA_PATH = "network_data"


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
        return """def can_replicate(self, is_owner, is_initial):\n"""\
               """    yield from super().can_replicate(is_owner, is_initial)\n    {}""".format(yield_body)

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
        self._instigator_to_pawn = {}

        self.scene = scene

    def on_reassigned_pawn(self, old_pawn, replicable_class_name):
        try:
            replicable_cls = Replicable.subclasses[replicable_class_name]

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

        self._assign_new_pawn(bge_obj, controller, replicable_cls)

        # Remove old pawn
        self.scene.remove_replicable(old_pawn)

    def on_assigned_pawn(self, bge_obj, replicable_class_name):
        replicable_cls = Replicable.subclasses[replicable_class_name]

        controller = self.scene.add_replicable(SCAPlayerPawnController)
        replication_manager = self.scene.get_pending_connection_info()

        replication_manager.set_root_for_scene(self.scene, controller)

        # Create and move pawn to creator!
        pawn = self._assign_new_pawn(bge_obj, controller, replicable_cls)
        pawn.transform.world_position = bge_obj.worldPosition
        pawn.transform.world_orientation = bge_obj.worldOrientation.to_quaternion()

    def send_to_new_pawn(self, instigator, message):
        pawn = self._instigator_to_pawn[instigator]
        pawn.receive_identified_message('SELF_MESSAGE', message)

    def _assign_new_pawn(self, instigator, controller, replicable_cls):
        pawn = self.scene.add_replicable(replicable_cls)
        controller.take_control(pawn)
        pawn.owner = controller

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


class Scene(_Scene):

    def __init__(self, world, name):
        super().__init__(world, name)

        self.entity_builder = EntityBuilder(self.bge_scene)
        self.entity_classes = {}

        if world.netmode == Netmodes.server:
            self.controller_manager = ControllerManager(self)
        else:
            self.controller_manager = None

        self._load_configuration_files()
        self._convert_scene_message_logic()

        self.get_pending_connection_info = None

    def cull_invalid_objects(self):
        to_remove = []
        for entity in self.entity_builder.entity_to_game_obj.keys():
            if not entity.is_alive:
                to_remove.append(entity)

        for entity in to_remove:
            self.remove_replicable(entity)

    def _convert_scene_message_logic(self):
        objects = list(self.bge_scene.objects)
        objects.extend(self.bge_scene.objectsInactive)

        for obj in objects:
            self._convert_object_message_logic(obj)

    def _convert_object_message_logic(self, obj):
        """Convert logic bricks which use SCENE message API"""
        # Convert sensors
        def get_subject(identifier, request):
            # Subscribe to messages
            if identifier == 'SCENE_MESSAGE':
                send_to_bge = partial(self.receive_identified_message, identifier, request)
                self.messenger.add_subscriber(request, send_to_bge)

            return encode_scene_info(request, self)

        convert_object_message_logic(get_sensors(obj), message_prefixes_scene, get_subject)

        # Convert actuators
        get_subject = lambda identifier, request: encode_object(encode_scene_info(request, self), obj)
        convert_object_message_logic(get_actuators(obj), message_prefixes_scene, get_subject)

    def receive_identified_message(self, identifier, subject):
        """Send message to a specific instance that won't be picked up as a broadcast

        :param prefix: prefix of subject
        :param subject: subject of message
        """
        encoded_scene_info = encode_scene_info(subject, self)
        encoded_subject = encode_subject(identifier, encoded_scene_info)
        logic.sendMessage(encoded_subject)

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

        self._listeners = {}
        self._listeners['SET_NETMODE'] = self._on_set_netmode

        self._messages = []
        self._converted_scenes = set()

        self._pending_replication_managers = deque()

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

        if netmode == Netmodes.server:
            port = world_settings['port']
            self.world.rules = Rules()

        else:
            port = 0

        self.network_manager = NetworkManager(self.world, "", port)

        # Time since last sent
        self.time_since_sent = 0.0

        # Set network as active update function
        self.on_step = self.step_network
        self.cleanup = lambda: self.network_manager.stop()

        self._listeners['METHOD_INVOKE'] = self._on_invoke_method
        self._listeners['RPC_INVOKE'] = self._on_invoke_rpc
        self._listeners['PAWN_REASSOCIATE'] = self._on_controller_reassign
        self._listeners['SELF_MESSAGE'] = self._on_self_message

        self._listeners['SCENE_MESSAGE'] = self._on_scene_message
        self._listeners['PAWN_ASSOCIATE'] = self._on_controller_assign

        self._listeners['CONNECT_TO'] = self._on_connect_to

        # Set network state
        self._update_network_state()

        logic.sendMessage(encode_subject("NETWORK_INIT"))

        print("Network started")

    def add_listener(self, name, func):
        self._listeners[name].append(func)

    def push_network_message(self, message):
        self._messages.append(message)
        print("push", message)

    def send_global_message(self, identifier, subject=""):
        encoded_subject = encode_subject(identifier, subject)
        logic.sendMessage(encoded_subject)

    def create_new_player(self, replication_manager):
        self._pending_replication_managers.append(replication_manager)
        self.send_global_message("REQUEST_PAWN")

    def _process_messages(self):
        # TODO pre-extract prefixes in SCENE/replicable setup
        messages = self._messages[:]
        self._messages.clear()

        listeners = self._listeners
        world = self.world

        # Lower priority
        non_global_messages = []

        for encoded_subject in messages:
            try:
                identifier, subject = decode_subject(encoded_subject)

            except ValueError:
                continue

            listener = listeners[identifier]

            if identifier in message_prefixes_global:
                listener(subject)

            elif identifier in message_prefixes_scene:
                encoded_scene_info, obj = decode_object(subject)
                request, scene = decode_scene_info(world, encoded_scene_info)
                non_global_messages.append(partial(listener, scene, obj, request))

            # Replicable message
            else:
                try:
                    request, replicable = decode_replicable_info(world, subject)
                except ValueError:
                    continue

                non_global_messages.append(partial(listener, replicable, request))

        for listener in non_global_messages:
            listener()

    def _convert_game_global_message_logic(self):
        """Convert all global messages in scene"""
        for scene in logic.getSceneList():
            if not id(scene) in self._converted_scenes:
                self._convert_scene_global_message_logic(scene)
                self._converted_scenes.add(id(scene))

    def _convert_scene_global_message_logic(self, scene):
        """Convert logic bricks which use GLOBAL message API"""
        objects = list(scene.objects)
        objects.extend(scene.objectsInactive)

        for obj in objects:
            # Convert sensors
            convert_object_message_logic(get_sensors(obj), message_prefixes_global)

            # Convert actuators
            convert_object_message_logic(get_actuators(obj), message_prefixes_global)

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

    def _get_pending_connection_info(self):
        return self._pending_replication_managers.popleft()

    def _update_network_state(self):
        # Initialise network objects if they're added
        for bge_scene in logic.getSceneList():
            scene_name = bge_scene.name

            # Initialise scene if it doesn't exist
            try:
                scene = self.world.scenes[scene_name]

            except KeyError:
                scene = self.world.add_scene(scene_name)
                scene.get_pending_connection_info = self._get_pending_connection_info

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

    @property
    def time_step(self):
        return 1 / logic.getLogicTicRate()

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
        self._convert_game_global_message_logic()

        logic.NextFrame()

        # Process received messages from logic.NextFrame()
        self._process_messages()

        # Check if exit is required
        self.check_exit()

    def step_network(self, delta_time):
        self.time_since_sent += delta_time

        self.network_manager.receive()

        self._convert_game_global_message_logic()

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


# Helper functions
def get_sensors(obj):
    return [s for s in obj.sensors if isinstance(s, types.KX_NetworkMessageSensor)]


def get_actuators(obj):
    return [a for a in obj.actuators if isinstance(a, types.KX_NetworkMessageActuator)]


def main():
    game_loop = GameLoop()
    logic.game = game_loop
    game_loop.run()


# Instant-message API
def activate_actuator(cont, actuator):
    if not isinstance(actuator, types.KX_NetworkMessageActuator):
        cont.activate(actuator)
        return

    # TODO what about safe messages??
    logic.game.push_network_message(actuator.subject)


def deactivate_actuator(cont, actuator):
    if not isinstance(actuator, types.KX_NetworkMessageActuator):
        cont.deactivate(actuator)
        return


def _logical_controller(condition, cont):
    if condition(cont.sensors):
        for actuator in cont.actuators:
            activate_actuator(cont, actuator)
    else:
        for actuator in cont.actuators:
            deactivate_actuator(cont, actuator)


def _AND(sensors):
    for sens in sensors:
        if not sens.positive:
            return False

    return True


def _NAND(sensors):
    return not _AND(sensors)


def _OR(sensors):
    for sens in sensors:
        if sens.positive:
            return True

    return False


def _NOR(sensors):
    return not _OR(sensors)


def _XOR(sensors):
    number_positive = 0
    for sens in sensors:
        if sens.positive:
            number_positive += 1

    return number_positive == 1


def _XNOR(sensors):
    number_false = 0
    for sens in sensors:
        if not sens.positive:
            number_false += 1

    return number_false == 1


def AND(cont):
    _logical_controller(_AND, cont)


def NAND(cont):
    _logical_controller(_NAND, cont)


def OR(cont):
    _logical_controller(_OR, cont)


def NOR(cont):
    _logical_controller(_NOR, cont)


def XNOR(cont):
    _logical_controller(_XNOR, cont)


def XOR(cont):
    _logical_controller(_XOR, cont)
