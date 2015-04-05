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
    "blender": (2, 74, 0),
    "location": "LOGIC_EDITOR > UI > NETWORKING",
    "warning": "",
    "wiki_url": "https://github.com/agoose77/bge_network_addon/wiki",
    "tracker_url": "https://github.com/agoose77/bge_network_addon/issues",
    "category": "Game Engine"}

import bpy
import sys

from contextlib import contextmanager
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


def type_to_enum_type(type_):
    types = {int: "INT", float: "FLOAT", str: "STRING", bool: "BOOL"}
    return types[type_]


TYPE_ENUMS = [(c, c, c) for i, c in enumerate(map(type_to_enum_type, (bool, int, float, str)))]
NETWORK_ENUMS = get_bpy_enum(Netmodes)
ROLES_ENUMS = get_bpy_enum(Roles)

CONFIGURATION_FILE = "configuration.json"

LISTENER_PATH = "interface.listener"
DATA_PATH = "network_data"
RULES_FILENAME = "rules.py"
MAINLOOP_FILENAME = "mainloop.py"
INTERFACE_FILENAME = "interface.py"
SIGNALS_FILENAME = "signals.py"
ACTORS_FILENAME = "actors.py"
REQUIRED_FILES = MAINLOOP_FILENAME, INTERFACE_FILENAME, RULES_FILENAME, SIGNALS_FILENAME, ACTORS_FILENAME

DISPATCHER_NAME = "DISPATCHER"
DEFAULT_TEMPLATE_MODULES = {"game_system.entities": [], "actors": ("SCAActor",)}
DEFAULT_BASES = "SCAActor",
HIDDEN_BASES = "Actor",


busy_operations = set()
files_last_modified = {}
active_network_scene = None


@contextmanager
def whilst_not_busy(identifier):
    if identifier in busy_operations:
        return

    busy_operations.add(identifier)
    try:
        yield
    finally:
        busy_operations.remove(identifier)


def state_changed(self, context):
    bpy.ops.network.show_states(index=context.object.states_index)


def on_template_updated(self, context):
    obj = context.object
    if not obj:
        return

    bases = {}
    for template_module in obj.templates:
        template_path = template_module.name

        if not template_module.loaded:
            continue

        try:
            module = __import__(template_path, fromlist=[''])

        except ImportError:
            return

        templates = template_module.templates

        for template in templates:
            if template.active:
                cls = getattr(module, template.name)
                bases[cls] = template

    obj_defaults = obj.template_defaults
    obj_defaults.clear()

    try:
        mro = determine_mro(*bases.keys())

    except TypeError:
        return

    for cls in mro:
        try:
            template = bases[cls]

        except KeyError:
            continue

        for source in template.defaults:
            attribute_name = source.name

            if attribute_name in obj_defaults:
                continue

            destination = obj_defaults.add()
            update_item(source, destination)
            destination.original_hash = source.hash


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


class TemplateAttributeDefault(bpy.types.PropertyGroup):

    @property
    def hash(self):
        return str(hash(getattr(self, self.value_name)))

    @property
    def value_name(self):
        return "value_{}".format(self.type.lower())

    def get_items(self, context):
        return []

    name = bpy.props.StringProperty(name="Name")
    type = bpy.props.EnumProperty(name="Type", items=TYPE_ENUMS)

    value_int = bpy.props.IntProperty()
    value_float = bpy.props.FloatProperty()
    value_string = bpy.props.StringProperty()
    value_bool = bpy.props.BoolProperty()
    value_enum = bpy.props.EnumProperty(items=get_items)


bpy.utils.register_class(TemplateAttributeDefault)


class ResolvedTemplateAttributeDefault(bpy.types.PropertyGroup):

    @property
    def hash(self):
        return str(hash(getattr(self, self.value_name)))

    @property
    def value_name(self):
        return "value_{}".format(self.type.lower())

    @property
    def modified(self):
        return self.hash != self.original_hash

    def get_items(self, context):
        return []

    original_hash = bpy.props.StringProperty(name="Hash")
    name = bpy.props.StringProperty(name="Name")
    type = bpy.props.EnumProperty(name="Type", items=TYPE_ENUMS)

    value_int = bpy.props.IntProperty()
    value_float = bpy.props.FloatProperty()
    value_string = bpy.props.StringProperty()
    value_bool = bpy.props.BoolProperty()
    value_enum = bpy.props.EnumProperty(items=get_items)


bpy.utils.register_class(ResolvedTemplateAttributeDefault)


class TemplateClass(bpy.types.PropertyGroup):

    """PropertyGroup for Template items"""

    name = bpy.props.StringProperty(name="Name", default="", description="Name of template")
    active = bpy.props.BoolProperty(name="Active", default=False, description="Use this template",
                                    update=on_template_updated)
    required = bpy.props.BoolProperty(name="Default", default=False)

    defaults = bpy.props.CollectionProperty(name="Defaults", type=TemplateAttributeDefault)
    defaults_active = bpy.props.IntProperty()

bpy.utils.register_class(TemplateClass)


