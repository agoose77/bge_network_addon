from network.signals import Signal


class ControllerPendingAssignmentSignal(Signal):
    pass


class ControllerAssignedSignal(Signal):
    pass


class ControllerReassignedSignal(Signal):
    pass


class OnInitialisedMessageSignal(Signal):
    pass


class RegisterStateSignal(Signal):
    pass


class NetmodeAssignedSignal(Signal):
    pass