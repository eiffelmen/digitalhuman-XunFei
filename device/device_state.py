class State:
    SLEEP = 0
    WORK = 1


class DeviceState:
    def __init__(self):
        self._state: State = State.SLEEP
