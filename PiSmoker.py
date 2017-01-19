import Queue
import logging
import logging.config
import time

import numpy as np
import FB_Handler
import PiSmoker_Backend

import LCDDisplay
import MAX31865
import PID as PID
import Traeger

# Parameters
FB_URL = 'https://pismoker.firebaseio.com/'
PIDCycleTime = 20  # Frequency to update control loop
U_MIN = 0.15  # Maintenance level
U_MAX = 1.0  #
IGNITER_TEMP = 100  # Temperature to start igniter
SHUTDOWN_TIME = 10 * 60  # Time to run fan after shutdown
Relays = {'auger': 22, 'fan': 18, 'igniter': 16}  # Board

logger = None


class PiSmoker(object):
    Parameters = None
    TempInterval = 3  # Frequency to record temperatures
    TempRecord = 60  # Period to record temperatures in memory
    db = None  # type: PiSmoker_Backend.PiSmoker_Backend
    relays = {'auger': 25, 'fan': 24, 'igniter': 23}  # BCM
    G = None  # type: Traeger.Traeger
    Program = []
    qT = qR = qP = None  # type: Queue.Queue
    Control = None  # type: PID.PID
    Temps = None  # type: list

    def __init__(self, db, qT=None, qR=None, qP=None, relays=None):
        """

        @param db: Database backend, expects methods from PiSmoker_Backend
        @type db: PiSmoker_Backend.PiSmoker_Backend
        @param relays: [Optional]Dictionary of relay names and GPIO pins
        @type relays: dict
        """
        self.Parameters = {'mode':          'Off', 'target': 225, 'PB': 60.0, 'Ti': 180.0, 'Td': 45.0, 'CycleTime': 20,
                           'u':             0.15, 'PMode': 2.0, 'program': False,
                           'ProgramToggle': time.time()}  # 60,180,45 held +- 5F
        # Initialize Traeger Object
        if relays:
            self.relays = relays
        self.G = Traeger.Traeger(self.relays)
        self.db = db

        self.qT = qT or Queue.Queue()
        self.qR = qR or Queue.Queue()
        self.qP = qP or Queue.Queue()
        # PID controller based on proportional band in standard PID form https://en.wikipedia.org/wiki/PID_controller#Ideal_versus_standard_PID_form
        # u = Kp (e(t)+ 1/Ti INT + Td de/dt)
        # PB = Proportional Band
        # Ti = Goal of eliminating in Ti seconds (Make large to disable integration)
        # Td = Predicts error value at Td in seconds

        # Start controller
        self.Control = PID.PID(self.Parameters['PB'], self.Parameters['Ti'], self.Parameters['Td'])
        self.Control.setTarget(self.Parameters['target'])

        self.Temps = []
        # Set mode
        self.ModeUpdated()

    def RecordTemps(self, T):
        now = time.time()
        if not self.Temps or now - self.Temps[-1][0] > self.TempInterval:
            Ts = [now]
            for t in T:
                Ts.append(t.read())
            self.Temps.append(Ts)
            self.db.PostTemps(self.Parameters['target'], Ts)

            # TODO: Replace with peek and pop type operations.
            # Clean up old temperatures
            NewTemps = []
            for Ts in self.Temps:
                if now - Ts[0] < self.TempRecord:  # Still valid
                    NewTemps.append(Ts)

            # Push temperatures to LCD
            self.qT.put(Ts)

    def readLCD(self):
        NewParameters = {}
        while not self.qR.empty():
            NewParameters.update(self.qR.get())
        return NewParameters

    def UpdateParameters(self):
        # Loop through each key, see what changed
        NewParameters = self.db.ReadParameters()
        NewParameters.update(self.readLCD())
        for k in NewParameters.keys():
            logger.info('New self.Parameters: %s -- %r (%r)', k, float(NewParameters[k]), self.Parameters[k])
            if k == 'target':
                if float(self.Parameters[k]) != float(NewParameters[k]):
                    self.Control.setTarget(float(NewParameters[k]))
                    self.Parameters[k] = float(NewParameters[k])
            elif k in ['PB', 'Ti', 'Td']:
                if float(self.Parameters[k]) != float(NewParameters[k]):
                    self.Parameters[k] = float(NewParameters[k])
                    self.Control.setGains(self.Parameters['PB'], self.Parameters['Ti'], self.Parameters['Td'])
                    self.db.WriteParameters(self.Parameters)
            elif k == 'PMode':
                if float(self.Parameters[k]) != float(NewParameters[k]):
                    self.Parameters[k] = float(NewParameters[k])
                    self.ModeUpdated()
                    self.db.WriteParameters(self.Parameters)
            elif k == 'mode':
                if self.Parameters[k] != NewParameters[k]:
                    self.Parameters[k] = NewParameters[k]
                    self.ModeUpdated()
                    self.db.WriteParameters(self.Parameters)
            elif k == 'program':
                if self.Parameters[k] != NewParameters[k]:
                    self.Parameters[k] = NewParameters[k]
                    self.Parameters['LastReadProgram'] = time.time() - 10000
                    self.ReadProgram()
                    self.ProcessProgram()
                    # TODO: Figure out reason for break after program
                    # break  # Stop processing new parameters - not sure why?
        # Write parameters back after all changes have been handled.
        self.db.WriteParameters(self.Parameters)

    def GetAverageSince(self, startTime):
        # TODO: Rolling average
        n = 0
        sum = [0] * len(self.Temps[0])
        for Ts in self.Temps:
            if Ts[0] < startTime:
                continue
            for i in range(0, len(Ts)):  # Add
                sum[i] += Ts[i]

            n += 1

        Avg = np.array(sum) / n

        return Avg.tolist()

    # Modes
    def ModeUpdated(self):
        if self.Parameters['mode'] == 'Off':
            logger.info('Setting mode to Off')
            self.G.Initialize()

        elif self.Parameters['mode'] == 'Shutdown':
            self.G.Initialize()
            self.G.SetState('fan', True)

        elif self.Parameters['mode'] == 'Start':
            self.G.SetState('fan', True)
            self.G.SetState('auger', True)
            self.G.SetState('igniter', True)
            self.Parameters['CycleTime'] = 15 + 45
            self.Parameters['u'] = 15.0 / (15.0 + 45.0)  # P0

        elif self.Parameters['mode'] == 'Smoke':
            self.G.SetState('fan', True)
            self.G.SetState('auger', True)
            self.CheckIgniter()
            On = 15
            Off = 45 + self.Parameters['PMode'] * 10  # http://tipsforbbq.com/Definition/Traeger-P-Setting
            self.Parameters['CycleTime'] = On + Off
            self.Parameters['u'] = On / (On + Off)

        elif self.Parameters['mode'] == 'Ignite':  # Similar to smoke, with igniter on
            self.G.SetState('fan', True)
            self.G.SetState('auger', True)
            self.G.SetState('igniter', True)
            On = 15
            Off = 45 + self.Parameters['PMode'] * 10  # http://tipsforbbq.com/Definition/Traeger-P-Setting
            self.Parameters['CycleTime'] = On + Off
            self.Parameters['u'] = On / (On + Off)

        elif self.Parameters['mode'] == 'Hold':
            self.G.SetState('fan', True)
            self.G.SetState('auger', True)
            self.CheckIgniter()
            self.Parameters['CycleTime'] = PIDCycleTime
            self.Parameters['u'] = U_MIN  # Set to maintenance level

        self.WriteParameters()

    def DoMode(self):
        now = time.time()
        if self.Parameters['mode'] == 'Off':
            pass

        elif self.Parameters['mode'] == 'Shutdown':
            if (now - self.G.ToggleTime['fan']) > SHUTDOWN_TIME:
                self.Parameters['mode'] = 'Off'
                self.ModeUpdated()

        elif self.Parameters['mode'] == 'Start':
            self.DoAugerControl()
            self.G.SetState('igniter', True)
            if self.Temps[-1][1] > 115:
                self.Parameters['mode'] = 'Hold'
                self.ModeUpdated()

        elif self.Parameters['mode'] == 'Smoke':
            self.DoAugerControl()

        elif self.Parameters['mode'] == 'Ignite':
            self.DoAugerControl()
            self.G.SetState('igniter', True)

        elif self.Parameters['mode'] == 'Hold':
            self.DoControl()
            self.DoAugerControl()

    def WriteParameters(self):
        """Write parameters to file"""

        for r in self.relays:
            self.Parameters[r] = self.G.GetState(r)

        self.Parameters['LastWritten'] = time.time()
        self.qP.put(self.Parameters)

        self.db.WriteParameters(self.Parameters)

    def DoAugerControl(self):
        # Auger currently on AND TimeSinceToggle > Auger On Time
        if self.G.GetState('auger') and (time.time() - self.G.ToggleTime['auger']) > self.Parameters['CycleTime'] * self.Parameters['u']:
            if self.Parameters['u'] < 1.0:
                self.G.SetState('auger', False)
                self.WriteParameters()
            self.CheckIgniter()

        # Auger currently off AND TimeSinceToggle > Auger Off Time
        if (not self.G.GetState('auger')) and (time.time() - self.G.ToggleTime['auger']) > self.Parameters['CycleTime'] * (
                    1 - self.Parameters['u']):
            self.G.SetState('auger', True)
            self.CheckIgniter()
            self.WriteParameters()

    def CheckIgniter(self):
        # Check if igniter needed
        if self.Temps[-1][1] < IGNITER_TEMP:
            self.G.SetState('igniter', True)
        else:
            self.G.SetState('igniter', False)

        # Check if igniter has been running for too long
        if (time.time() - self.G.ToggleTime['igniter']) > 1200 and self.G.GetState('igniter'):
            logger.info('Disabling igniter due to timeout')
            self.G.SetState('igniter', False)
            self.Parameters['mode'] = 'Shutdown'
            self.ModeUpdated()

    def DoControl(self):
        if (time.time() - self.Control.LastUpdate) > self.Parameters['CycleTime']:
            # TODO: Replace with stored sliding window average computed as they are updated.
            Avg = self.GetAverageSince(self.Control.LastUpdate)
            self.Parameters['u'] = self.Control.update(Avg[1])  # Grill probe is [0] in T, [1] in Temps
            self.Parameters['u'] = max(self.Parameters['u'], U_MIN)
            self.Parameters['u'] = min(self.Parameters['u'], U_MAX)
            logger.info('u %f', self.Parameters['u'])

            # Post control state
            D = {'time': time.time() * 1000, 'u': self.Parameters['u'], 'P': self.Control.P, 'I': self.Control.I, 'D': self.Control.D,
                 'PID':  self.Control.u, 'Error': self.Control.error, 'Derv': self.Control.Derv, 'Inter': self.Control.Inter}

            self.db.WriteControl(D)

            self.WriteParameters()

        return self.Parameters

    def ReadProgram(self):
        # Check if program is new
        NewProgram = self.db.ReadProgram(self.Parameters['program'])
        if NewProgram and self.Program != NewProgram:
            logger.info('Detected new program')
        self.SetProgram(NewProgram)

    def EvaluateTriggers(self):
        now = time.time()
        if self.Parameters['program'] and len(self.Program) > 0:
            P = self.Program[0]

            if P['trigger'] == 'Time':
                if now - self.Parameters['ProgramToggle'] > float(P['triggerValue']):
                    self.NextProgram()

            elif P['trigger'] == 'MeatTemp':
                if self.Temps[-1][2] > float(P['triggerValue']):
                    self.NextProgram()

    def NextProgram(self):
        logger.info('Advancing to next program')
        self.Program.pop(0)  # Remove current program

        self.db.WriteProgram(self.Program)
        if len(self.Program) > 0:
            self.ProcessProgram()
        else:
            logger.info('Last program reached, disabling program')
            self.Parameters['program'] = False
            self.WriteParameters()

    def ProcessProgram(self):
        if len(self.Program) > 0:
            self.Parameters['ProgramToggle'] = time.time()

            P = self.Program[0]
            self.Parameters['mode'] = P['mode']
            self.ModeUpdated()

            self.Parameters['target'] = float(P['target'])
            self.Control.setTarget(self.Parameters['target'])
            self.WriteParameters()

        else:
            logger.info('Last program reached, disabling program')
            self.Parameters['program'] = False
            self.WriteParameters()

    def SetProgram(self, Program):
        self.Program = Program
        self.ProcessProgram()

