import logging.config
import spidev
import time

# Start logging
logging.config.fileConfig('/home/pi/PiSmoker/logging.conf')
logger = logging.getLogger(__name__)

# Datasheet http://www.ti.com/lit/ds/symlink/ads1118.pdf

# Channel numbers AINp AINn: bits
_channel_bits = {'01': 0b000,  # default
                 '03': 0b001,
                 '13': 0b010,
                 '23': 0b011,
                 '0G': 0b100,
                 '1G': 0b101,
                 '2G': 0b110,
                 '3G': 0b111}  # @type channels: dict
_gain_bits = {6.144: 0b000,
              4.096: 0b001,
              2.048: 0b010,  # Default range
              1.024: 0b011,
              0.512: 0b100,
              0.256: 0b101}
_gains = sorted(_gain_bits.keys())
_dr_bits = {8:   0b000,
            16:  0b001,
            32:  0b010,
            64:  0b011,
            128: 0b100,  # Default
            250: 0b101,
            475: 0b110,
            860: 0b111}
_drs = sorted(_dr_bits.keys())
_ITS_GAIN = 0.03125  # Gain from Internal Temperature sensor.
_ITS_SAMPLE_TIME = 60


# noinspection PyPackageRequirements,SpellCheckingInspection
class ADS1118(object):
    V_ref = 0.  # @param R_ref: Reference Voltage
    __cs = None  # @param cs: Chip select number
    __bus = None  # @param bus: SPI bus to be used
    __spi = None  # @type spi: spidev

    __dr = 128
    __gain = 2.048
    __channel = '01'
    __mode = True  # Single Shot
    __its = False  # Read from internal temperature sensor
    __pu = False  # Internal pull up disable

    __autoscale = False

    __last_cmd = []
    __last_its = 0.
    __last_its_time = None

    def __init__(self, bus=0, cs=0, **kwargs):
        """

        @param cs: Chip Select
        @type cs: int
        @param bus: SPI Bus
        @type bus: int

        """
        self.__cs = cs
        self.__bus = bus

        if kwargs['speed']:
            self.setup_spi(speed=kwargs['speed'])
        else:
            self.setup_spi(speed=61000)

        self.config(**kwargs)

    def setup_spi(self, speed=7629):
        """Set up the SPI bus for the parameters set.

        @param speed: Max SPI speed in Hz
        @type speed: int
        @return: None
        @rtype: None
        """

        # Setup SPI
        if speed <= 17.9:
            raise TypeError("ADS1118 minimum SPI clock is 17.9Hz.")
        if speed > 4e6:
            raise TypeError("ADS1118 max SPI clock is 4MHz.")

        self.__spi = spidev.SpiDev()
        self.__spi.open(self.__bus, self.__cs)
        self.__spi.max_speed_hz = speed
        # Datasheet indicates mode must be CPOL=0, CPHA=1 (i.e. mode 1)
        self.__spi.mode = 0b01

    # noinspection PyIncorrectDocstring
    def config(self, ss=False, channel=None, max_v=None, mode=None, dr=None, its=None, pu=None, **kwargs):
        """

        @param ss: Execute singleshot measurement
        @type ss: bool
        @param channel: Channel to be read
        @type channel: str
        @param max_v: Full range voltage (from datasheet)
        @type max_v: float
        @param mode: Measurement mode (Singleshot?/!Continuous)
        @type mode: bool
        @param dr: Datarate (Samples per second)
        @type dr: int
        @param its: Internal Temperature Sensor
        @type its: bool
        @param pu: Enable Pullup Resistor on DOUT
        @type pu: bool
        @param autoscale:
        @return: None
        @rtype: None
        """
        # Config bits
        # 15    Single Shot start conversion
        # 14:12 Multiplexer configuration (channel selection)
        # 11:9  Programmable gain amplifier
        # 8     Mode (0=Continuous, 1=Single-shot)
        # 7:5   Sampling Rate (Datarate)
        # 4     Temperature sensor mode (0=ADC, 1=Temperature Sensor)
        # 3     Pull up enable (0=pullup disabled, 1=pullup enabled)
        # 2:1   Valid Data/NOP: Config data only written when NOP is 0b01
        # 0     Reserved: Always write 0b1, returns either 0b0 or 0b1.
        if channel is None:
            channel = self.__channel
        elif channel not in _channel_bits:
            raise TypeError("Channel %s not a valid channel." % channel)
        else:
            self.__channel = channel

        if max_v is None:
            max_v = self.__gain

        if max_v not in _gain_bits:
            try:
                for dev_gain in _gains:
                    if abs(max_v) > dev_gain:
                        continue
                    else:
                        max_v = dev_gain
                        self.__gain = max_v
                        break

            except TypeError:
                # We were given a bad gain, just go to max range
                max_v = _gains[-1]
                self.__gain = max_v
        else:
            self.__gain = max_v

        if dr is None:
            dr = self.__dr

        if dr not in _dr_bits:
            try:
                for dev_dr in _drs:
                    if abs(dr) > dev_dr:
                        continue
                    else:
                        dr = dev_dr
                        self.__dr = dr
                        break

            except TypeError:
                # We were given a bad dr, just go to mid rate.
                dr = _drs[len(_drs) / 2]
                self.__dr = dr
        else:
            self.__dr = dr

        if mode is None:
            mode = self.__mode
        else:
            self.__mode = mode

        if its is None:
            its = self.__its
        else:
            self.__its = its

        if pu is None:
            pu = self.__pu
        else:
            self.__pu = pu

        if 'autoscale' in kwargs:
            self.__autoscale = kwargs['autoscale']

        if ss and not mode:
            logger.warning("Requested singleshot measurement in continuous mode.", exc_info=1)
            ss = False

        MSB = (((ss & 0b1) << 7) |  # Single-shot execute
               (_channel_bits[channel] << 4) |  # Channel setting
               (_gain_bits[max_v] << 1) |  # Gain setting
               (mode & 0b1))  # Sampling Mode
        LSB = ((_dr_bits[dr] << 5) |  # Sampling rate
               ((its & 0b1) << 4) |  # Internal Temperature Sensor enable
               ((pu & 0b1) << 3) |  # Pullup resistor status
               0b011)  # Valid config + reserved bit

        if self.__last_cmd != [MSB, LSB] or ss:
            # Configuration has changed, or we want a singleshot measurement.
            self.__last_cmd = [MSB, LSB]
            self.__spi.xfer2(self.__last_cmd)
            time.sleep(1.2 / dr)  # Wait at least 1.2 * sample time to ensure data is ready

    def _raw_read(self):
        """ Read and return direct ADC value (appropriately signed).

        @return: ADC value as a python signed int
        @rtype: int
        """

        # Clock out two bytes, holding MOSI/DIN low.
        reading = self.__spi.xfer2([0x00, 0x00])
        ADC = (reading[0] << 8) + reading[1]  # Shift MSB up 8 bits, add to LSB
        if (reading[0] & (0b1 << 7)) != 0:
            # Reading is negative (two's compliment)
            ADC -= (0b1 << 8)

        return ADC

    def read(self, channel=None, its=False):
        """ Perform single-ended ADC read.

        @param channel: [Optional] Channel to read
        @type channel: [Optional]str
        @param its: Read internal temperature sensor
        @type its: bool
        @return: ADC Voltage
        @rtype: float
        """

        if its:
            # Because it takes time to switch inputs, have some sampling histeresis for the internal temperature sensor.
            now = time.time()
            if now - self.__last_its_time > _ITS_SAMPLE_TIME:
                self.__last_its_time = now
            else:
                return self.__last_its
        # Read command: cycle out 2 null bytes to get in the data.

        kwargs = {}
        if self.__mode:
            # Single shot mode, write configuration and wait before sampling.
            kwargs.update(ss=True)
        if channel:
            kwargs.update(channel=channel)
        if its:
            kwargs.update(its=True)
        self.config(**kwargs)

        ADC = self._raw_read()

        # Calculate reading from gain or its scale if self._its is set.
        if self.__its:
            scale = 0.03125
        else:
            scale = self.__gain / 65536.

        v_in = ADC * scale

        if self.__autoscale:
            if abs(ADC) < ((2 ^ 15) * .8) and (self.__gain / 2) >= _gains[0]:
                # If we have autoscale option turned on, the voltage measured is less than 80% of the next range down,
                #  and the next range down is possible, change the gain to the next possible range.
                self.__gain /= 2
            elif abs(ADC) > ((2 ^ 16) * .9) and (self.__gain * 2) <= _gains[-1]:
                # If we have autoscale option turned on, the voltage measured is greater than 90% of the current range
                #  and the next range up is possible, change the gain to the next possible range.
                self.__gain *= 2

        if self.__its:
            self.__last_its = v_in

        return v_in

    def read_its(self):
        return self.read(its=True)

    def read_channel(self):
        return self.read(its=False)

    def close(self):
        self.__spi.close()

    def __del__(self):
        self.close()
