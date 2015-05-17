# ##### BEGIN GPL LICENSE BLOCK #####
#
# This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

bl_info = {
    "name": "PyAuthServer BGE Addon",
    "description": "Interfaces PyAuthServer for networking.",
    "author": "Angus Hollands",
    "version": (1, 1, 4),
    "blender": (2, 74, 0),
    "location": "LOGIC_EDITOR > UI > NETWORKING",
    "warning": "",
    "wiki_url": "https://github.com/agoose77/bge_network_addon/wiki",
    "tracker_url": "https://github.com/agoose77/bge_network_addon/issues",
    "category": "Game Engine"}

import bpy

import sys
ORIGINAL_MODULES = list(sys.modules)

from json import dump
from os import path, makedirs, listdir
from shutil import rmtree
from inspect import getmembers, isclass
from logging import warning, info, exception

from game_system.configobj import ConfigObj
from network.replicable import Replicable

# Submodules
from .utilities import get_active_item, if_not_busy, copy_logic_properties_to_collection
from .version_checker import RemoteVersionChecker
from .property_groups import *
from .configuration import *
from .operators import *
from .renderers import *


active_network_scene = None
outdated_modules = []
files_last_modified = {}

version_checker = RemoteVersionChecker()
version_checker.start()


def state_changed(self, context):
    bpy.ops.network.show_states(index=context.object.states_index)


@if_not_busy("disable_scenes")
def on_scene_use_network_updated_protected(scene, context):
    global active_network_scene

    if scene == active_network_scene:
        active_network_scene = None

    if not scene.use_network:
        # Remove dispatcher object
        dispatcher = get_dispatcher(scene)
        if dispatcher is not None:
            info("Unlinking dispatcher: {}".format(dispatcher))
            scene.objects.unlink(dispatcher)

        return

    active_network_scene = scene
    for scene in bpy.data.scenes:
        if scene == scene:
            continue

        scene.use_network = False


def on_scene_use_network_updated(self, scene):
    on_scene_use_network_updated_protected(self, scene)


