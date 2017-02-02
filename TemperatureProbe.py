from math import sqrt, exp
from functools import partial

# Constants for temperature probe type
THERMOCOUPLE = 'TC'
THERMISTOR = 'TR'
RTD = 'RTD'
VALID_PROBE_TYPES = [RTD, THERMISTOR, THERMOCOUPLE]

# Parameters for RTD correction from IEC 751 (PT100)
# Solved for alpha = 0.00385055
# RTD Constants
_A_PT = 3.90830e-3
_B_PT = -5.775e-7
_R_0_PT100 = 100.
_R_0_PT1000 = 1000.


class Thermocouple(object):
    c2e_ranges = {
        'B': [630.615, 1820.000],
        'E': [0.000, 1000.000],
        'J': [760.000, 1200.000],
        'K': [0.000, 1372.000],
        'N': [0.000, 1300.],
        'R': [1064.180, 1664.500, 1768.1],
        'S': [1064.180, 1664.500, 1768.1],
        'T': [0.000, 400.000]
    }
    c2e_coefs = {
        'B': [[0.000000000000E+00, -0.246508183460E-03, 0.590404211710E-05, -0.132579316360E-08, 0.156682919010E-11,
               -0.169445292400E-14, 0.629903470940E-18],
              [-0.389381686210E+01, 0.285717474700E-01, -0.848851047850E-04, 0.157852801640E-06, -0.168353448640E-09,
               0.111097940130E-12, -0.445154310330E-16, 0.989756408210E-20, -0.937913302890E-24]],
        'E': [[0.000000000000E+00, 0.586655087080E-01, 0.454109771240E-04, -0.779980486860E-06, -0.258001608430E-07,
               -0.594525830570E-09, -0.932140586670E-11, -0.102876055340E-12, -0.803701236210E-15, -0.439794973910E-17,
               -0.164147763550E-19, -0.396736195160E-22, -0.558273287210E-25, -0.346578420130E-28],
              [0.000000000000E+00, 0.586655087100E-01, 0.450322755820E-04, 0.289084072120E-07, -0.330568966520E-09,
               0.650244032700E-12, -0.191974955040E-15, -0.125366004970E-17, 0.214892175690E-20, -0.143880417820E-23,
               0.359608994810E-27]],
        'J': [[0.000000000000E+00, 0.503811878150E-01, 0.304758369300E-04, -0.856810657200E-07, 0.132281952950E-09,
               -0.170529583370E-12, 0.209480906970E-15, -0.125383953360E-18, 0.156317256970E-22],
              [0.296456256810E+03, -0.149761277860E+01, 0.317871039240E-02, -0.318476867010E-05, 0.157208190040E-08,
               -0.306913690560E-12]],
        'K': [[0.000000000000E+00, 0.394501280250E-01, 0.236223735980E-04, -0.328589067840E-06, -0.499048287770E-08,
               0.675090591730E-10, -0.574103274280E-12, -0.310888728940E-14, -0.104516093650E-16, -0.198892668780E-19,
               -0.163226974860E-22],
              [-0.176004136860E-01, 0.389212049750E-01, 0.185587700320E-04, -0.994575928740E-07, 0.318409457190E-09,
               -0.560728448890E-12, 0.560750590590E-15, -0.320207200030E-18, 0.971511471520E-22, -0.121047212750E-25]],
        'N': [[0.000000000000E+00, 0.261591059620E-01, 0.109574842280E-04, -0.938411115540E-07, -0.464120397590E-10,
               -0.263033577160E-11, -0.226534380030E-13, -0.760893007910E-16, -0.934196678350E-19],
              [0.000000000000E+00, 0.259293946010E-01, 0.157101418800E-04, 0.438256272370E-07, -0.252611697940E-09,
               0.643118193390E-12, -0.100634715190E-14, 0.997453389920E-18, -0.608632456070E-21, 0.208492293390E-24,
               -0.306821961510E-28]],
        'R': [[0.000000000000E+00, 0.528961729765E-02, 0.139166589782E-04, -0.238855693017E-07, 0.356916001063E-10,
               -0.462347666298E-13, 0.500777441034E-16, -0.373105886191E-19, 0.157716482367E-22, -0.281038625251E-26],
              [0.295157925316E+01, -0.252061251332E-02, 0.159564501865E-04, -0.764085947576E-08, 0.205305291024E-11,
               -0.293359668173E-15],
              [0.152232118209E+03, -0.268819888545E+00, 0.171280280471E-03, -0.345895706453E-07, -0.934633971046E-14]],
        'S': [[0.000000000000E+00, 0.540313308631E-02, 0.125934289740E-04, -0.232477968689E-07, 0.322028823036E-10,
               -0.331465196389E-13, 0.255744251786E-16, -0.125068871393E-19, 0.271443176145E-23],
              [0.132900444085E+01, 0.334509311344E-02, 0.654805192818E-05, -0.164856259209E-08, 0.129989605174E-13],
              [0.146628232636E+03, -0.258430516752E+00, 0.163693574641E-03, -0.330439046987E-07, -0.943223690612E-14]],
        'T': [[0.000000000000E+00, 0.387481063640E-01, 0.441944343470E-04, 0.118443231050E-06, 0.200329735540E-07,
               0.901380195590E-09, 0.226511565930E-10, 0.360711542050E-12, 0.384939398830E-14, 0.282135219250E-16,
               0.142515947790E-18, 0.487686622860E-21, 0.107955392700E-23, 0.139450270620E-26, 0.797951539270E-30],
              [0.000000000000E+00, 0.387481063640E-01, 0.332922278800E-04, 0.206182434040E-06, -0.218822568460E-08,
               0.109968809280E-10, -0.308157587720E-13, 0.454791352900E-16, -0.275129016730E-19]],
    }
    e2c_ranges = {
        'B': [2.431, 13.820],
        'E': [0.000, 76.373],
        'J': [0.000, 42.919, 69.553],
        'K': [0.000, 20.644, 54.886],
        'N': [0.000, 20.613, 47.513],
        'R': [1.923, 13.228, 19.739, 21.103],
        'S': [1.874, 11.950, 17.536, 18.693],
        'T': [0.000, 20.872]
    }
    e2c_coefs = {
        'B': [
            [9.8423321E+01, 6.9971500E+02, -8.4765304E+02, 1.0052644E+03, -8.3345952E+02, 4.5508542E+02, -1.5523037E+02,
             2.9886750E+01, -2.4742860E+00],
            [2.1315071E+02, 2.8510504E+02, -5.2742887E+01, 9.9160804E+00, -1.2965303E+00, 1.1195870E-01, -6.0625199E-03,
             1.8661696E-04, -2.4878585E-06]],
        'E': [[0.0000000E+00, 1.6977288E+01, -4.3514970E-01, -1.5859697E-01, -9.2502871E-02, -2.6084314E-02,
               -4.1360199E-03, -3.4034030E-04, -1.1564890E-05, 0.0000000E+00],
              [0.0000000E+00, 1.7057035E+01, -2.3301759E-01, 6.5435585E-03, -7.3562749E-05, -1.7896001E-06,
               8.4036165E-08, -1.3735879E-09, 1.0629823E-11, -3.2447087E-14]],
        'J': [[0.0000000E+00, 1.9528268E+01, -1.2286185E+00, -1.0752178E+00, -5.9086933E-01, -1.7256713E-01,
               -2.8131513E-02, -2.3963370E-03, -8.3823321E-05],
              [0.000000E+00, 1.978425E+01, -2.001204E-01, 1.036969E-02, -2.549687E-04, 3.585153E-06, -5.344285E-08,
               5.099890E-10, 0.000000E+00],
              [-3.11358187E+03, 3.00543684E+02, -9.94773230E+00, 1.70276630E-01, -1.43033468E-03, 4.73886084E-06,
               0.00000000E+00, 0.00000000E+00, 0.00000000E+00]],
        'K': [[0.0000000E+00, 2.5173462E+01, -1.1662878E+00, -1.0833638E+00, -8.9773540E-01, -3.7342377E-01,
               -8.6632643E-02, -1.0450598E-02, -5.1920577E-04, 0.0000000E+00],
              [0.000000E+00, 2.508355E+01, 7.860106E-02, -2.503131E-01, 8.315270E-02, -1.228034E-02, 9.804036E-04,
               -4.413030E-05, 1.057734E-06, -1.052755E-08],
              [-1.318058E+02, 4.830222E+01, -1.646031E+00, 5.464731E-02, -9.650715E-04, 8.802193E-06, -3.110810E-08,
               0.000000E+00, 0.000000E+00, 0.000000E+00]],
        'N': [[0.0000000E+00, 3.8436847E+01, 1.1010485E+00, 5.2229312E+00, 7.2060525E+00, 5.8488586E+00, 2.7754916E+00,
               7.7075166E-01, 1.1582665E-01, 7.3138868E-03],
              [0.00000E+00, 3.86896E+01, -1.08267E+00, 4.70205E-02, -2.12169E-06, -1.17272E-04, 5.39280E-06,
               -7.98156E-08, 0.00000E+00, 0.00000E+00],
              [1.972485E+01, 3.300943E+01, -3.915159E-01, 9.855391E-03, -1.274371E-04, 7.767022E-07, 0.000000E+00,
               0.000000E+00, 0.000000E+00, 0.000000E+00]],
        'R': [
            [0.0000000E+00, 1.8891380E+02, -9.3835290E+01, 1.3068619E+02, -2.2703580E+02, 3.5145659E+02, -3.8953900E+02,
             2.8239471E+02, -1.2607281E+02, 3.1353611E+01, -3.3187769E+00],
            [1.334584505E+01, 1.472644573E+02, -1.844024844E+01, 4.031129726E+00, -6.249428360E-01, 6.468412046E-02,
             -4.458750426E-03, 1.994710149E-04, -5.313401790E-06, 6.481976217E-08, 0.000000000E+00],
            [-8.199599416E+01, 1.553962042E+02, -8.342197663E+00, 4.279433549E-01, -1.191577910E-02, 1.492290091E-04,
             0.000000000E+00, 0.000000000E+00, 0.000000000E+00, 0.000000000E+00, 0.000000000E+00],
            [3.406177836E+04, -7.023729171E+03, 5.582903813E+02, -1.952394635E+01, 2.560740231E-01, 0.000000000E+00,
             0.000000000E+00, 0.000000000E+00, 0.000000000E+00, 0.000000000E+00, 0.000000000E+00]],
        'S': [[0.00000000E+00, 1.84949460E+02, -8.00504062E+01, 1.02237430E+02, -1.52248592E+02, 1.88821343E+02,
               -1.59085941E+02, 8.23027880E+01, -2.34181944E+01, 2.79786260E+00],
              [1.291507177E+01, 1.466298863E+02, -1.534713402E+01, 3.145945973E+00, -4.163257839E-01, 3.187963771E-02,
               -1.291637500E-03, 2.183475087E-05, -1.447379511E-07, 8.211272125E-09],
              [-8.087801117E+01, 1.621573104E+02, -8.536869453E+00, 4.719686976E-01, -1.441693666E-02, 2.081618890E-04,
               0.000000000E+00, 0.000000000E+00, 0.000000000E+00, 0.000000000E+00],
              [5.333875126E+04, -1.235892298E+04, 1.092657613E+03, -4.265693686E+01, 6.247205420E-01, 0.000000000E+00,
               0.000000000E+00, 0.000000000E+00, 0.000000000E+00, 0.000000000E+00]],
        'T': [[0.0000000E+00, 2.5949192E+01, -2.1316967E-01, 7.9018692E-01, 4.2527777E-01, 1.3304473E-01, 2.0241446E-02,
               1.2668171E-03],
              [0.000000E+00, 2.592800E+01, -7.602961E-01, 4.637791E-02, -2.165394E-03, 6.048144E-05, -7.293422E-07,
               0.000000E+00]]
    }

    def __init__(self, tc_type='K'):
        if tc_type not in self.c2e_ranges.keys():
            raise TypeError("Thermocouple type '%s' invalid." % tc_type)

        self.type = tc_type

    def c2e(self, Tc):
        """Converts temperature in C to equivalent thermocouple voltage in Volts using NIST ITS-90 functions.

        @param Tc: Temperature (C)
        @type Tc: float
        @return: Voltage (Volts)
        @rtype: float
        """
        E = 0
        # Gets index for coefs for which the NIST function is valid
        t_r = 0
        while t_r < len(self.c2e_ranges[self.type]) - 1 and self.c2e_ranges[self.type][t_r] <= Tc:
            t_r += 1

        # Recursive formulation of polynomial coefficient solution.
        for a in range(len(self.c2e_coefs[self.type][t_r]) - 1, -1, -1):
            E = self.c2e_coefs[self.type][t_r][a] + Tc * E

        if self.type is 'K':
            # Special K-type corrections.
            E += 0.1185976 * exp(-0.1183432e-3 * (Tc - 0.1269686e3) ** 2)

        return E / 1000.  # Units of NIST ITS-90 are mV

    def e2c(self, E):
        """Convert reading in V to reading in C for Thermocouple type using NIST ITS-90 functions.

        @param E: Reading (V)
        @type E: float
        @return: Temperature (C)
        @rtype: float
        """
        Tc = 0.

        E_mV = E * 1000.  # NIST ITS-90 data all computed in mV

        # Gets index for coefs for which the NIST function is valid
        e_r = 0
        while e_r < len(self.e2c_ranges[self.type]) - 1 and self.e2c_ranges[self.type][e_r] <= E_mV:
            e_r += 1

        # Recursive formulation of polynomial coefficient solution.
        for a in range(len(self.e2c_coefs[self.type][e_r]) - 1, -1, -1):
            Tc = self.e2c_coefs[self.type][e_r][a] + E_mV * Tc

        return Tc


