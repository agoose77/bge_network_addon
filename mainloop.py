from network.enums import Netmodes
from network.network import Network
from network.replicable import Replicable
from network.signals import SignalValue, DisconnectSignal, Signal
from network.world_info import WorldInfo

from game_system.signals import LogicUpdateSignal, TimerUpdateSignal, PlayerInputSignal
from game_system.timer import Timer

from interface import convert_data, resolve_netmode, initialise_network_obj, DATA_PATH, SETUP_OBJECTS
from json import load
from time import clock

import bge


def update_graphs():
    """Update isolated resource graphs"""
    Replicable.update_graph()
    Signal.update_graph()


def main():
    # Load configuration
    file_path = bge.logic.expandPath("//{}/{}".format(DATA_PATH, "main.definition"))
    with open(file_path, "r") as file:
        data = load(file)

    host = data['host']
    port = data['port']
    network_tick_rate = data['tick_rate']
    metric_interval = data['metric_interval']

    scenes_data = data['scenes']

    WorldInfo.netmode = resolve_netmode(data['netmode'])
    WorldInfo.tick_rate = bge.logic.getLogicTicRate()

    network = Network(host, port)

    # Main loop
    accumulator = 0.0
    last_time = last_sent_time = clock()

    requires_exit = SignalValue(False)

    convert_data()

    # Fixed time-step
    while not requires_exit.value:
        current_time = clock()

        # Determine delta time
        step_time = 1 / bge.logic.getLogicTicRate()
        delta_time = current_time - last_time
        last_time = current_time

        # Set upper bound
        if delta_time > 0.25:
            delta_time = 0.25

        accumulator += delta_time

        # Whilst we have enough time in the buffer
        while accumulator >= step_time:

            exit_key = bge.logic.getExitKey()

            if bge.logic.keyboard.events[exit_key] == bge.logic.KX_INPUT_JUST_ACTIVATED:
                # Exit immediately!
                if WorldInfo.netmode == Netmodes.server:
                    requires_exit.value = True

                else:
                    quit_func = lambda: setattr(requires_exit, "value", True)
                    DisconnectSignal.invoke(quit_func)
                    # Else abort
                    timeout = Timer(0.6)
                    timeout.on_target = quit_func

            # Handle this outside of usual update
            WorldInfo.update_clock(step_time)

            scene = bge.logic.getCurrentScene()
            scene_data = scenes_data[scene.name]

            uninitialised_objects = [o for o in scene.objects if o.name in scene_data and not o in SETUP_OBJECTS]

            for obj in uninitialised_objects:
                initialise_network_obj(obj)

            network.receive()
            update_graphs()

            # Update Timers
            TimerUpdateSignal.invoke(step_time)

            # Update Player Controller inputs for client
            if WorldInfo.netmode != Netmodes.server:
                PlayerInputSignal.invoke(step_time)
                update_graphs()

            # Update main logic (Replicable update)
            LogicUpdateSignal.invoke(step_time)
            update_graphs()

            bge.logic.NextFrame()

            # Transmit new state to remote peer
            is_full_update = ((current_time - last_sent_time) >= (1 / network_tick_rate))

            if is_full_update:
                last_sent_time = current_time

            network.send(is_full_update)

            network_metrics = network.metrics
            if network_metrics.sample_age >= metric_interval:
                network_metrics.reset_sample_window()

            current_time += step_time
            accumulator -= step_time


if __name__ == "__main__":
    main()