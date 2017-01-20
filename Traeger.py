import RPi.GPIO as GPIO
import time, logging, logging.config

#Start logging
logging.config.fileConfig('/home/pi/PiSmoker/logging.conf')
logger = logging.getLogger(__name__)
class Traeger:
    Relays = None  # type: list
    ToggleTime = None  # type: dict
    GPIO_Invert = False  # type: bool
    __GPIO_MODE = GPIO.BCM

    def __init__(self, relays, invert=False):
        self.Relays = relays
        self.ToggleTime = dict()
        self.GPIO_Invert = bool(invert)

    def Initialize(self):
        GPIO.setwarnings(False)
        GPIO.setmode(self.__GPIO_MODE)
        for k in self.Relays.keys():
            GPIO.setup(self.Relays[k],GPIO.OUT)
            self.SetState(k,0)
            self.ToggleTime[k] = time.time()

    def GetState(self, relay_id):
        return GPIO.input(self.Relays[relay_id]) != self.GPIO_Invert

    def SetState(self, relay_id, state):
        state = bool(state)
        if self.GetState(relay_id) != state:
            logger.info('Toggling %s: %s', relay_id, state and 'On' or 'Off')
        self.ToggleTime[relay_id] = time.time()
        GPIO.output(self.Relays[relay_id], state != self.GPIO_Invert)

    def toggle(self, relay_id):
        self.SetState(relay_id, not self.GetState(relay_id))
