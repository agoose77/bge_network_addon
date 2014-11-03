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
    "version": (3, 0, 0),
    "blender": (2, 71, 0),
    "api": 56945,
    "location": "LOGIC_EDITOR > UI > NETWORKING",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Game Engine"}

import bpy
import sys
from json import dump
from os import path, makedirs, listdir
from shutil import rmtree
from inspect import getmembers, isclass

ORIGINAL_MODULES = list(sys.modules)

from game_system.configobj import ConfigObj
from network.replicable import Replicable
from network.enums import Roles, Netmodes


def get_bpy_enum(enum):
    enum_name = enum.__name__.rstrip("s").lower()
    return [(x.upper(), x.replace('_', ' ').title(), "{} {}".format(x.capitalize(), enum_name), i)
            for i, x in enumerate(enum.values)]

NETWORK_ENUMS = get_bpy_enum(Netmodes)
ROLES_ENUMS = get_bpy_enum(Roles)

CONFIGURATION_FILE = "configuration.json"
LISTENER_PATH = "interface.listener"
DATA_PATH = "network_data"
MAINLOOP_FILENAME = "mainloop.py"
INTERFACE_FILENAME = "interface.py"
REQUIRED_FILES = MAINLOOP_FILENAME, INTERFACE_FILENAME
DISPATCHER_NAME = "DISPATCHER"
ENTITY_BASES = "game_system.entities",


class AttributeGroup(bpy.types.PropertyGroup):

    """PropertyGroup for Actor attributes"""

    name = bpy.props.StringProperty()
    type = bpy.props.StringProperty()

    notify = bpy.props.BoolProperty(default=False, description="Whether attribute should trigger notifications")
    replicate = bpy.props.BoolProperty(default=False, description="Replicate this attribute")


bpy.utils.register_class(AttributeGroup)


class RPCArgumentGroup(bpy.types.PropertyGroup):

    """PropertyGroup for RPC arguments"""

    name = bpy.props.StringProperty()
    type = bpy.props.StringProperty()

    replicate = bpy.props.BoolProperty(default=False, description="Replicate this attribute")


bpy.utils.register_class(RPCArgumentGroup)


class RPCGroup(bpy.types.PropertyGroup):

    """PropertyGroup for RPC calls"""

    name = bpy.props.StringProperty(name="Name", default="Function", description="Name of RPC call")
    reliable = bpy.props.BoolProperty(default=False, name="Reliable", description="Guarantee delivery of RPC call")
    simulated = bpy.props.BoolProperty(default=False, name="Simulated", description="Allow execution for simulated proxy")
    target = bpy.props.EnumProperty(items=NETWORK_ENUMS, name='Target', description="Netmode of RPC target")

    arguments = bpy.props.CollectionProperty(type=RPCArgumentGroup)
    arguments_index = bpy.props.IntProperty()


bpy.utils.register_class(RPCGroup)


class StateGroup(bpy.types.PropertyGroup):

    """PropertyGroup for RPC calls"""

    name = bpy.props.StringProperty(name="Name", default="", description="Netmode of state group")
    states = bpy.props.BoolVectorProperty(name="States", size=30)


bpy.utils.register_class(StateGroup)


class TemplateClass(bpy.types.PropertyGroup):

    """PropertyGroup for Template items"""

    name = bpy.props.StringProperty(name="Name", default="", description="Name of template")
    active = bpy.props.BoolProperty(name="Active", default=False, description="Use this template")


bpy.utils.register_class(TemplateClass)


class TemplateModule(bpy.types.PropertyGroup):

    """PropertyGroup for Template collections"""

    name = bpy.props.StringProperty(name="Template Path", default="", description="Full path of template")
    loaded = bpy.props.BoolProperty(name="Loaded", default=False, description="Flag to prevent reloading")
    templates = bpy.props.CollectionProperty(name="Templates", type=TemplateClass)
    templates_active = bpy.props.IntProperty()


bpy.utils.register_class(TemplateModule)


