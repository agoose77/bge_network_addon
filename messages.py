from collections import OrderedDict
from json import dumps, loads

message_subjects = dict(CONTROLLER_REQUEST="CONTROLLER_REQUEST")

# Prefixes for messages associated with replicables
message_prefixes_replicable = dict(
    CONTROLLER_REASSIGN="CHANGE_PAWN::",

    RPC_INVOKE="@",
    NOTIFICATION="!",
    SELF_MESSAGE="->",
    METHOD_INVOKE="#",
    NEW_PAWN="NEW_PAWN->"
    )


message_prefixes_global = dict(
    SET_NETMODE="NETMODE=",
    CONNECT_TO="CONNECT->"
    )

message_prefixes_scene = dict(
    SCENE_MESSAGE="SCENE->",
    CONTROLLER_ASSIGN="NEW_PAWN=",
)


all_message_prefixes = message_prefixes_replicable.copy()
all_message_prefixes.update(message_prefixes_scene)
all_message_prefixes.update(message_prefixes_global)


def convert_object_message_logic(message_logic_bricks, prefix_dictionary, get_request=None):
    """Convert logic bricks which use SCENE message API"""
    # Convert sensors
    for message_handler in message_logic_bricks:
        message_subject = message_handler.subject

        # Find in scene prefixes
        try:
            identifier, request = prefix_identifier_from_subject(message_subject, prefix_dictionary)

        except ValueError:
            continue

        if get_request is not None:
            request = get_request(identifier, request)

        message_handler.subject = encode_subject(identifier, request)


def prefix_identifier_from_subject(subject, prefix_dictionary=None):
    if prefix_dictionary is None:
        prefix_dictionary = all_message_prefixes

    for identifier, prefix in prefix_dictionary.items():
        if subject.startswith(prefix):
            return identifier, subject[len(prefix):]

    raise ValueError("Invalid subject")


def encode_subject(identifier, subject=''):
    return "${}${}".format(identifier, subject)


def decode_subject(encoded_subject):
    if encoded_subject[0] != "$":
        raise ValueError

    after_first_char = encoded_subject[1:]
    end_index = after_first_char.find("$")
    if end_index == -1:
        raise ValueError

    identifier = after_first_char[:end_index]
    subject = after_first_char[end_index + 1:]
    return identifier, subject


def encode_object(subject, obj):
    scene = obj.scene
    scene_id = id(scene)
    obj_id = id(obj)
    return dumps((scene_id, obj_id, subject))


def decode_object(encoded_subject):
    from bge import logic

    scene_id, obj_id, subject = loads(encoded_subject)

    for scene in logic.getSceneList():
        if id(scene) == scene_id:
            break

    else:
        raise ValueError("No BGE scene with id {} found".format(scene_id))

    obj = scene.objects.from_id(obj_id)
    return subject, obj


def encode_replicable_info(subject, replicable):
    return dumps((subject, replicable.scene.name, replicable.unique_id))


def encode_scene_info(subject, scene):
    return dumps((subject, scene.name))


def decode_scene_info(world, encoded_subject):
    subject, scene_id = loads(encoded_subject)
    scene = world.scenes[scene_id]
    return subject, scene


def decode_replicable_info(world, encoded_subject):
    subject, scene_id, replicable_id = loads(encoded_subject)

    scene = world.scenes[scene_id]
    replicable = scene.replicables[replicable_id]

    return subject, replicable
