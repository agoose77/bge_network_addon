from bpy import types, props, utils

from .utilities import unload_template

_check_for_updates = None


def set_check_for_updates(func):
    global _check_for_updates
    _check_for_updates = func


class LOGIC_OT_add_rpc(types.Operator):
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


class LOGIC_OT_remove_rpc(types.Operator):
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


class LOGIC_OT_add_template_class(types.Operator):
    """Load templates from a module"""
    bl_idname = "network.set_template_class"
    bl_label = "Add template module"

    path = props.StringProperty(name="Path", description="Path to template module")

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        obj = context.active_object
        path = self.path

        template_module = obj.template
        template_module.import_path = path

        return {'FINISHED'}


class LOGIC_OT_remove_template_class(types.Operator):
    """Unload template from a module"""
    bl_idname = "network.remove_template_class"
    bl_label = "Remove template class"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        template = obj.template

        template.defaults.clear()
        template.defaults_active = 0

        unload_template(template.import_path)
        print("UNLOADed")

        template.import_path = ""

        return {'FINISHED'}


class LOGIC_OT_set_states_from_visible(types.Operator):
    """Write currently visible states to mask for this netmode"""
    bl_idname = "network.set_states_from_visible"
    bl_label = "Save logic states for this netmode"

    mode = props.EnumProperty(items=(("states", "states", "states"),
                                     ("simulated_states", "simulated_states", "simulated_states")),
                            default="states")

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object

        mode_states = obj.states[obj.states_index]
        states = getattr(mode_states, self.mode)
        states[:] = obj.game.states_visible

        return {'FINISHED'}


class LOGIC_OT_show_states(types.Operator):
    """Read currently visible states from mask for this netmode"""
    bl_idname = "network.show_states"
    bl_label = "Set the states for this netmode visible"

    index = props.IntProperty()

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object

        active_state_group = obj.states[self.index]
        obj.game.states_visible = active_state_group.states

        for area in context.screen.areas:
            if area.type != 'LOGIC_EDITOR':
                continue

            area.tag_redraw()

        return {'FINISHED'}


class LOGIC_OT_select_network_objects(types.Operator):
    """Create group for network objects in scene"""
    bl_idname = "network.select_all"
    bl_label = "Select all network objects"

    def execute(self, context):
        for obj in context.scene.objects:
            obj.select = obj.use_network

        return {'FINISHED'}


class WM_OT_info_operator(types.Operator):
    bl_idname = "wm.display_info"
    bl_label = "Popup Message"

    message = props.StringProperty(name="Message")

    def execute(self, context):
        self.report({'INFO'}, self.message)
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout

        col = layout.column()
        col.label(text=self.message, icon='INFO')


class LOGIC_OT_check_for_updates(types.Operator):
    """Create group for network objects in scene"""
    bl_idname = "network.check_for_updates"
    bl_label = "Check for updates to network systems"

    def execute(self, context):
        if callable(_check_for_updates):
            _check_for_updates()
            print("UPDATE")

        return {'FINISHED'}


def register():
    utils.register_module(__name__)


def unregister():
    utils.unregister_module(__name__)