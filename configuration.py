from network.enums import Roles, Netmodes
from .utilities import get_bpy_enum, type_to_enum_type


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
ASSETS_FILENAME = "assets.blend"
REQUIRED_FILES = MAINLOOP_FILENAME, INTERFACE_FILENAME, RULES_FILENAME, SIGNALS_FILENAME, ACTORS_FILENAME

DISPATCHER_NAME = "DISPATCHER"
DISPATCHER_MARKER = "_DISPATCHER"

DEFAULT_TEMPLATE_MODULES = {"game_system.entities": [], "actors": ("SCAActor",)}
HIDDEN_BASES = "Actor",