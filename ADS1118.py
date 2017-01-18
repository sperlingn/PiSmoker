import logging.config
import spidev
import time

# Start logging
logging.config.fileConfig('/home/pi/PiSmoker/logging.conf')
logger = logging.getLogger(__name__)

# Datasheet http://www.ti.com/lit/ds/symlink/ads1118.pdf

# Channel numbers AINp AINn: bits
channel_bits = {'01': 0b000,  # default
                '03': 0b001,
                '13': 0b010,
                '23': 0b011,
                '0G': 0b100,
                '1G': 0b101,
                '2G': 0b110,
                '3G': 0b111}  # @type channels: dict
gain_bits = {6.144: 0b000,
             4.096: 0b001,
             2.048: 0b010,  # Default range
             1.024: 0b011,
             0.512: 0b100,
             0.256: 0b101}
gains = sorted(gain_bits.keys())
dr_bits = {8:   0b000,
           16:  0b001,
           32:  0b010,
           64:  0b011,
           128: 0b100,  # Default
           250: 0b101,
           475: 0b110,
           860: 0b111}
drs = sorted(dr_bits.keys())
ITS_GAIN = 0.03125  # Gain from Internal Temperature sensor.


# noinspection PyPackageRequirements,SpellCheckingInspection
class ADS1118:
    V_ref = 0.  # @param R_ref: Reference Voltage
    _cs = None  # @param cs: Chip select number
    _bus = None  # @param bus: SPI bus to be used
    _spi = None  # @type spi: spidev

    _dr = 128
    _gain = 2.048
    _channel = '01'
    _mode = True  # Single Shot
    _its = False  # Read from internal temperature sensor
    _pu = False  # Internal pull up disable

    _autoscale = False

    _last_cmd = []

    def __init__(self, bus=0, cs=0, **kwargs):
        """

        @param cs: Chip Select
        @type cs: int
        @param bus: SPI Bus
        @type bus: int

        """
        self._cs = cs
        self._bus = bus

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

        self._spi = spidev.SpiDev()
        self._spi.open(self._bus, self._cs)
        self._spi.max_speed_hz = speed
        # Datasheet indicates mode must be CPOL=0, CPHA=1 (i.e. mode 1)
        self._spi.mode = 0b01

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
            channel = self._channel
        elif channel not in channel_bits:
            raise TypeError("Channel %s not a valid channel." % channel)
        else:
            self._channel = channel

        if max_v is None:
            max_v = self._gain

        if max_v not in gain_bits:
            try:
                for dev_gain in gains:
                    if abs(max_v) > dev_gain:
                        continue
                    else:
                        max_v = dev_gain
                        self._gain = max_v
                        break

            except TypeError:
                # We were given a bad gain, just go to max range
                max_v = gains[-1]
                self._gain = max_v
        else:
            self._gain = max_v

        if dr is None:
            dr = self._dr

        if dr not in dr_bits:
            try:
                for dev_dr in drs:
                    if abs(dr) > dev_dr:
                        continue
                    else:
                        dr = dev_dr
                        self._dr = dr
                        break

            except TypeError:
                # We were given a bad dr, just go to mid rate.
                dr = drs[len(drs) / 2]
                self._dr = dr
        else:
            self._dr = dr

        if mode is None:
            mode = self._mode
        else:
            self._mode = mode

        if its is None:
            its = self._its
        else:
            self._its = its

        if pu is None:
            pu = self._pu
        else:
            self._pu = pu

        if 'autoscale' in kwargs:
            self._autoscale = kwargs['autoscale']

        if ss and not mode:
            logger.warning("Requested singleshot measurement in continuous mode.", exc_info=1)
            ss = False

        MSB = (((ss & 0b1) << 7) |  # Single-shot execute
               (channel_bits[channel] << 4) |  # Channel setting
               (gain_bits[max_v] << 1) |  # Gain setting
               (mode & 0b1))  # Sampling Mode
        LSB = ((dr_bits[dr] << 5) |  # Sampling rate
               ((its & 0b1) << 4) |  # Internal Temperature Sensor enable
               ((pu & 0b1) << 3) |  # Pullup resistor status
               0b011)  # Valid config + reserved bit

        if self._last_cmd != [MSB, LSB] or ss:
            # Configuration has changed, or we want a singleshot measurement.
            self._last_cmd = [MSB, LSB]
            self._spi.xfer2(self._last_cmd)
            time.sleep(1.2 / dr)  # Wait at least 1.2 * sample time to ensure data is ready

    def _raw_read(self):
        """ Read and return direct ADC value (appropriately signed).

        @return: ADC value as a python signed int
        @rtype: int
        """

        # Clock out two bytes, holding MOSI/DIN low.
        reading = self._spi.xfer2([0x00, 0x00])
        ADC = (reading[0] << 8) + reading[1]  # Shift MSB up 8 bits, add to LSB
        if (reading[0] & (0b1 << 7)) != 0:
            # Reading is negative (two's compliment)
            ADC -= (0b1 << 8)

        return ADC

    def read(self, channel=None, its=False):
        """ Perform single-ended ADC read.

        @param channel: [Optional] Channel to read
        @type channel: str
        @param its: Read internal temperature sensor
        @type its: bool
        @return: ADC Voltage
        @rtype: float
        """

        # Read command: cycle out 2 null bytes to get in the data.

        kwargs = {}
        if self._mode:
            # Single shot mode, write configuration and wait before sampling.
            kwargs.update(ss=True)
        if channel:
            kwargs.update(channel=channel)
        if its:
            kwargs.update(its=True)
        self.config(**kwargs)

        ADC = self._raw_read()

        # Calculate reading from gain or its scale if self._its is set.
        if self._its:
            scale = 0.03125
        else:
            scale = self._gain / 65536.

        v_in = ADC * scale

        if self._autoscale:
            if abs(ADC) < ((2 ^ 15) * .8) and (self._gain / 2) >= gains[0]:
                # If we have autoscale option turned on, the voltage measured is less than 80% of the next range down,
                #  and the next range down is possible, change the gain to the next possible range.
                self._gain /= 2
            elif abs(ADC) > ((2 ^ 16) * .9) and (self._gain * 2) <= gains[-1]:
                # If we have autoscale option turned on, the voltage measured is greater than 90% of the current range
                #  and the next range up is possible, change the gain to the next possible range.
                self._gain *= 2

        return v_in

    def read_its(self):
        return self.read(its=True)

    def read_channel(self):
        return self.read(its=False)

    def close(self):
        self._spi.close()

    def __del__(self):
        self.close()
