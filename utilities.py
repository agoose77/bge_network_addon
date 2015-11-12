from contextlib import contextmanager
from bpy import types
from inspect import isclass
import sys

from network.replicable import Replicable

busy_operations = set()
template_modules = {}


@contextmanager
def if_not_busy(identifier):
    if identifier in busy_operations:
        return

    busy_operations.add(identifier)
    try:
        yield
    finally:
        busy_operations.remove(identifier)


def load_template(path):
    cls, loaded_modules = load_class_from_module(path)

    # Add counter here
    info = template_modules.setdefault(path, [loaded_modules, 0])

    if loaded_modules:
        info[1] += 1

    return cls


def unload_template(path):
    if path in template_modules:
        info = template_modules[path]
        info[1] -= 1

        if not info[1]:
            print("ULOADE", info[0])
            for mod_name in info[0]:
                sys.modules.pop(mod_name)

            template_modules.pop(path)


def load_class_from_module(path):
    *module_parts, class_name = path.split(".")
    module_path = '.'.join(module_parts)

    pre_modules = sys.modules.copy()
    module = __import__(module_path, fromlist=[class_name])
    loaded_modules = set(sys.modules) - pre_modules.keys()

    cls = getattr(module, class_name)
    return cls, loaded_modules


def is_replicable(obj):
    if not isclass(obj):
        return False

    if not issubclass(obj, Replicable) or obj is Replicable:
        return False

    return True


def get_active_item(collection, index):
    if index >= len(collection):
        return None

    return collection[index]


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


def get_bpy_enum(enum):
    enum_name = enum.__name__.rstrip("s").lower()
    print(list(enum))
    return [(x.upper(), x.replace('_', ' ').title(), "{} {}".format(x.capitalize(), enum_name), 'BLANK1', v)
            for x, v in enum]


def type_to_enum_type(type_):
    types = {int: "INT", float: "FLOAT", str: "STRING", bool: "BOOL"}
    return types[type_]


def copy_logic_properties_to_collection(source, destination, condition=None):
    visited_keys = set()

    for source_property in source:
        if callable(condition) and not condition(source_property):
            continue

        prop_name = source_property.name

        try:
            target_property = destination[prop_name]

        except KeyError:
            target_property = destination.add()

        target_property.name = source_property.name
        target_property.type = source_property.type

        visited_keys.add(prop_name)

    # Remove non existent values
    destination_keys = {a.name for a in destination}
    for key in (destination_keys - visited_keys):
        index = destination.find(key)
        destination.remove(index)