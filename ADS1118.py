import spidev
import time, math, logging, logging.config

#Start logging
logging.config.fileConfig('/home/pi/PiSmoker/logging.conf')
logger = logging.getLogger(__name__)

#Datasheet http://www.ti.com/lit/ds/symlink/ads1118.pdf

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
dr_bits = {  8: 0b000,
            16: 0b001,
            32: 0b010,
            64: 0b011,
           128: 0b100, # Default
           250: 0b101,
           475: 0b110,
           860: 0b111}


class ADS1118:

    V_ref = 0.  # @param R_ref: Reference Voltage
    _cs = None  # @param cs: Chip select number
    _bus = None  # @param bus: SPI bus to be used
    _spi = None  # @type spi: spidev

    _dr = 128
    _gain = 2.048
    _channel = '01'
    _mode = 1 # Single Shot
    _its = 0 # Read from internal temperature sensor
    _pu = 0 # Internal pullup disable

    def __init__(self,bus=0,cs=0):
        """

        @param cs: Chip Select
        @type cs: int

        """
        self._cs = cs
        self._bus = bus

        self.setupSPI(speed=61000)

        self.config()

    def setupSPI(self,speed=7629):
        """Set up the SPI bus for the parameters set.

        @param speed: Max SPI speed in Hz
        @type speed: int
        @return: None
        @rtype: None
        """

        #Setup SPI
        if speed <= 17.9:
            raise TypeError("ADS1118 minimum SPI clock is 17.9Hz.")
        if speed > 4e6:
            raise TypeError("ADS1118 max SPI clock is 4MHz.")

        self._spi = spidev.SpiDev()
        self._spi.open(self._bus, self._cs)
        self._spi.max_speed_hz = speed
        # Datasheet indicates mode must be CPOL=0, CPHA=1 (i.e. mode 1)
        self._spi.mode = 0b01

    def config(self,ss=0,channel=None,gain=None,mode=None,dr=None,its=None,pu=None):
        #Config bits
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

        if gain is None:
            gain = self._gain
        elif gain not in gain_bits:
            raise TypeError("Programmable Gain Range %d not a valid gain." % gain)
        else:
            self._gain = gain

        if dr is None:
            dr = self._dr
        elif dr not in dr_bits:
            raise TypeError("Datarate %i not a valid sampling rate." % dr)
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

        MSB = ((ss & 0b1 << 7) |
               (channel_bits[channel] << 4) |
               (gain_bits[gain] << 1) |
               (mode & 0b1))
        LSB = ((dr_bits[dr] << 5) |
               ((its & 0b1) << 4) |
               ((pu & 0b1) << 3) |
               (0b01 << 1) |
               0b1)

        self._spi.xfer2([MSB, LSB])
        time.sleep(1.2 / dr)  # Wait at least 1.2 * sample time to ensure data is ready

    def read(self):
        """ Perform single-ended ADC read.

        @return: ADC Voltage
        @rtype: float
        """

        # Read command: cycle out 2 null bytes to get in the data.

        if self._mode & 0b1:
            # Single shot mode, write configuration and wait before sampling.
            self.config(ss=1)

        reading = self._spi.xfer2([0x00,0x00])

        ADC = (reading[0] << 8) + reading[1]  # Shift MSB up 8 bits, add to LSB
        if (reading[0] & (0b1 << 7)) != 0:
            # Reading is negative (two's compliment)
            ADC -= (0b1 << 8)

        v_in = float(ADC * (self._gain / 65536.))
        return v_in

    def parse_reading(self, reading):
        ADC = (reading[0] << 8) + reading[1]  # Shift MSB up 8 bits, add to LSB
        if (reading[0] & (0b1 << 7)) != 0:
            # Reading is negative (two's compliment)
            ADC -= (0b1 << 8)

        if self._its:
            scale = 0.03125
        else:
            scale = self._gain / 65536.

        return ADC * scale  # Per datasheet ITS = 0.03125 degC/count

    def read_its(self):
        if not self._its:
            self.config(its=1)

        Tc = self.read()

        return Tc

    def read_channel(self):
        if self._its:
            self.config(its=0)

        v_in = self.read()

        return v_in

    def close(self):
        self._spi.close()

    def __del__(self):
        self.close()