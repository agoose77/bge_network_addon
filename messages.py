message_subjects = dict(CONTROLLER_REQUEST="CONTROLLER_REQUEST")

# Prefixes for messages associated with replicables
message_prefixes_unique = dict(
    CONTROLLER_ASSIGN="CONTROLLER_ASSIGN_",
    CONTROLLER_REASSIGN="CONTROLLER_REASSIGN_",

    RPC_INVOKE="@",
    NOTIFICATION="!",
    SELF_MESSAGE="::",
    METHOD_INVOKE="#",
    NEW_PAWN="NEW_PAWN::"
    )


message_prefixes_global = dict(
    SET_NETMODE="NETMODE=",
    SCENE_MESSAGE="SCENE::",
    )
