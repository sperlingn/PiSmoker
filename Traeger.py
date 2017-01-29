import logging.config
from time import time

import RPi.GPIO as GPIO

# Start logging
logging.config.fileConfig('/home/pi/PiSmoker/logging.conf')
logger = logging.getLogger(__name__)


class Traeger:
    _relays = None  # type: list
    ToggleTime = None  # type: dict
    GPIO_Invert = False  # type: bool
    _GPIO_MODE = GPIO.BCM

    def __init__(self, relays, invert=False):
        self._relays = relays
        self.ToggleTime = dict()
        self.GPIO_Invert = bool(invert)

    def Initialize(self):
        GPIO.setwarnings(False)
        GPIO.setmode(self._GPIO_MODE)
        for k in self._relays:
            GPIO.setup(self._relays[k], GPIO.OUT)
            self.SetState(k, 0)
            self.ToggleTime[k] = time()

    def GetState(self, relay_id):
        return GPIO.input(self._relays[relay_id]) != self.GPIO_Invert

    def SetState(self, relay_id, state):
        state = bool(state)
        if self.GetState(relay_id) != state:
            logger.info('Toggling %s: %s', relay_id, state and 'On' or 'Off')
        self.ToggleTime[relay_id] = time()
        GPIO.output(self._relays[relay_id], state != self.GPIO_Invert)

    def toggle(self, relay_id):
        self.SetState(relay_id, not self.GetState(relay_id))
