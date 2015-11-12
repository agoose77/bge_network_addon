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

# CREATE_PAWN
#


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
