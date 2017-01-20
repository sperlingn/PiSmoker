from Queue import Queue
from logging import getLogger, config
from time import sleep, time

from numpy import array

from PiSmoker_Backend import PiSmoker_Backend
from FB_Handler import Firebase_Backend
from LCDDisplay import LCDDisplay

from MAX31865 import MAX31865
from ADS1118 import ADS1118
from TemperatureProbe import TemperatureProbe, RTD, THERMISTOR, THERMOCOUPLE

from PID import PID
from Traeger import Traeger

FB_URL = 'https://pismoker.firebaseio.com/'
PIDCycleTime = 20  # Frequency to update control loop
U_MIN = 0.15  # Maintenance level
U_MAX = 1.0  #
IGNITER_TEMP = 100  # Temperature to start igniter
SHUTDOWN_TIME = 10 * 60  # Time to run fan after shutdown

_BUS = 1
_MAX_CS = 0
_ADS_CS = 1
_MCS_CS = 2
# Relays = {'auger': 22, 'fan': 18, 'igniter': 16}  # Board

logger = None


class PiSmoker_Parameters(dict):
    """
    Modification of dict class to implement on_update callbacks
    """
    __setter_cb = None  # Signature:

    def __init__(self, __setter_callback=None, *args, **kwargs):
        super(PiSmoker_Parameters, self).__init__(*args, **kwargs)

        if __setter_callback:
            self._set_cb = __setter_callback

    def __setitem__(self, key, value):
        super(PiSmoker_Parameters, self).__setitem__(key, value)
        if self.__setter_cb:
            self.__setter_cb(key, value)


