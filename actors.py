from game_system.entities import Actor as _Actor


class SCAActor(_Actor):
    """Interface for SCA_ system with network system"""

    component_tags = tuple(_Actor.component_tags) + ("bge_addon",)

    def on_notify(self, name):
        super().on_notify(name)

        self.bge_addon.on_notify(name)

    def get_property(self, name):
        return self.bge_addon.get_property(name)

    def set_property(self, name, value):
        self.bge_addon.set_property(name, value)

    def dispatch_rpc(self, name, data):
        self.bge_addon.dispatch_rpc(name, data)

    def update(self, dt):
        pass