# noinspection SpellCheckingInspection
class TemperatureProbe(object):
    # TODO: Sliding window temperature log.
    # As a new temperature is added, remove the last one in the window. FIFO queue?
    temp_in_F = False
    type = None

    tc_type = 'K'
    tc_probe = None  # @type tc_probe: Thermocouple

    # User functions to read various required parameters.
    #  Thermistors require thermis_fn, thermocouples require read_cj_fn, all require read_fn
    read_fn = None  # Function used to read voltage from ADC
    read_cj_fn = None  # Function used to read Cold Junction temperature for thermocouple
    thermis_fn = None  # Arbitrary voltage to temperature function for thermistors

    R_0_RTD = _R_0_PT1000

    def __init__(self, probe_type, read_fn, read_fn_args=None, read_cj_fn=None, read_cj_fn_args=None, subtype=None,
                 thermis_fn=None, thermis_fn_args=None, temp_in_F=None, **kwargs):
        """

        @param probe_type: Probe type, recognizes: [RTD, THERMISTOR, THERMOCOUPLE] (['RTD', 'TR', 'TC'])
        @type probe_type:  str
        @param read_fn:  Function which returns the ADC voltage. Signature read_fn(*read_fn_args,**read_fn_kwargs)
        @type read_fn: callable
        @param read_fn_args: Positional parameters for read_fn
        @type read_fn_args: tuple
        @param read_cj_fn: Function to obtain the cold junction temperature. Signature read_cj_fn(*read_cj_fn_args,...)
        @type read_cj_fn: callable
        @param read_cj_fn_args: Positional parameters for read_cj_fn
        @type read_cj_fn_args: tuple
        @param subtype: Sensor subtype: e.g. 'K' for Thermocouple, 'PT100' for RTD, etc. (default: 'K', 'PT100', None)
        @type subtype: str
        @param thermis_fn: Function for thermistor voltage to temperature. Signature thermis_fn(V,*thermis_fn_args,...)
        @type thermis_fn:  callable
        @param thermis_fn_args:  Positional parameters for pos>1,
        @type thermis_fn_args: tuple
        @param *_fn_kwargs: Keyword arguments set for any of the callable functions, will be passed directly.
        @type *_fn_kwargs: dict
        """

        if probe_type not in VALID_PROBE_TYPES:
            raise TypeError("Invalid probe type: %s" % probe_type)

        if probe_type is THERMOCOUPLE:
            if read_cj_fn is None or not callable(read_cj_fn):
                raise TypeError("Probe type Thermocouple requires a callable read_cj_fn")

            self.read_cj_fn = read_cj_fn
            if 'read_cj_fn_kwargs' in kwargs:
                self.read_cj_fn = partial(self.read_cj_fn, **kwargs['read_cj_fn_kwargs'])
            if read_cj_fn_args is not None:
                try:
                    self.read_cj_fn = partial(self.read_cj_fn, *read_cj_fn_args)
                except TypeError:
                    self.read_cj_fn = partial(self.read_cj_fn, read_cj_fn_args)
            if subtype is not None:
                self.tc_type = subtype
            self.tc_probe = Thermocouple(self.tc_type)
        elif probe_type is THERMISTOR:
            if thermis_fn is None or not callable(thermis_fn):
                raise TypeError("Probe type Thermistor requires a callable thermis_fn")

            self.thermis_fn = thermis_fn
            if 'thermis_fn_kwargs' in kwargs:
                self.thermis_fn = partial(self.thermis_fn, **kwargs['thermis_fn_kwargs'])
            if thermis_fn_args is not None:
                try:
                    self.thermis_fn = partial(self.thermis_fn, *thermis_fn_args)
                except TypeError:
                    self.thermis_fn = partial(self.thermis_fn, thermis_fn_args)
        elif probe_type is RTD and subtype is not None:
            if subtype == 'PT100':
                self.R_0_RTD = _R_0_PT100
            elif subtype == 'PT1000':
                self.R_0_RTD = _R_0_PT1000
            else:
                self.R_0_RTD = float(subtype)

        if not callable(read_fn):
            assert callable(read_fn)
            raise TypeError("read_fn must be a callable object")
        else:
            self.read_fn = read_fn
            if 'read_fn_kwargs' in kwargs:
                self.read_fn = partial(self.read_fn, **kwargs['read_fn_kwargs'])
            if read_fn_args is not None:
                try:
                    self.read_fn = partial(self.read_fn, *read_fn_args)
                except TypeError:
                    self.read_fn = partial(self.read_fn, read_fn_args)

        self.type = probe_type

        if temp_in_F is not None:
            self.temp_in_F = temp_in_F

    def _read_RTD(self):
        return self.rtd_conversion(self.read_fn())

    def _read_THERMOCOUPLE(self):

        # Measure cold junction temperature, and convert to voltage for this thermocouple.
        cjv = self.tc_probe.c2e(self.read_cj_fn())

        # Temperature for probe calculated from CJV + Voltage.
        return self.tc_probe.e2c(self.read_fn() + cjv)

    def _read_THERMISTOR(self):
        raise NotImplementedError("Thermistor reading not implemented in this class.")
        pass

    def rtd_conversion(self, R_T):
        # Use NIST RTD Linearization function.
        Tc = (-_A_PT + sqrt(_A_PT * _A_PT - 4 * _B_PT * (1 - R_T / self.R_0_RTD))) / (2 * _B_PT)
        return Tc

    def read(self, temp_in_F=None):
        """Read voltage using read_fn and convert to a temperature in default unit

        @param temp_in_F: Return temperature in degrees Fahrenheit? (False for deg. Celsius). Overrides default.
        @type temp_in_F: bool
        @return: Temperature read by probe.
        @rtype: float
        """
        if self.type == RTD:
            Tc = self._read_RTD()
        elif self.type == THERMOCOUPLE:
            Tc = self._read_THERMOCOUPLE()
        elif self.type == THERMISTOR:
            Tc = self._read_THERMISTOR()
        else:
            raise TypeError("Unknown probe type %s" % self.type)

        if temp_in_F is None:
            temp_in_F = self.temp_in_F

        if temp_in_F:
            T = Tc * 9 / 5 + 32
        else:
            T = Tc

        return T