class SystemPanel(bpy.types.Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_label = "Networking"
    bl_context = "world"

    COMPAT_ENGINES = {'BLENDER_GAME'}

    @classmethod
    def register(cls):
        bpy.types.Scene.network_mode = bpy.props.EnumProperty(name="Mode", items=NETWORK_ENUMS)
        bpy.types.Scene.host = bpy.props.StringProperty(name="Socket Host", default="")
        bpy.types.Scene.port = bpy.props.IntProperty(name="Socket Port")
        bpy.types.Scene.tick_rate = bpy.props.IntProperty(name="Tick Rate", default=30)
        bpy.types.Scene.metric_interval = bpy.props.FloatProperty(name="Metrics Sample Interval", default=2.0)
        bpy.types.Scene.use_network = bpy.props.BoolProperty(name="Use Networking", default=False,
                                                             description="Enable networking for the game")

    def draw_header(self, context):
        self.layout.prop(context.scene, "use_network", text="")

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.active = scene.use_network

        layout.prop(scene, "network_mode", icon='CONSOLE')

        if scene.network_mode == "SERVER":
            layout.prop(scene, "port")

        layout.prop(scene, "tick_rate")
        layout.prop(scene, "metric_interval")


class RPCPanel(bpy.types.Panel):
    bl_space_type = "LOGIC_EDITOR"
    bl_region_type = "UI"
    bl_label = "RPC Calls"

    COMPAT_ENGINES = {'BLENDER_GAME'}

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.use_network

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

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.use_network

    @classmethod
    def register(cls):
        bpy.types.Object.states_index = bpy.props.IntProperty(default=0)
        bpy.types.Object.states = bpy.props.CollectionProperty(name="Network States", type=StateGroup)

    def draw_states_row(self, active_state, sub_layout):
        top_i = 0
        bottom_i = 15

        for col_i in range(3):
            column = sub_layout.column(align=True)
            row = column.row(align=True)
            for _ in range(5):
                row.prop(active_state, "states", index=top_i, toggle=True, text="")
                top_i += 1

            row = column.row(align=True)
            for _ in range(5):
                row.prop(active_state, "states", index=bottom_i, toggle=True, text="")
                bottom_i += 1

    def draw(self, context):
        layout = self.layout

        obj = context.object

        layout.template_list('RENDER_RT_StateList', "States", obj, "states", obj, "states_index", rows=3)

        active_state = get_active_item(obj.states, obj.states_index)
        if active_state is None:
            return

        sub_layout = layout.split(0.3)
        sub_layout.label("States")

        box = sub_layout.box()
        sub_layout = box.column_flow(columns=3)
        self.draw_states_row(active_state, sub_layout)

        column = box.column()
        column.operator("network.save_states", icon='FILE_REFRESH', text="")


# Add support for modifying inherited parameters?
class AttributesPanel(bpy.types.Panel):
    bl_space_type = "LOGIC_EDITOR"
    bl_region_type = "UI"
    bl_label = "Replicated Attributes"

    COMPAT_ENGINES = {'BLENDER_GAME'}

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.use_network

    @classmethod
    def register(cls):
        bpy.types.Object.attribute_index = bpy.props.IntProperty(default=0)
        bpy.types.Object.attributes = bpy.props.CollectionProperty(name="Network Attributes", type=AttributeGroup)

    def draw(self, context):
        layout = self.layout

        obj = context.object
        scene = context.scene

        layout.template_list('RENDER_RT_AttributeList', "Properties", obj, "attributes", obj, "attribute_index", rows=3)

        layout.active = scene.network_mode == 'SERVER'


class TemplatesPanel(bpy.types.Panel):
    bl_space_type = "LOGIC_EDITOR"
    bl_region_type = "UI"
    bl_label = "Templates"

    COMPAT_ENGINES = {'BLENDER_GAME'}

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.use_network

    @classmethod
    def register(cls):
        bpy.types.Object.templates_index = bpy.props.IntProperty(default=0)
        bpy.types.Object.templates = bpy.props.CollectionProperty(name="Templates", type=TemplateModule)

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
        column.template_list('RENDER_RT_TemplateList', "TemplateItem", active_template, "templates", active_template,
                             "templates_active", rows=3)

        row = layout.row()
        row.label("Template Attributes")

        box = layout.box()
        box.prop(obj, "network_role")
        box.active = obj.use_network



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
        bpy.types.Object.network_role = bpy.props.EnumProperty(name="Network Role",
                                                               description="Establish a network role for this object",
                                                               items=ROLES_ENUMS)

    def draw(self, context):
        layout = self.layout
        obj = context.object

        layout.prop(obj, "use_network", icon='AUTOMERGE_ON' if obj.use_network else 'AUTOMERGE_OFF')


class RENDER_RT_StateList(bpy.types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        sub_layout = layout.split(0.8)
        sub_layout.label(item.name, icon="NONE")

        view = sub_layout.operator("network.set_states_visible", icon='RESTRICT_VIEW_OFF', text="Go To State")
        view.index = index


class RENDER_RT_RPCArgumentList(bpy.types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        sub_layout = layout.split(0.8, True)
        sub_layout.label(item.name, icon="NONE")

        item_active = item.replicate

        row = layout.row()
        attr_icon = 'CHECKBOX_HLT' if item_active else 'CHECKBOX_DEHLT'
        row.prop(item, "replicate", text="", icon=attr_icon, emboss=False)


class RENDER_RT_AttributeList(bpy.types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(item.name, icon="NONE")
        row = layout.row()

        item_active = item.replicate

        row.prop(item, "notify", text="", icon='INFO')
        row.active = item_active

        row = layout.row()
        attr_icon = 'MUTE_IPO_OFF' if item_active else 'MUTE_IPO_ON'
        row.prop(item, "replicate", text="", icon=attr_icon, emboss=False)


class RENDER_RT_RPCList(bpy.types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        network_mode = context.scene.network_mode

        direction_icon = 'TRIA_UP' if network_mode == item.target else 'TRIA_DOWN'
        layout.prop(item, "name", icon=direction_icon, text="", emboss=False)

        reliable_icon = 'LIBRARY_DATA_DIRECT' if item.reliable else 'LIBRARY_DATA_INDIRECT'
        layout.prop(item, "reliable", text="", icon=reliable_icon, emboss=False)

        simulated_icon = 'SOLO_ON' if item.simulated else 'SOLO_OFF'
        layout.prop(item, "simulated", text="", icon=simulated_icon, emboss=False)


class RENDER_RT_TemplateGroupList(bpy.types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(icon='FILE_SCRIPT', text=item.name)


class RENDER_RT_TemplateList(bpy.types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(icon='SCRIPTPLUGINS', text=item.name)

        layout.prop(item, "active", text="")


class LOGIC_OT_add_rpc(bpy.types.Operator):
    """Tooltip"""
    bl_idname = "network.add_rpc_call"
    bl_label = "Add RPC call"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        obj.rpc_calls.add()

        return {'FINISHED'}


class LOGIC_OT_remove_rpc(bpy.types.Operator):
    """Tooltip"""
    bl_idname = "network.remove_rpc_call"
    bl_label = "Remove RPC call"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        obj.rpc_calls.remove(obj.rpc_calls_index)

        return {'FINISHED'}


class LOGIC_OT_add_template(bpy.types.Operator):
    """Tooltip"""
    bl_idname = "network.add_template"
    bl_label = "Add template"

    path = bpy.props.StringProperty(name="Path", description="Path to templates")

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        obj = context.active_object
        name = self.path

        try:
            __import__(name, fromlist=[''])

        except (ValueError, ImportError):
            return {'CANCELLED'}

        template = obj.templates.add()
        template.name = name

        return {'FINISHED'}


class LOGIC_OT_remove_template(bpy.types.Operator):
    """Tooltip"""
    bl_idname = "network.remove_template"
    bl_label = "Remove template"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        active_template = get_active_item(obj.templates, obj.templates_index)
        if not active_template.name in ENTITY_BASES:
            obj.templates.remove(obj.templates_index)

        return {'FINISHED'}


class LOGIC_OT_save_states(bpy.types.Operator):
    """Tooltip"""
    bl_idname = "network.save_states"
    bl_label = "Save logic states for this netmode"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        obj.states[obj.states_index].states = obj.game.states_visible

        return {'FINISHED'}


class LOGIC_OT_set_states_visible(bpy.types.Operator):
    """Tooltip"""
    bl_idname = "network.set_states_visible"
    bl_label = "Set the states for this netmode visible"

    index = bpy.props.IntProperty()

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object

        active_state = obj.states[self.index]
        obj.game.states_visible = active_state.states

        for area in bpy.context.screen.areas:
            if area.type != 'LOGIC_EDITOR':
                continue

            area.tag_redraw()

        return {'FINISHED'}


def get_active_item(collection, index):
    if index >= len(collection):
        return None

    return collection[index]


def update_collection(source, destination):
    original = {}

    for prop in destination:
        original[prop.name] = prop.items()

    destination.clear()

    for prop in source:
        attr = destination.add()

        try:
            item_dict = dict(prop.items())

        except TypeError:
            invalid_members = list(dir(bpy.types.Struct)) + ['rna_type']
            item_dict = {k: getattr(prop, k) for k in dir(prop) if not k in invalid_members}

        try:
            original_items = original[prop.name]

        except KeyError:
            pass

        else:
            item_dict.update(original_items)

        for key, value in item_dict.items():
            attr[key] = value


update_handlers = []

busy = False
@bpy.app.handlers.persistent
def on_update(scene):
    context = bpy.context

    global busy
    if busy:
        return

    busy = True

    for func in update_handlers:
        func(context)

    busy = False


@bpy.app.handlers.persistent
def on_save(dummy):
    data_path = bpy.path.abspath("//{}".format(DATA_PATH))

    scene = bpy.context.scene

    if scene.network_mode == "CLIENT":
        scene.port = 0

    host = scene.host
    port = scene.port

    config = {}

    files = listdir(data_path)

    for scene_ in bpy.data.scenes:

        for obj in scene_.objects:
            obj_name = obj.name

            obj_path = path.join(data_path, obj_name)

            if not obj.use_network:
                if obj_name in files:
                    rmtree(obj_path)

                continue

            filepath = path.join(obj_path, "actor.definition")

            data = dict()

            get_value = lambda n: obj.game.properties[n].value
            data['attributes'] = {a.name: {'default': get_value(a.name), 'notify': a.notify}
                                  for a in obj.attributes if a.replicate}
            data['rpc_calls'] = {r.name: {'arguments': {a.name: a.type for a in r.arguments if a.replicate},
                                          'target': r.target, 'reliable': r.reliable,
                                          'simulated': r.simulated} for r in obj.rpc_calls}

            data['templates'] = ["{}.{}".format(g.name, t.name) for g in obj.templates for t in g.templates
                                 if t.active]
            data['states'] = {c.name: c.state_mask for c in obj.states}

            makedirs(path.dirname(filepath), exist_ok=True)
            with open(filepath, "w") as file:
                dump(data, file)

            configuration = ConfigObj()
            configuration['BGE'] = {'object_name': obj.name}

            configpath = path.join(data_path, "{}/definition.cfg".format(obj.name))
            with open(configpath, "wb") as file:
                configuration.write(file)

    config['host'] = host
    config['port'] = port
    config['tick_rate'] = scene.tick_rate
    config['metric_interval'] = scene.metric_interval
    config['netmode'] = scene.network_mode

    with open(path.join(data_path, "main.definition"), "w") as file:
        dump(config, file)


def prop_is_replicated(prop, attributes):
    prop_name = prop.name

    if not prop_name in attributes:
        return False

    return attributes[prop_name].replicate


def update_attributes(context):
    if not hasattr(context, "object"):
        return

    if not context.object:
        return

    obj = context.object
    attributes = obj.attributes

    update_collection(obj.game.properties, attributes)

    for rpc_call in obj.rpc_calls:
        valid_props = [p for p in obj.game.properties if not prop_is_replicated(p, attributes)]
        update_collection(valid_props, rpc_call.arguments)

    if not obj.states:
        server = obj.states.add()
        server.name = "Server"
        server.state_mask = 2

        client = obj.states.add()
        client.name = "Client"
        client.state_mask = 1


def update_message_listener(context):
    if DISPATCHER_NAME in context.scene.objects:
        return

    bpy.ops.object.empty_add()
    empty = context.object

    empty.location = (0.0, 0.0, 0.0)

    bpy.ops.logic.sensor_add(type='MESSAGE')
    bpy.ops.logic.controller_add(type='PYTHON')

    empty.game.sensors[0].link(empty.game.controllers[0])
    empty.game.controllers[0].mode = 'MODULE'
    empty.game.controllers[0].module = LISTENER_PATH
    empty.game.controllers[0].states = 30

    empty.name = DISPATCHER_NAME


def update_network_logic(context):
    scene = context.scene

    if scene.use_network:
        if not scene.get("__main__") == INTERFACE_FILENAME:
            scene['__main__'] = INTERFACE_FILENAME

    elif '__main__' in scene:
        del scene['__main__']

    for filename in REQUIRED_FILES:
        source_dir = path.dirname(__file__)
        source_path = path.join(source_dir, filename)

        if not filename in bpy.data.texts:
            text = bpy.data.texts.new(filename)
            with open(source_path, "r") as file:
                text.from_string(file.read())


@bpy.app.handlers.persistent
def clean_modules(dummy):
    """Free any imported modules I.E Network to prevent state error"""
    for mod_name in set(sys.modules).difference(ORIGINAL_MODULES):
        sys.modules.pop(mod_name)


def update_templates(context):
    obj = context.object
    if not obj:
        return

    for module_path in ENTITY_BASES:
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

    except ImportError:
        return

    templates = template_module.templates
    templates.clear()

    for name, value in getmembers(module):
        if name.startswith("_"):
            continue

        if not isclass(value):
            continue

        if not issubclass(value, Replicable) or value is Replicable:
            continue

        template = templates.add()
        template.name = name

    template_module.loaded = True


update_handlers.append(update_attributes)
update_handlers.append(update_network_logic)
update_handlers.append(update_message_listener)
update_handlers.append(update_templates)


def register():
    bpy.utils.register_module(__name__)
    bpy.app.handlers.scene_update_post.append(on_update)
    bpy.app.handlers.save_post.append(on_save)
    bpy.app.handlers.game_pre.append(on_save)
    bpy.app.handlers.game_pre.append(clean_modules)


def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.app.handlers.scene_update_post.remove(on_update)
    bpy.app.handlers.save_post.remove(on_save)
    bpy.app.handlers.game_pre.remove(on_save)
    bpy.app.handlers.game_pre.remove(clean_modules)