class SystemPanel(bpy.types.Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_label = "Networking"
    bl_context = "scene"

    COMPAT_ENGINES = {'BLENDER_GAME'}

    @classmethod
    def register(cls):
        bpy.types.Scene.port = bpy.props.IntProperty(name="Server Port", description="Port used to bind server")
        bpy.types.Scene.tick_rate = bpy.props.IntProperty(name="Tick Rate", default=30,
                                                          description="Number of network ticks per second")
        bpy.types.Scene.metric_interval = bpy.props.FloatProperty(name="Metrics Sample Interval", default=2.0,
                                                                  description="Time (in seconds) between successive "
                                                                              "network metrics updates")
        bpy.types.Scene.use_network = bpy.props.BoolProperty(name="Use Networking", default=False,
                                                             description="Set current scene as network scene",
                                                             update=on_scene_use_network_updated)

    def draw_header(self, context):
        self.layout.prop(context.scene, "use_network", text="")

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.active = scene.use_network

        layout.prop(scene, "port")

        layout.prop(scene, "tick_rate")
        layout.prop(scene, "metric_interval")

        layout.operator("network.select_all", icon='GROUP', text="Select Only Network Objects")


def obj_panel_network_poll(cls, context):
    obj = context.object
    scene = context.scene
    return obj is not None and obj.use_network and scene.use_network


class RPCPanel(bpy.types.Panel):
    bl_space_type = "LOGIC_EDITOR"
    bl_region_type = "UI"
    bl_label = "RPC Calls"

    COMPAT_ENGINES = {'BLENDER_GAME'}

    poll = classmethod(obj_panel_network_poll)

    @classmethod
    def register(cls):
        bpy.types.Object.rpc_calls_index = bpy.props.IntProperty(default=0)
        bpy.types.Object.rpc_calls = bpy.props.CollectionProperty(name="RPC Calls", type=RPCGroup)

    def draw(self, context):
        layout = self.layout

        obj = context.object

        rpc_list = layout.row()
        rpc_list.template_list('RENDER_RT_RPCList', "RPC Calls", obj, "rpc_calls", obj, "rpc_calls_index", rows=3)

        row = rpc_list.column(align=True)
        row.operator("network.add_rpc_call", icon='ZOOMIN', text="")
        row.operator("network.remove_rpc_call", icon='ZOOMOUT', text="")

        active_rpc = get_active_item(obj.rpc_calls, obj.rpc_calls_index)
        if active_rpc is None:
            return

        rpc_settings = layout.row()
        rpc_data = rpc_settings.column()
        rpc_data.label("Info", icon='INFO')
        rpc_data.prop(active_rpc, 'name')
        rpc_data.prop(active_rpc, 'target')
        rpc_data.prop(active_rpc, 'reliable', icon='LIBRARY_DATA_DIRECT' if active_rpc.reliable else
                      'LIBRARY_DATA_INDIRECT')
        rpc_data.prop(active_rpc, 'simulated', icon='SOLO_ON' if active_rpc.simulated else 'SOLO_OFF')

        rpc_args = rpc_settings.column()
        rpc_args.label("Arguments", icon='SETTINGS')
        rpc_args.template_list('RENDER_RT_RPCArgumentList', "RPCProperties", active_rpc, "arguments", active_rpc,
                               "arguments_index", rows=3)


class StatesPanel(bpy.types.Panel):
    bl_space_type = "LOGIC_EDITOR"
    bl_region_type = "UI"
    bl_label = "Network State"

    COMPAT_ENGINES = {'BLENDER_GAME'}

    poll = classmethod(obj_panel_network_poll)

    @classmethod
    def register(cls):
        bpy.types.Object.states_index = bpy.props.IntProperty(default=0, update=state_changed)
        bpy.types.Object.states = bpy.props.CollectionProperty(name="Network States", type=StateGroup)
        bpy.types.Object.simulated_states = bpy.props.BoolVectorProperty(name="Simulated States", size=30)

    def draw_states_row(self, data, name, layout, icon_func=None):
        top_i = 0
        bottom_i = 15

        if icon_func is None:
            icon_func = lambda index: 'BLANK1'

        sub_layout = layout.column_flow(columns=3)
        for col_i in range(3):
            column = sub_layout.column(align=True)
            row = column.row(align=True)
            for _ in range(5):
                icon = icon_func(top_i)
                row.prop(data, name, index=top_i, toggle=True, text="", icon=icon)
                top_i += 1

            row = column.row(align=True)
            for _ in range(5):
                icon = icon_func(bottom_i)
                row.prop(data, name, index=bottom_i, toggle=True, text="", icon=icon)
                bottom_i += 1

    def draw(self, context):
        layout = self.layout

        obj = context.object

        sub_layout = layout.split(0.3)
        sub_layout.label("Simulated States")

        box = sub_layout.box()
        self.draw_states_row(obj, 'simulated_states', box)

        column = box.column()
        set_states = column.operator("network.set_states_from_visible", icon='VISIBLE_IPO_ON', text="")
        set_states.set_simulated = True

        layout.label("Netmode States")
        sub_layout = layout.split(0.3)
        sub_layout.template_list('RENDER_RT_StateList', "States", obj, "states", obj, "states_index", rows=3)

        active_state = get_active_item(obj.states, obj.states_index)
        if active_state is None:
            return

        box = sub_layout.box()
        simulated_icon = lambda i: 'KEY_HLT' if obj.simulated_states[i] else 'BLANK1'
        self.draw_states_row(active_state, 'states', box, icon_func=simulated_icon)

        column = box.column()
        column.operator("network.set_states_from_visible", icon='VISIBLE_IPO_ON', text="")


# Add support for modifying inherited parameters?
class AttributesPanel(bpy.types.Panel):
    bl_space_type = "LOGIC_EDITOR"
    bl_region_type = "UI"
    bl_label = "Replicated Attributes"

    COMPAT_ENGINES = {'BLENDER_GAME'}

    poll = classmethod(obj_panel_network_poll)

    @classmethod
    def register(cls):
        bpy.types.Object.attribute_index = bpy.props.IntProperty(default=0)
        bpy.types.Object.attributes = bpy.props.CollectionProperty(name="Network Attributes", type=AttributeGroup)

    def draw(self, context):
        layout = self.layout

        obj = context.object
        scene = context.scene

        layout.template_list('RENDER_RT_AttributeList', "Properties", obj, "attributes", obj, "attribute_index", rows=3)


class TemplatesPanel(bpy.types.Panel):
    bl_space_type = "LOGIC_EDITOR"
    bl_region_type = "UI"
    bl_label = "Templates"

    COMPAT_ENGINES = {'BLENDER_GAME'}

    poll = classmethod(obj_panel_network_poll)

    @classmethod
    def register(cls):
        bpy.types.Object.templates_index = bpy.props.IntProperty(default=0)
        bpy.types.Object.templates = bpy.props.CollectionProperty(name="Templates", type=TemplateModule)
        bpy.types.Object.template_defaults = bpy.props.CollectionProperty(name="TemplateDefaults",
                                                                          type=ResolvedTemplateAttributeDefault)
        bpy.types.Object.templates_defaults_index = bpy.props.IntProperty(default=0)

    def draw(self, context):
        layout = self.layout

        obj = context.object

        rpc_list = layout.row()
        rpc_list.template_list('RENDER_RT_TemplateGroupList', "Templates", obj, "templates", obj, "templates_index",
                               rows=3)

        row = rpc_list.column(align=True)
        row.operator("network.add_template", icon='ZOOMIN', text="")
        row.operator("network.remove_template", icon='ZOOMOUT', text="")

        active_template = get_active_item(obj.templates, obj.templates_index)
        if active_template is None:
            return

        column = layout.column()
        column.label("Template Classes")
        column.template_list('RENDER_RT_TemplateList', "TemplateItems", active_template, "templates", active_template,
                             "templates_active", rows=3)

        if active_template is None:
            return

        row = layout.row()
        row.label("Template Attributes")

        layout.template_list('RENDER_RT_TemplateDefaultList', "TemplateItemDefaults", obj, "template_defaults",
                             obj, "templates_defaults_index", rows=3)

        if not obj.template_defaults:
            layout.label("Final class could not be built from selected template classes", icon='ERROR')


class NetworkPanel(bpy.types.Panel):
    bl_space_type = "LOGIC_EDITOR"
    bl_region_type = "UI"
    bl_label = "Network"

    COMPAT_ENGINES = {'BLENDER_GAME'}

    @classmethod
    def poll(cls, context):
        return context.object is not None

    @classmethod
    def register(cls):
        bpy.types.Object.use_network = bpy.props.BoolProperty(default=False, name="Use Networking",
                                                              description="Enable replication for this object")
        bpy.types.Object.remote_role = bpy.props.EnumProperty(name="Remote Role",
                                                              description="Establish a network role for this object",
                                                              items=ROLES_ENUMS, default="SIMULATED_PROXY")

    def draw_header(self, context):
        obj = context.object

        if context.scene.use_network:
            self.layout.prop(obj, "use_network", text="")

    def draw(self, context):
        obj = context.object
        layout = self.layout
        layout.active = obj.use_network

        if context.scene.use_network:
            layout.prop(obj, "remote_role")

        else:
            self.layout.label("Networking Must Be Enabled For This Scene", icon='ERROR')


def save_state(context):
    network_scene = active_network_scene
    if network_scene is None:
        print("No network scene exists, nothing to save...")
        return

    data_path = bpy.path.abspath("//{}".format(DATA_PATH))

    try:
        file_names = listdir(data_path)

    except FileNotFoundError:
        makedirs(data_path, exist_ok=True)
        file_names = listdir(data_path)

    config = {}

    for obj in network_scene.objects:
        obj_name = obj.name
        obj_path = path.join(data_path, obj_name)

        # Remove any previous network objects
        if not obj.use_network:
            if obj_name in file_names:
                rmtree(obj_path)

            continue

        definition_filepath = path.join(obj_path, "actor.definition")

        data = dict()

        get_property_value = lambda n: obj.game.properties[n].value
        data['attributes'] = {a.name: {'default': get_property_value(a.name),
                                       'initial_only': not a.replicate_after_initial,
                                       'ignore_owner': not a.replicate_for_owner}
                              for a in obj.attributes if a.replicate}

        data['rpc_calls'] = {r.name: {'arguments': {a.name: a.type for a in r.arguments if a.replicate},
                                      'target': r.target, 'reliable': r.reliable,
                                      'simulated': r.simulated} for r in obj.rpc_calls}

        data['templates'] = ["{}.{}".format(m.name, c.name) for m in obj.templates for c in m.templates if c.active]
        data['defaults'] = {d.name: getattr(d, d.value_name) for d in obj.template_defaults if d.modified}
        data['states'] = {c.name: list(c.states) for c in obj.states}
        data['simulated_states'] = list(obj.simulated_states)
        data['remote_role'] = obj.remote_role

        # Make sure we have directory for actor definition
        definition_directory = path.dirname(definition_filepath)
        makedirs(definition_directory, exist_ok=True)

        with open(definition_filepath, "w") as file:
            dump(data, file)

        configuration = ConfigObj()
        configuration['BGE'] = {'object_name': obj.name}

        configuration_filepath = path.join(data_path, "{}/definition.cfg".format(obj.name))
        with open(configuration_filepath, "wb") as file:
            configuration.write(file)

    config['port'] = network_scene.port
    config['tick_rate'] = network_scene.tick_rate
    config['metric_interval'] = network_scene.metric_interval
    config['scene'] = network_scene.name

    with open(path.join(data_path, "main.definition"), "w") as file:
        dump(config, file)


def get_addon_folder():
    """Return the folder of the network addon"""
    return path.dirname(__file__)


def is_valid_variable_name(name):
    stripped_underscore = name.replace('_', '')
    return stripped_underscore.isalnum() and not stripped_underscore[0].isnumeric()


def attribute_allowed_as_argument(rpc_call, attr):
    if attr.replicate:
        return rpc_call.target == "SERVER" and not attr.replicate_for_owner

    return True


def update_attributes(context):
    if not hasattr(context, "object"):
        return

    if not context.object:
        return

    obj = context.object
    attributes = obj.attributes

    copy_logic_properties_to_collection(obj.game.properties, attributes, lambda p: is_valid_variable_name(p.name))

    for rpc_call in obj.rpc_calls:
        copy_logic_properties_to_collection(attributes, rpc_call.arguments,
                                   lambda prop: attribute_allowed_as_argument(rpc_call, prop))

    if not obj.states:
        server = obj.states.add()

        server.name = "Server"
        server.states[1] = True

        client = obj.states.add()
        client.name = "Client"
        client.states[0] = True


def verify_text_files(check_modified=False):
    """Verify that all required text files are included in Blend

    :param check_modified: optionally check text files are up to date
    """
    for filename in REQUIRED_FILES:
        source_dir = get_addon_folder()
        source_path = path.join(source_dir, filename)

        try:
            text_block = bpy.data.texts[filename]

        except KeyError:
            text_block = bpy.data.texts.new(filename)

            with open(source_path, "r") as file:
                text_block.from_string(file.read())

            info("Created text block for {} from disk".format(filename))

        if check_modified:
            os_last_modified = path.getmtime(source_path)
            if files_last_modified.get(filename) == os_last_modified:
                continue

            with open(source_path, "r") as file:
                text_block.from_string(file.read())

            info("Updated {} with latest version from disk".format(filename))

            files_last_modified[filename] = os_last_modified


def update_text_files(context):
    verify_text_files()


def reload_text_files(context):
    verify_text_files(check_modified=True)


def update_network_logic(context):
    network_scene = active_network_scene

    if network_scene is None:
        for scene in bpy.data.scenes:
            if '__main__' in scene:
                del scene['__main__']

    else:
        for scene in bpy.data.scenes:
            if not scene.get("__main__") == INTERFACE_FILENAME:
                scene['__main__'] = INTERFACE_FILENAME


def clean_modules(context):
    """Free any imported modules I.E Network to prevent state error"""
    unwanted_modules = set(sys.modules).difference(ORIGINAL_MODULES)
    for mod_name in unwanted_modules:
        sys.modules.pop(mod_name)

    return unwanted_modules


def is_replicable(obj):
    if not isclass(obj):
        return False

    if not issubclass(obj, Replicable) or obj is Replicable:
        return False

    return True


def update_templates(context):
    try:
        obj = context.object
        assert obj

    except (AttributeError, AssertionError):
        return

    for module_path in DEFAULT_TEMPLATE_MODULES:
        if module_path in obj.templates:
            continue

        template = obj.templates.add()
        template.name = module_path

    template_module = get_active_item(obj.templates, obj.templates_index)
    if template_module is None:
        return

    template_path = template_module.name

    if not template_path:
        return

    if template_module.loaded:
        return

    try:
        module = __import__(template_path, fromlist=[''])

    except ImportError as err:
        exception("Failed to load {}: {}".format(template_path, err))
        return

    else:
        info("Loaded {}".format(template_path))

    templates = template_module.templates
    templates.clear()

    required_templates = []
    for name, value in getmembers(module, is_replicable):
        if name.startswith("_"):
            continue

        if name in HIDDEN_BASES:
            continue

        info("Found class {}".format(name))

        template = templates.add()
        template.name = name

        if name in DEFAULT_TEMPLATE_MODULES.get(template_path, []):
            required_templates.append(template)

        # Store the default attribute values
        defaults = template.defaults
        ui_types = int, bool, str, float

        for attribute_name, attribute_value in getmembers(value):
            if attribute_name.startswith("_"):
                continue

            value_type = type(attribute_value)
            if value_type not in ui_types:
                continue

            default = defaults.add()
            default.name = attribute_name
            default.type = type_to_enum_type(value_type)

            value_name = default.value_name
            setattr(default, value_name, attribute_value)

    template_module.loaded = True

    for template in required_templates:
        template.required = template.active = True


def update_use_network(context):
    global active_network_scene

    for scene in bpy.data.scenes:
        if scene.use_network:
            if active_network_scene is None:
                active_network_scene = scene

            elif scene != active_network_scene:
                scene.use_network = False


def get_dispatcher(scene):
    """Check if dispatcher exists in scene"""
    try:
        return scene.objects[DISPATCHER_NAME]

    except KeyError:
        # It might have been renamed
        for obj in scene.objects:
            if DISPATCHER_MARKER in obj:
                return obj

    return None


def load_dispatcher(scene):
    """Load dispatcher object from assets blend"""
    addon_folder = get_addon_folder()
    data_path = path.join(addon_folder, ASSETS_FILENAME)

    # Load dispatcher
    with bpy.data.libraries.load(data_path) as (data_from, data_to):
        data_to.objects.append(DISPATCHER_NAME)

    dispatcher = data_to.objects[0]
    dispatcher[DISPATCHER_MARKER] = True

    scene.objects.link(dispatcher)


def check_dispatcher_exists(context):
    network_scene = active_network_scene
    if network_scene is None:
        return

    if get_dispatcher(network_scene) is not None:
        return

    info("Reloaded dispatcher from assets.blend")
    load_dispatcher(network_scene)


def set_network_global_var(context):
    """Set global active_network_scene variable in registered"""
    global active_network_scene
    for scene in bpy.data.scenes:
        if scene.use_network:
            active_network_scene = scene
            return


def poll_version_checker(context):
    """Check for any update results"""
    for name, is_up_to_date in version_checker.results:
        if not is_up_to_date:
            bpy.ops.wm.display_info('INVOKE_DEFAULT', message="{} is out of date!".format(name))


def send_version_check_requests():
    """Send version comparison request to worker thread"""
    remote_path = "https://raw.githubusercontent.com/agoose77/PyAuthServer/master/network/"
    local_path = __import__("network").__path__[0]
    version_checker.check_version("Network", remote_path, local_path, "version.txt")

    remote_path = "https://raw.githubusercontent.com/agoose77/bge_network_addon/master/"
    local_path = get_addon_folder()
    version_checker.check_version("BGE Network Addon", remote_path, local_path, "version.txt")


def pre_game_save(context):
    if not bpy.data.is_saved:
        warning("This file has not been saved, network data will not be created")
        return

    save_state(context)


def run_callbacks(handlers):
    context = bpy.context
    for callback in handlers:
        callback(context)


on_update_if_active_handlers = []
on_update_global_handlers = []

on_save_if_active_handlers = []
on_load_global_handlers = []
pre_game_if_active_handlers = []


@if_not_busy("update")
@bpy.app.handlers.persistent
def on_update(scene):
    run_callbacks(on_update_global_handlers)

    if active_network_scene:
        run_callbacks(on_update_if_active_handlers)


@bpy.app.handlers.persistent
def on_save(dummy):
    if active_network_scene:
        run_callbacks(on_save_if_active_handlers)


@bpy.app.handlers.persistent
def on_load(dummy):
    run_callbacks(on_load_global_handlers)


@bpy.app.handlers.persistent
def on_game_pre(scene):
    if active_network_scene:
        run_callbacks(pre_game_if_active_handlers)


# Handler dispatchers
on_update_if_active_handlers.append(update_attributes)
on_update_if_active_handlers.append(update_network_logic)
on_update_if_active_handlers.append(update_text_files)
on_update_if_active_handlers.append(update_templates)
on_update_if_active_handlers.append(check_dispatcher_exists)

on_update_global_handlers.append(update_use_network)
on_update_global_handlers.append(poll_version_checker)

pre_game_if_active_handlers.append(pre_game_save)
pre_game_if_active_handlers.append(clean_modules)
pre_game_if_active_handlers.append(reload_text_files)

on_save_if_active_handlers.append(save_state)
on_load_global_handlers.append(set_network_global_var)


registered = False


def register():
    global registered

    if registered:
        return

    # Check updates
    send_version_check_requests()

    bpy.utils.register_module(__name__)

    bpy.app.handlers.scene_update_post.append(on_update)
    bpy.app.handlers.save_post.append(on_save)
    bpy.app.handlers.game_pre.append(on_game_pre)
    bpy.app.handlers.load_post.append(on_load)

    registered = True


def unregister():
    bpy.utils.unregister_module(__name__)

    bpy.app.handlers.scene_update_post.remove(on_update)
    bpy.app.handlers.save_post.remove(on_save)
    bpy.app.handlers.load_post.remove(on_load)
    bpy.app.handlers.game_pre.remove(on_game_pre)

    unloaded = clean_modules(None)
    info("Unloaded {}".format(unloaded))

    global registered
    registered = False