from firebase import FirebaseAuthentication, FirebaseApplication
from time import time
import logging.config
from PiSmoker_Backend import PiSmoker_Backend

logging.config.fileConfig('/home/pi/PiSmoker/logging.conf')
logger = logging.getLogger(__name__)


# noinspection PyBroadException
class Firebase_Backend(PiSmoker_Backend):
    firebase_inst = None
    """@type self.firebase_inst: firebase"""
    fb_params = {'print': 'silent'}
    _polling_interval = 3  # Frequency to poll web for new parameters
    _read_program_interval = 60  # Frequency to poll web for new program

    _last_write_parameters = time()
    _last_read_parameters = time()
    _last_write_program = time()
    _last_read_program = time()
    _last_write_control = time()
    _last_read_control = time()
    _do_async = True
    _init_args = None
    _init_kwargs = None

    def __init__(self, app_url, auth_secret, async=True, *args, **kwargs):
        auth = FirebaseAuthentication(secret=auth_secret, email='pismoker@shimavak.net')
        self.firebase_inst = FirebaseApplication(app_url, authentication=auth)
        self._do_async = async
        self._init_args = args
        self._init_kwargs = kwargs

    def _get(self, url):
        return
        return self.firebase_inst.get(url=url, name=None, connection=None, params=self.fb_params)

    def _post(self, url, data):
        return
        return self.firebase_inst.post(url=url, data=data, connection=None, params=self.fb_params)

    def _post_async(self, url, data):
        return
        return self.firebase_inst.post_async(url, data, params=self.fb_params, callback=self.PostCallback)

    def _patch(self, url, data):
        return
        return self.firebase_inst.patch(url=url, data=data, connection=None, params=self.fb_params)

    def _patch_async(self, url, data):
        return
        return self.firebase_inst.patch_async(url=url, data=data, callback=self.PostCallback, params=self.fb_params)

    def _delete(self, url, name):
        return
        return self.firebase_inst.delete(url=url, name=name, connection=None, params=self.fb_params)

    def _put(self, url, name, data):
        return
        return self.firebase_inst.put(url=url, name=name, data=data, connection=None, params=self.fb_params)

    def PostTemps(self, target_temp, Ts):
        T = super(Firebase_Backend, self).PostTemps(target_temp, Ts)
        try:
            return self._post_async('/Temps', T)
        except:
            logger.info('Error writing Temps to Firebase')
            return -1

    def PostCallback(self, data=None):
        pass

    def ResetFirebase(self, Parameters):
        try:
            self._put('/', 'Parameters', Parameters)
            self._delete('/', 'Temps')
            self._delete('/', 'Controls')
            self._delete('/', 'Program')
        except:
            logger.info('Error initializing Firebase')

        # Post control state
        D = {'time': time() * 1000, 'u': 0, 'P': 0, 'I': 0, 'D': 0, 'PID': 0, 'Error': 0, 'Derv': 0, 'Inter': 0}

        try:
            self._post_async('/Controls', D)
        except:
            logger.info('Error writing Controls to Firebase')
            return -1

    def _WriteParameters_async(self, Parameters):
        """Write parameters to file"""
        try:
            return self._patch_async('/Parameters', Parameters)
        except:
            logger.info('Error writing parameters to Firebase')
            return -1

    def _WriteParameters_sync(self, Parameters):
        """Write parameters to file"""

        try:
            return self._patch('/Parameters', Parameters)
        except:
            logger.info('Error writing parameters to Firebase')
            return -1

    def WriteParameters(self, Parameters):
        if self._do_async:
            self._WriteParameters_async(Parameters)
        else:
            self._WriteParameters_sync(Parameters)

    def ReadParameters(self):
        """Read parameters file written by web server and LCD"""
        # Read from queue
        now = time()

        # Read from web server
        if now > self._last_read_parameters + self._polling_interval:
            self._last_read_parameters = now
            try:
                return self._get('/Parameters')
                # logger.info('New parameters from firebase: %s',NewParameters)
                # (Parameters, Program) = UpdateParameters(NewParameters, Parameters, Temps, Program)
            except Exception as e:
                logger.info('Error reading parameters from Firebase (%s)' % e.message)
                return {}

    def WriteControl(self, D):
        """Write Control settings to backend"""
        try:
            return self._post_async('/Controls', D)
        except:
            logger.info('Error writing Controls to Firebase')
            return -1

    def WriteProgram(self, Program):
        try:
            self._delete('/', 'Program')
            for P in Program:
                self._post('/Program', P)
        except:
            logger.info('Error writing Program to Firebase')

    def ReadProgram(self, run_program):
        """

        @param run_program:
        @type run_program: bool
        @return:
        @rtype: []
        """
        now = time()
        if now - self._last_read_program > self._read_program_interval and run_program:
            try:
                raw = self._get('/Program')

                if raw is not None:
                    return [k[1] for k in sorted(raw.items())]
                    # for k in sorted(raw.items()):
                    #    NewProgram.append(k[1])
            except:
                logger.info('Error reading Program from Firebase')
            self._last_read_program = now