def main(*args, **kwargs):
    # Start logging
    logging.config.fileConfig('/home/pi/PiSmoker/logging.conf')
    logger = logging.getLogger('PiSmoker')

    # Initialize RTD Probes
    T = []
    T.append(MAX31865.MAX31865(1, 1000, 4000, False))  # Grill
    T.append(MAX31865.MAX31865(0, 100, 400, True))  # Meat


    # Start firebase
    f = open('/home/pi/PiSmoker/AuthToken.txt', 'r')
    Secret = f.read()
    f.close()
    Params = {'print': 'silent'}
    Params = {'auth': Secret, 'print': 'silent'}  # ".write": "auth !== null"
    firebase_db = FB_Handler.Firebase_Backend(FB_URL, Secret)

    # Initialize LCD
    qP = Queue.Queue()  # Queue for Parameters
    qT = Queue.Queue()  # Queue for Temps
    qR = Queue.Queue()  # Return for Parameters
    qT.put([0, 0, 0])
    lcd = LCDDisplay.LCDDisplay(qP, qT, qR)
    lcd.setDaemon(True)
    lcd.start()

    ##############
    # Setup       #
    ##############

    # Default parameters
    Smoker = PiSmoker(firebase_db)

    # Setup variables
    Temps = []  # type: [[time, T[0], T[1],...],...]
    Program = []
    #Parameters['LastReadProgram'] = time.time()
    #Parameters['LastReadWeb'] = time.time()

    ###############
    # Main Loop    #
    ###############
    time.sleep(5)  # Wait for clock to sync
    try:
        while 1:
            # Record temperatures
            Smoker.RecordTemps(Temps)

            # Check for new parameters
            Smoker.UpdateParameters()

            # Check for new program
            Smoker.ProcessProgram()

            # Evaluate triggers
            Smoker.EvaluateTriggers()

            # Do mode
            Smoker.DoMode()

            time.sleep(0.05)
    except KeyboardInterrupt:
        retval = 0
    else:
        retval = 1
    finally:
        for relay in Relays:
            # Shutdown all relays if possible.
            G.SetState(relay_id=relay, state=False)
        return retval


if __name__ == '__main__':
    import sys

    retval = main()
    sys.exit(retval)
