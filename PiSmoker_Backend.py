class PiSmoker_Backend(object):
    """
    Interface class for all backends.  They must all support these bare minimum Functions and Signatures

    * Private variables:
    @param _polling_interval: Frequency to poll for new parameters in seconds
    @type _polling_interval: float
    @param _last_write: time.time() that variables were last written out.
    @type _last_write: float
    @param _last_read: time.time() that variables were last read in.
    @type _last_read: float
    """
    _polling_interval = None
    _last_write_parameters = None
    _last_read_parameters = None
    _last_write_program = None
    _last_read_program = None
    _last_write_control = None
    _last_read_control = None
    _read_program_interval = 60  # Freqnency to poll web for new program

    def __init__(self, *args, **kwargs):
        raise NotImplementedError("Template class, must be implemented.")

    def PostTemps(self, target_temp, Ts):
        """Expected to implement storing the temperatures in the backend.
        PiSmoker_Backend implementation

        @param target_temp: Target Temperature
        @type target_temp: float
        @param Ts: List of time, temperatures...
        @type Ts: [float, ...]
        @return: Dictionary to store
        @rtype: dict
        """
        T = {'time': Ts[0] * 1000, 'TT': target_temp}
        T.update({'T%i'%i: t for (i, t) in enumerate(Ts[1:], 1)})
        return T

    def WriteParameters(self, Parameters):
        raise NotImplementedError("Template class, must be implemented.")

    def ReadParameters(self):
        """Read parameters file written by web server and LCD

        @return: Parameters dictionary
        @rtype: dict
        """
        raise NotImplementedError("Template class, must be implemented.")

    def WriteControl(self, D):
        """Write Control settings to backend"""
        raise NotImplementedError("Template class, must be implemented.")

    def WriteProgram(self, Program):
        """Write Control settings to backend"""
        raise NotImplementedError("Template class, must be implemented.")

    def ReadProgram(self, run_program):
        raise NotImplementedError("Template class, must be implemented.")
