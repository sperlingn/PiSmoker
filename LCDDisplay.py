import logging.config
from threading import Thread
from time import sleep

# import Adafruit_CharLCD as LCD
from Queue import Queue

import FakeLCD as LCD

buttons = ((LCD.SELECT, 'Mode'),
           (LCD.LEFT, 'Left'),
           (LCD.UP, 'Up'),  # Hardware snafu
           (LCD.DOWN, 'Down'),
           (LCD.RIGHT, 'Right'))

Modes = ('Off', 'Start', 'Smoke', 'Hold', 'Ignite', 'Shutdown')

# Start logging
logging.config.fileConfig('/home/pi/PiSmoker/logging.conf')
logger = logging.getLogger(__name__)


# noinspection PyBroadException
class LCDDisplay(Thread):
    qP = qT = qR = None  # type: Queue
    Parameters = None  # type: dict
    Ts = None  # type: list

    def __init__(self, qP, qT, qR):
        super(LCDDisplay, self).__init__()
        try:
            self.lcd = LCD.Adafruit_CharLCDPlate()
        except:
            logger.info('Unable to initialize LCD')

        self.qP = qP
        self.qT = qT
        self.qR = qR
        self.Ts = {'time': 0, 'grill': 0, 'meat1': 0}
        self.Parameters = {'target': 0, 'mode': '', 'PMode': ''}

        self.Display = ''

    def run(self):
        while True:
            self.GetButtons()
            while not self.qP.empty():
                self.Parameters = self.qP.get()
            while not self.qT.empty():
                self.Ts = self.qT.get()

            self.UpdateDisplay()
            sleep(0.05)

    def UpdateDisplay(self):
        text = 'T%i G%i M%i'.ljust(16) % (self.Parameters['target'], self.Ts['grill'], self.Ts['meat1'])
        text += '\n'
        if self.Parameters['mode'] == 'Hold' or self.Parameters['mode'] == 'Start':
            text += '%s %3.2f   %s' % (self.Parameters['mode'].ljust(5), self.Parameters['u'], self.GetCurrentState())
        elif self.Parameters['mode'] == 'Smoke':
            text += '%s P:%i    %s' % (
                self.Parameters['mode'].ljust(5), self.Parameters['PMode'], self.GetCurrentState())
        else:
            text += '%s' % (self.Parameters['mode'].ljust(16))

        self.Send2Display(text)

    def Send2Display(self, text):
        if self.Display != text:
            try:
                self.lcd.clear()
                self.lcd.message(text)
                self.Display = text
            except:
                logger.info('Unable to update LCD - %s', text)

    def GetButtons(self):
        for button in buttons:
            try:
                if self.lcd.is_pressed(button[0]):
                    if button[1] == 'Mode':
                        NewMode = self.GetCurrentMode() + 1
                        if NewMode == len(Modes):
                            NewMode = 0
                        NewParameters = {'mode': Modes[NewMode]}
                        self.qR.put(NewParameters)
                    elif button[1] == 'Up':
                        if self.Parameters['mode'] == 'Smoke':
                            NewParameters = {'PMode': self.Parameters['PMode'] + 1}
                        else:
                            NewParameters = {'target': self.Parameters['target'] + 5}
                        self.qR.put(NewParameters)
                    elif button[1] == 'Down':
                        if self.Parameters['mode'] == 'Smoke':
                            NewParameters = {'PMode': self.Parameters['PMode'] - 1}
                        else:
                            NewParameters = {'target': self.Parameters['target'] - 5}
                        self.qR.put(NewParameters)
                    sleep(0.03)
            except:
                logger.info('Unable to read buttons')

    def GetCurrentMode(self):
        for i in range(len(Modes)):
            if self.Parameters['mode'] == Modes[i]:
                return i

    def GetCurrentState(self):
        State = ''
        if self.Parameters['fan']:
            State += 'F'
        else:
            State += ' '

        if self.Parameters['igniter']:
            State += 'I'
        else:
            State += ' '

        if self.Parameters['auger']:
            State += 'A'
        else:
            State += ' '

        return State
