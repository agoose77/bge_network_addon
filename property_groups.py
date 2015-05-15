from bpy import types, props, utils

from .configuration import NETWORK_ENUMS, TYPE_ENUMS
from .utilities import determine_mro


class AttributeGroup(types.PropertyGroup):

    """PropertyGroup for Actor attributes"""

    name = props.StringProperty(description="Name of network attribute")
    type = props.StringProperty(description="Data type of network attribute")

    replicate = props.BoolProperty(default=False, description="Replicate this attribute")

    replicate_for_owner = props.BoolProperty(default=False, description="Replicate this attribute to the owner "
                                                                            "client")
    replicate_after_initial = props.BoolProperty(default=True, description="Replicate this attribute after initial "
                                                                               "replication")


utils.register_class(AttributeGroup)


class RPCArgumentGroup(types.PropertyGroup):

    """PropertyGroup for RPC arguments"""

    name = props.StringProperty(description="Name of RPC argument")
    type = props.StringProperty(description="Data type of RPC argument")

    replicate = props.BoolProperty(default=False, description="Replicate this attribute")


utils.register_class(RPCArgumentGroup)


class RPCGroup(types.PropertyGroup):

    """PropertyGroup for RPC calls"""

    name = props.StringProperty(default="Function", description="Name of RPC call")
    reliable = props.BoolProperty(default=False, description="Guarantee delivery of RPC call")
    simulated = props.BoolProperty(default=False, description="Allow execution for simulated proxies")
    target = props.EnumProperty(items=NETWORK_ENUMS, description="Netmode of RPC target")

    arguments = props.CollectionProperty(type=RPCArgumentGroup)
    arguments_index = props.IntProperty()


utils.register_class(RPCGroup)


class StateGroup(types.PropertyGroup):

    """PropertyGroup for RPC calls"""

    name = props.StringProperty(description="Netmode to which these states belong")
    states = props.BoolVectorProperty(size=30)


utils.register_class(StateGroup)


class TemplateAttributeDefault(types.PropertyGroup):

    @property
    def hash(self):
        return str(hash(getattr(self, self.value_name)))

    @property
    def value_name(self):
        return "value_{}".format(self.type.lower())

    @property
    def value(self):
        return getattr(self, self.value_name)

    @value.setter
    def value(self, value):
        setattr(self, self.value_name, value)

    name = props.StringProperty(description="Name of template attribute default value")
    type = props.EnumProperty(description="Data type of template attribute default value", items=TYPE_ENUMS)

    value_int = props.IntProperty()
    value_float = props.FloatProperty()
    value_string = props.StringProperty()
    value_bool = props.BoolProperty()


utils.register_class(TemplateAttributeDefault)


class ResolvedTemplateAttributeDefault(types.PropertyGroup):

    @property
    def hash(self):
        return str(hash(getattr(self, self.value_name)))

    @property
    def value_name(self):
        return "value_{}".format(self.type.lower())

    @property
    def value(self):
        return getattr(self, self.value_name)

    @value.setter
    def value(self, value):
        setattr(self, self.value_name, value)

    @property
    def modified(self):
        return self.hash != self.original_hash

    original_hash = props.StringProperty()
    name = props.StringProperty(description="Name of resolved template attribute default value")
    type = props.EnumProperty(description="Data type of resolved template attribute default value",
                              items=TYPE_ENUMS)

    value_int = props.IntProperty()
    value_float = props.FloatProperty()
    value_string = props.StringProperty()
    value_bool = props.BoolProperty()


utils.register_class(ResolvedTemplateAttributeDefault)


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

            destination.name = source.name
            destination.type = source.type
            destination.value = source.value

            destination.original_hash = source.hash


class TemplateClass(types.PropertyGroup):
    """PropertyGroup for Template items"""

    name = props.StringProperty(description="Name of template class")
    active = props.BoolProperty(description="Inherit this template class", update=on_template_updated)
    required = props.BoolProperty(description="If this template class is required by default")

    defaults = props.CollectionProperty(type=TemplateAttributeDefault)
    defaults_active = props.IntProperty()


utils.register_class(TemplateClass)


class TemplateModule(types.PropertyGroup):
    """PropertyGroup for Template collections"""

    name = props.StringProperty(name="Template Path", default="", description="Full path of template")
    loaded = props.BoolProperty(default=False, description="Flag to prevent reloading")
    templates = props.CollectionProperty(type=TemplateClass)
    templates_active = props.IntProperty()


utils.register_class(TemplateModule)