class PiSmoker(object):
    Parameters = None  # type: PiSmoker_Parameters
    TempInterval = 3  # Frequency to record temperatures
    TempRecord = 60  # Period to record temperatures in memory
    db = None  # type: PiSmoker_Backend
    relays = {'auger': 25, 'fan': 24, 'igniter': 23}  # BCM
    G = None  # type: Traeger
    Program = []
    qT = qR = qP = None  # type: Queue
    Control = None  # type: PID
    Temps = None  # type: list

    def __init__(self, db, qT=None, qR=None, qP=None, relays=None):
        """

        @param db: Database backend, expects methods from PiSmoker_Backend
        @type db: PiSmoker_Backend.PiSmoker_Backend
        @param relays: [Optional]Dictionary of relay names and GPIO pins
        @type relays: dict
        """
        self.Parameters = PiSmoker_Parameters(
                {'mode':  'Off', 'target': 225, 'PB': 60.0, 'Ti': 180.0, 'Td': 45.0, 'CycleTime': 20, 'u': 0.15,
                 'PMode': 2.0, 'program': False, 'ProgramToggle': time()},
                __setter_callback__=self.ParameterUpdateCallback)  # 60,180,45 held +- 5F
        # Initialize Traeger Object
        if relays:
            self.relays = relays
        self.G = Traeger(self.relays)
        self.db = db

        self.qT = qT or Queue()
        self.qR = qR or Queue()
        self.qP = qP or Queue()
        # PID controller based on proportional band in standard PID form
        # https://en.wikipedia.org/wiki/PID_controller#Ideal_versus_standard_PID_form
        # u = Kp (e(t)+ 1/Ti INT + Td de/dt)
        # PB = Proportional Band
        # Ti = Goal of eliminating in Ti seconds (Make large to disable integration)
        # Td = Predicts error value at Td in seconds

        # Start controller
        self.Control = PID(self.Parameters['PB'], self.Parameters['Ti'], self.Parameters['Td'])
        self.Control.setTarget(self.Parameters['target'])

        self.Temps = []
        # Set mode
        self.ModeUpdated()

    def RecordTemps(self, probe_list):
        """

        @param probe_list: List of probes which provide the read() function to get the temperature.
        @type probe_list: [TemperatureProbe.TemperatureProbe,...]
        @return:
        @rtype:
        """
        now = time()
        if not self.Temps or now - self.Temps[-1][0] > self.TempInterval:
            Ts = {'time': now}
            Ts.update({probe: probe_list[probe].read() for probe in probe_list})
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

    def ParameterUpdateCallback(self, parameter, value):
        logger.info('New Parameters: %s -- %r (%r)', parameter, float(value), self.Parameters[parameter])
        if parameter == 'target':
            self.Control.setTarget(float(value))
        elif parameter in ['PB', 'Ti', 'Td']:
            self.Control.setGains(self.Parameters['PB'], self.Parameters['Ti'], self.Parameters['Td'])
        elif parameter == 'PMode':
            self.ModeUpdated()
        elif parameter == 'mode':
            self.ModeUpdated()
        elif parameter == 'program':
            self.ReadProgram()
            self.ProcessProgram()
            # TODO: Figure out reason for break after program
            # break  # Stop processing new parameters - not sure why?
        # Write parameters back after all changes have been handled.
        self.WriteParameters()

    def UpdateParameters(self):
        # Loop through each key, see what changed
        NewParameters = self.db.ReadParameters()
        NewParameters.update(self.readLCD())
        for k in NewParameters.keys():
            logger.info('New self.Parameters: %s -- %r (%r)', k, float(NewParameters[k]), self.Parameters[k])
            if k in ['target', 'PB', 'Ti', 'Td', 'PMode']:
                if float(self.Parameters[k]) != float(NewParameters[k]):
                    self.Parameters[k] = float(NewParameters[k])
            elif k == 'mode':
                if self.Parameters[k] != NewParameters[k]:
                    self.Parameters[k] = NewParameters[k]
            elif k == 'program':
                if self.Parameters[k] != NewParameters[k]:
                    self.Parameters[k] = NewParameters[k]
                    self.Parameters['LastReadProgram'] = time() - 10000
                    # TODO: Figure out reason for break after program
                    # break  # Stop processing new parameters - not sure why?

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

        Avg = array(sum) / n

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
        now = time()
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

        self.Parameters['LastWritten'] = time()
        self.qP.put(self.Parameters)

        self.db.WriteParameters(self.Parameters)

    def DoAugerControl(self):
        # Auger currently on AND TimeSinceToggle > Auger On Time
        if self.G.GetState('auger') and (time() - self.G.ToggleTime['auger']) > self.Parameters['CycleTime'] * \
                self.Parameters['u']:
            if self.Parameters['u'] < 1.0:
                self.G.SetState('auger', False)
                self.WriteParameters()
            self.CheckIgniter()

        # Auger currently off AND TimeSinceToggle > Auger Off Time
        if (not self.G.GetState('auger')) and (time() - self.G.ToggleTime['auger']) > self.Parameters[
            'CycleTime'] * (
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
        if (time() - self.G.ToggleTime['igniter']) > 1200 and self.G.GetState('igniter'):
            logger.info('Disabling igniter due to timeout')
            self.G.SetState('igniter', False)
            self.Parameters['mode'] = 'Shutdown'
            self.ModeUpdated()

    def DoControl(self):
        if (time() - self.Control.LastUpdate) > self.Parameters['CycleTime']:
            # TODO: Replace with stored sliding window average computed as they are updated.
            Avg = self.GetAverageSince(self.Control.LastUpdate)
            self.Parameters['u'] = self.Control.update(Avg[1])  # Grill probe is [0] in T, [1] in Temps
            self.Parameters['u'] = max(self.Parameters['u'], U_MIN)
            self.Parameters['u'] = min(self.Parameters['u'], U_MAX)
            logger.info('u %f', self.Parameters['u'])

            # Post control state
            D = {'time':  time() * 1000, 'u': self.Parameters['u'], 'P': self.Control.P, 'I': self.Control.I,
                 'D':     self.Control.D,
                 'PID':   self.Control.u, 'Error': self.Control.error, 'Derv': self.Control.Derv,
                 'Inter': self.Control.Inter}

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
        now = time()
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
            self.Parameters['ProgramToggle'] = time()

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
    config.fileConfig('/home/pi/PiSmoker/logging.conf')
    logger = getLogger('PiSmoker')

    # Initialize Probes
    grill_ADC = MAX31865(bus=_BUS, cs=_MAX_CS, R_ref=4000.)
    ADS_ADC = ADS1118(bus=_BUS, cs=_ADS_CS)
    meat1_channel = '01'
    firebox_channel = '23'

    grill_probe = TemperatureProbe(RTD, read_fn=grill_ADC.read(), temp_in_F=True)
    meat1_probe = TemperatureProbe(THERMOCOUPLE, read_fn=ADS_ADC.read, read_fn_kwargs={'channel': meat1_channel},
                                   read_cj_fn=ADS_ADC.read_its, temp_in_F=True)
    firebox_probe = TemperatureProbe(THERMOCOUPLE, read_fn=ADS_ADC.read, read_fn_kwargs={'channel': firebox_channel},
                                   read_cj_fn=ADS_ADC.read_its, temp_in_F=True)
    Probes = {'grill': grill_probe,
              'meat':  meat1_probe,
              'firebox': firebox_probe}

    # Start firebase
    f = open('/home/pi/PiSmoker/AuthToken.txt', 'r')
    Secret = f.read()
    f.close()
    Params = {'print': 'silent'}
    Params = {'auth': Secret, 'print': 'silent'}  # ".write": "auth !== null"
    firebase_db = Firebase_Backend(FB_URL, Secret)

    # Initialize LCD
    qP = Queue()  # Queue for Parameters
    qT = Queue()  # Queue for Temps
    qR = Queue()  # Return for Parameters
    qT.put([0, 0, 0])
    lcd = LCDDisplay(qP, qT, qR)
    lcd.setDaemon(True)
    lcd.start()

    ##############
    # Setup       #
    ##############

    # Default parameters
    Smoker = PiSmoker(firebase_db)

    # Setup variables
    # Parameters['LastReadProgram'] = time.time()
    # Parameters['LastReadWeb'] = time.time()

    ###############
    # Main Loop    #
    ###############
    sleep(5)  # Wait for clock to sync
    retval = 0
    try:
        while 1:
            # Record temperatures
            Smoker.RecordTemps(Probes)

            # Check for new parameters
            Smoker.UpdateParameters()

            # Check for new program
            Smoker.ProcessProgram()

            # Evaluate triggers
            Smoker.EvaluateTriggers()

            # Do mode
            Smoker.DoMode()

            sleep(0.05)
    except KeyboardInterrupt:
        pass
    except:
        retval = 1
    finally:
        for relay in Smoker.relays:
            # Shutdown all relays if possible.
            Smoker.G.SetState(relay_id=relay, state=False)
        return retval


if __name__ == '__main__':
    import sys

    retval = main()
    sys.exit(retval)
