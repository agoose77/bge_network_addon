from game_system.entities import Actor as _Actor


class SCAActor(_Actor):
    """Interface for SCA_ system with network system"""

    component_tags = tuple(_Actor.component_tags) + ("bge_addon",)

    def on_notify(self, name):
        super().on_notify(name)

        self.bge_addon.on_notify(name)

    def update(self, dt):
        pass