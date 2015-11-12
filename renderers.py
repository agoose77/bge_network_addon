from bpy import types, utils


class RENDER_RT_StateList(types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(item.netmode, icon="NONE")


class RENDER_RT_RPCArgumentList(types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        sub_layout = layout.split(0.8, True)
        sub_layout.label(item.name, icon="NONE")

        item_active = item.replicate

        row = layout.row()
        attr_icon = 'CHECKBOX_HLT' if item_active else 'CHECKBOX_DEHLT'
        row.prop(item, "replicate", text="", icon=attr_icon, emboss=False)


class RENDER_RT_AttributeList(types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(item.name, icon="NONE")
        row = layout.row(align=True)

        item_active = item.replicate

        row.prop(item, "replicate_for_owner", text="", icon='LOOP_BACK')
        row.prop(item, "replicate_after_initial", text="", icon='DOTSUP')
        row.active = item_active

        row = layout.row()
        attr_icon = 'MUTE_IPO_OFF' if item_active else 'MUTE_IPO_ON'
        row.prop(item, "replicate", text="", icon=attr_icon, emboss=False)


class RENDER_RT_TemplateDefaultList(types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        item_name = item.name.replace("_", " ").title()
        layout.label(item_name, icon="NONE")
        row = layout.row(align=True)
        value_name = item.value_name
        row.prop(item, value_name, text="")


class RENDER_RT_RPCList(types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "name", text="", emboss=False)

        reliable_icon = 'LIBRARY_DATA_DIRECT' if item.reliable else 'LIBRARY_DATA_INDIRECT'
        layout.prop(item, "reliable", text="", icon=reliable_icon, emboss=False)

        simulated_icon = 'SOLO_ON' if item.simulated else 'SOLO_OFF'
        layout.prop(item, "simulated", text="", icon=simulated_icon, emboss=False)


def register():
    utils.register_module(__name__)


def unregister():
    utils.unregister_module(__name__)