class TemplateModule(bpy.types.PropertyGroup):

    """PropertyGroup for Template collections"""

    name = bpy.props.StringProperty(name="Template Path", default="", description="Full path of template")
    loaded = bpy.props.BoolProperty(name="Loaded", default=False, description="Flag to prevent reloading")
    templates = bpy.props.CollectionProperty(name="Templates", type=TemplateClass)
    templates_active = bpy.props.IntProperty()


bpy.utils.register_class(TemplateModule)


@whilst_not_busy("disable_scenes")
def disable_other_scenes_protected(scene, context):
    global active_network_scene

    if scene == active_network_scene:
        active_network_scene = None

    if not scene.use_network:
        return

    active_network_scene = scene

    for scene in bpy.data.scenes:
        if scene == scene:
            continue

        scene.use_network = False


def disable_other_scenes(self, scene):
    disable_other_scenes_protected(self, scene)


class SystemPanel(bpy.types.Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_label = "Networking"
    bl_context = "scene"

    COMPAT_ENGINES = {'BLENDER_GAME'}

    @classmethod
    def register(cls):
        bpy.types.Scene.port = bpy.props.IntProperty(name="Server Port")
        bpy.types.Scene.tick_rate = bpy.props.IntProperty(name="Tick Rate", default=30)
        bpy.types.Scene.metric_interval = bpy.props.FloatProperty(name="Metrics Sample Interval", default=2.0)
        bpy.types.Scene.use_network = bpy.props.BoolProperty(name="Use Networking", default=False,
                                                             description="Enable networking for the game",
                                                             update=disable_other_scenes)

    def draw_header(self, context):
        self.layout.prop(context.scene, "use_network", text="")

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.active = scene.use_network

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
        self.layout.prop(obj, "use_network", text="")

    def draw(self, context):
        obj = context.object
        layout = self.layout
        layout.active = obj.use_network

        layout.prop(obj, "remote_role")


class RENDER_RT_StateList(bpy.types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(item.name, icon="NONE")


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


class RENDER_RT_TemplateDefaultList(bpy.types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        item_name = item.name.replace("_", " ").title()
        layout.label(item_name, icon="NONE")
        row = layout.row(align=True)
        value_name = item.value_name
        row.prop(item, value_name, text="")


class RENDER_RT_RPCList(bpy.types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "name", text="", emboss=False)

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

        if not item.required:
            layout.prop(item, "active", text="")


class LOGIC_OT_group_network_objects(bpy.types.Operator):
    """Create group for network objects in scene"""
    bl_idname = "network.add_to_group"
    bl_label = "Add network objects to group"

    group_name = bpy.props.StringProperty(default="NetworkObjects")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        group_name = self.group_name

        try:
            group = bpy.data.groups[group_name]

        except KeyError:
            group = bpy.data.groups.new(group_name)

        for obj in context.scene.objects:
            if obj.use_network:
                try:
                    group.objects.link(obj)
                except RuntimeError:
                    continue


class LOGIC_OT_add_rpc(bpy.types.Operator):
    """Add a new RPC call"""
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
    """Delete selected RPC call"""
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
    """Load templates from a module"""
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
    """Unload templates from a module"""
    bl_idname = "network.remove_template"
    bl_label = "Remove template"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        active_template = get_active_item(obj.templates, obj.templates_index)

        if not active_template.name in DEFAULT_TEMPLATE_MODULES:
            obj.templates.remove(obj.templates_index)

        return {'FINISHED'}


class LOGIC_OT_set_states_from_visible(bpy.types.Operator):
    """Write currently visible states to mask for this netmode"""
    bl_idname = "network.set_states_from_visible"
    bl_label = "Save logic states for this netmode"

    set_simulated = bpy.props.BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        if self.set_simulated:
            states = obj.simulated_states

        else:
            states = obj.states[obj.states_index].states

        states[:] = obj.game.states_visible

        return {'FINISHED'}


class LOGIC_OT_show_states(bpy.types.Operator):
    """Read currently visible states from mask for this netmode"""
    bl_idname = "network.show_states"
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


def determine_mro(*bases):
    """Calculate the Method Resolution Order of bases using the C3 algorithm.

    Suppose you intended creating a class K with the given base classes. This
    function returns the MRO which K would have, *excluding* K itself (since
    it doesn't yet exist), as if you had actually created the class.

    Another way of looking at this, if you pass a single class K, this will
    return the linearization of K (the MRO of K, *including* itself).
    """
    seqs = [list(C.__mro__) for C in bases] + [list(bases)]
    res = []
    while True:
        non_empty = list(filter(None, seqs))
        if not non_empty:
            # Nothing left to process, we're done.
            return tuple(res)

        for seq in non_empty:  # Find merge candidates among seq heads.
            candidate = seq[0]
            not_head = [s for s in non_empty if candidate in s[1:]]
            if not_head:
                # Reject the candidate.
                candidate = None
            else:
                break

        if not candidate:
            raise TypeError("inconsistent hierarchy, no C3 MRO is possible")

        res.append(candidate)
        for seq in non_empty:
            # Remove candidate.
            if seq[0] == candidate:
                del seq[0]


def get_active_item(collection, index):
    if index >= len(collection):
        return None

    return collection[index]


def update_item(source, destination, destination_data=None):
    try:
        item_dict = dict(source.items())

    except TypeError:
        invalid_members = list(dir(bpy.types.Struct)) + ['rna_type']
        item_dict = {k: getattr(source, k) for k in dir(source) if not k in invalid_members}

    if destination_data is not None:
        item_dict.update(destination_data)
        pass

    for key, value in item_dict.items():
        destination[key] = value


def update_collection(source, destination, condition=None):
    original = {}

    for prop in destination:
        original[prop.name] = prop.items()

    destination.clear()

    for prop in source:
        if callable(condition) and not condition(prop):
            continue

        attr = destination.add()
        update_item(prop, attr, original.get(prop.name))


update_handlers = []


@whilst_not_busy("update")
@bpy.app.handlers.persistent
def on_update(scene):
    context = bpy.context

    for func in update_handlers:
        func(context)


@bpy.app.handlers.persistent
def on_save(dummy):
    data_path = bpy.path.abspath("//{}".format(DATA_PATH))

    network_scene = active_network_scene
    port = network_scene.port

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

            data['templates'] = ["{}.{}".format(g.name, t.name) for g in obj.templates for t in g.templates if t.active]
            data['defaults'] = {d.name: getattr(d, d.value_name) for d in obj.template_defaults if d.modified}
            data['states'] = {c.name: list(c.states) for c in obj.states}
            data['simulated_states'] = list(obj.simulated_states)
            data['remote_role'] = obj.remote_role

            makedirs(path.dirname(filepath), exist_ok=True)
            with open(filepath, "w") as file:
                dump(data, file)

            configuration = ConfigObj()
            configuration['BGE'] = {'object_name': obj.name}

            configpath = path.join(data_path, "{}/definition.cfg".format(obj.name))
            with open(configpath, "wb") as file:
                configuration.write(file)

    config['port'] = port
    config['tick_rate'] = network_scene.tick_rate
    config['metric_interval'] = network_scene.metric_interval
    config['scene'] = network_scene.name

    with open(path.join(data_path, "main.definition"), "w") as file:
        dump(config, file)


def prop_is_replicated(prop, attributes):
    prop_name = prop.name

    if prop_name not in attributes:
        return False

    return attributes[prop_name].replicate


def update_attributes(context):
    if not hasattr(context, "object"):
        return

    if not context.object:
        return

    obj = context.object
    attributes = obj.attributes

    update_collection(obj.game.properties, attributes, lambda p: " " not in p.name)

    for rpc_call in obj.rpc_calls:
        update_collection(attributes, rpc_call.arguments, lambda p: not p.replicate)

    if not obj.states:
        server = obj.states.add()

        server.name = "Server"
        server.states[1] = True

        client = obj.states.add()
        client.name = "Client"
        client.states[0] = True


def verify_text_files(check_modified=False):
    for filename in REQUIRED_FILES:
        source_dir = path.dirname(__file__)
        source_path = path.join(source_dir, filename)

        try:
            text_block = bpy.data.texts[filename]

        except KeyError:
            text_block = bpy.data.texts.new(filename)

            with open(source_path, "r") as file:
                text_block.from_string(file.read())

            print("Created text block for {} from disk".format(filename))

        if check_modified:
            os_last_modified = path.getmtime(source_path)
            if files_last_modified.get(filename) == os_last_modified:
                continue

            with open(source_path, "r") as file:
                text_block.from_string(file.read())

            print("Updated {} with latest version from disk".format(filename))

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


@bpy.app.handlers.persistent
def clean_modules(dummy):
    """Free any imported modules I.E Network to prevent state error"""
    unwanted_modules = set(sys.modules).difference(ORIGINAL_MODULES)
    for mod_name in unwanted_modules:
        sys.modules.pop(mod_name)

    return unwanted_modules


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

    except ImportError:
        return

    templates = template_module.templates
    templates.clear()

    required_templates = []
    for name, value in getmembers(module):
        if name.startswith("_"):
            continue

        if not isclass(value):
            continue

        if not issubclass(value, Replicable) or value is Replicable:
            continue

        if name in HIDDEN_BASES:
            continue

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


update_handlers.append(update_attributes)
update_handlers.append(update_network_logic)
update_handlers.append(update_text_files)
update_handlers.append(update_templates)
update_handlers.append(update_use_network)


registered = False


def register():
    global registered

    if registered:
        return

    bpy.utils.register_module(__name__)

    bpy.app.handlers.scene_update_post.append(on_update)
    bpy.app.handlers.save_post.append(on_save)
    bpy.app.handlers.game_pre.append(on_save)
    bpy.app.handlers.game_pre.append(clean_modules)
    bpy.app.handlers.game_pre.append(reload_text_files)

    registered = True


def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.app.handlers.scene_update_post.remove(on_update)
    bpy.app.handlers.save_post.remove(on_save)
    bpy.app.handlers.game_pre.remove(on_save)
    bpy.app.handlers.game_pre.remove(clean_modules)

    unloaded = clean_modules(None)
    print("Unloaded {}".format(unloaded))

    global registered
    registered = False