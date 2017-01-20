import logging.config
import spidev

# Start logging
logging.config.fileConfig('/home/pi/PiSmoker/logging.conf')
logger = logging.getLogger(__name__)


# Datasheet https://datasheets.maximintegrated.com/en/ds/MCP320X.pdf


class MCP320X(object):
    V_ref = 0.  # @param R_ref: Reference Voltage
    __cs = None  # @param cs: Chip select number
    __bus = None  # @param bus: SPI bus to be used
    __spi = None  # @type spi: spidev
    __channels = None  # @type channels: dict

    def __init__(self, bus=0, cs=0, spi_mode=0b11):
        """

        @param cs: Chip Select
        @type cs: int

        """
        self.__cs = cs
        self.__bus = bus

        self.setupSPI(mode=spi_mode, speed=61000)

    def setupSPI(self, mode=0b11, speed=7629):
        """Set up the SPI bus for the parameters set.

        @param mode: SPI Mode
        @type mode: Byte (0-3)
        @param speed: Max SPI speed in Hz
        @type speed: int
        @return: None
        @rtype: None
        """

        # Setup SPI
        if not mode & 0b11 == 0b11 or mode & 0b11 == 0b00:
            raise TypeError("MCP320X only supports SPI modes 0 and 3.")
        if speed <= 10e3:
            raise TypeError("MCP320X minimum recommended SPI clock is 10kHz.")
        if speed > 5e6:
            raise TypeError("MCP320X max SPI clock is 5MHz.")

        self.__spi = spidev.SpiDev()
        self.__spi.open(self.__bus, self.__cs)
        self.__spi.max_speed_hz = speed
        self.__spi.mode = mode

    def read(self, channel=0):
        """ Perform single-ended ADC read.

        @param channel: Channel to read (0-7)
        @type channel: int
        @return: ADC Voltage
        @rtype: float
        """

        # Read command per datasheet:
        # Requires 3 bytes, MSB first.
        # Byte 1: bit 1-5=0
        #           bit 6=1 ; Start bit
        #           bit 7=? ; Single-Ended/Differential
        #           bit 8=? ; D2 (Channel select)
        # Byte 2:   bit 1=? ; D1 (Channel select)
        #           bit 2=? ; D0 (Channel select)
        #         bit 3-*=* ; Remaining bits can be null, aren't read.
        # Results of read:
        # Byte 1: bit 1-8=* ; Undefined
        # Byte 2: bit 1-3=* ; Undefined
        #           bit 4=0 ; Reading Start
        #         bit 5-8=? ; Most significant 4 bits of reading
        # Byte 3: bit 1-8=? ; Remaining 8 bits of reading

        if channel not in self.__channels:
            raise TypeError("Channel %s not configured as input channel." % channel)
        else:
            cid = self.__channels[channel]

        read_command = [(0b1 << 2 | (cid & 0b1100) >> 2),
                        ((0b11 & cid) << 6),
                        0x00]

        reading = self.__spi.xfer2(read_command)

        ADC = ((reading[1] & 0b1111) << 8) + reading[2]  # Shift MSB up 8 bits, add to LSB
        v_in = float(ADC * self.V_ref) / 4096.
        return v_in

    def close(self):
        self.__spi.close()


class MCP3208(MCP320X):
    # Channel Setup:      0bD210 for bit S/D, D2, D1, D0
    __channels = {0:    0b1000,
                  1:    0b1001,
                  2:    0b1010,
                  3:    0b1011,
                  4:    0b1100,
                  5:    0b1101,
                  6:    0b1110,
                  7:    0b1111,
                  '01': 0b0000,
                  '10': 0b0001,
                  '23': 0b0010,
                  '32': 0b0011,
                  '45': 0b0100,
                  '54': 0b0101,
                  '67': 0b0110,
                  '76': 0b0111}

    def __init__(self, channels=None, *args, **kwargs):
        super(MCP3208, self).__init__(*args, **kwargs)

        if channels is not None:
            new_channels = dict()
            for channel in channels:
                if channel in self.channels:
                    new_channels.update({channel: self.channels[channel]})
                else:
                    raise TypeError("MCP3208 does not support channel configuration %s" % channel)
            self.channels = new_channels
