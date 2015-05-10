from contextlib import contextmanager
from bpy import types

busy_operations = set()


@contextmanager
def if_not_busy(identifier):
    if identifier in busy_operations:
        return

    busy_operations.add(identifier)
    try:
        yield
    finally:
        busy_operations.remove(identifier)


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
    return [(x.upper(), x.replace('_', ' ').title(), "{} {}".format(x.capitalize(), enum_name), i)
            for i, x in enumerate(enum.values)]


def type_to_enum_type(type_):
    types = {int: "INT", float: "FLOAT", str: "STRING", bool: "BOOL"}
    return types[type_]


def update_item(source, destination, destination_data=None):
    try:
        item_dict = dict(source.items())

    except TypeError:
        invalid_members = list(dir(types.Struct)) + ['rna_type']
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