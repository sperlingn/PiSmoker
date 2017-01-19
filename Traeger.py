import RPi.GPIO as GPIO
import time, logging, logging.config

#Start logging
logging.config.fileConfig('/home/pi/PiSmoker/logging.conf')
logger = logging.getLogger(__name__)
class Traeger:
    Relays = []
    ToggleTime = {}
    GPIO_Invert = False

    def __init__(self, relays, invert=False):
        self.Relays = relays
        self.ToggleTime = dict()
        self.GPIO_Invert = invert
        self.Initialize()

    def Initialize(self):
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        for k in self.Relays.keys():
            GPIO.setup(self.Relays[k],GPIO.OUT)
            self.SetState(k,0)
            self.ToggleTime[k] = time.time()

    def GetState(self, relay_id):
        return not GPIO.input(self.Relays[relay_id])

    def SetState(self, relay_id, state):
        if not (self.GetState(relay_id) == state):
            logger.info('Toggling %s: %d', relay_id, state)
        self.ToggleTime[relay_id] = time.time()
        GPIO.output(self.Relays[relay_id], state != self.GPIO_Invert)

    def toggle(self, relay_id):

