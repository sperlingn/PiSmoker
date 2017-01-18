import logging.config
import spidev
import time

# Start logging
logging.config.fileConfig('/home/pi/PiSmoker/logging.conf')
logger = logging.getLogger(__name__)

# Fault codes lookup
faultCodes = {0b10000000: 'Fault SPI %i: RTD High Threshold',
              0b01000000: 'Fault SPI %i: RTD Low Threshold',
              0b00100000: 'Fault SPI %i: REFIN- > 0.85 x V_BIAS',
              0b0001000:  'Fault SPI %i: REFIN- < 0.85 x V_BIAS (FORCE- Open)',
              0b00001000: 'Fault SPI %i: RTDIN- < 0.85 x V_BIAS (FORCE- Open)',
              0b00000100: 'Fault SPI %i: Overvoltage/undervoltage fault'}


# Datasheet https://datasheets.maximintegrated.com/en/ds/MAX31865.pdf
class MAX31865:
    # Reference Resistors
    R_0 = 0.  # @param R_0: double
    R_ref = 0.  # @param R_ref: Reference Resistance
    cs = None  # @param cs: Chip select number
    bus = None  # @param bus: SPI bus to be used
    spi = None  # @type spi: spidev
    fault = None  # @type fault: last fault code

    def __init__(self, cs=0, R_0=None, R_ref=None, ThreeWire=False, bus=0, spi_mode=0b01):
        """

        @param cs: Chip Select
        @type cs: int
        @param R_0: Resistance at 0C
        @type R_0: numeric
        @param R_ref: Reference Resistor value
        @type R_ref: numeric
        @param ThreeWire: RTD is three-wire type.
        @type ThreeWire: bool

        """
        self.cs = cs
        self.bus = bus
        self.ThreeWire = ThreeWire

        self.R_0 = R_0
        self.R_ref = R_ref

        self.setupSPI(mode=spi_mode, speed=61000)

        self.config()

    def setupSPI(self, mode=0b01, speed=7629):
        """Set up the SPI bus for the parameters set.

        @param mode: SPI Mode
        @type mode: Byte (0-3)
        @param speed: Max SPI speed in Hz
        @type speed: int
        @return: None
        @rtype: None
        """

        # Setup SPI
        if not mode & 0b01:
            raise TypeError("MAX31865 only supports SPI modes 1 and 3.")
        if speed > 5e6:
            raise TypeError("MAX31865 max SPI clock is 5MHz")

        self.spi = spidev.SpiDev()
        self.spi.open(self.bus, self.cs)
        self.spi.max_speed_hz = speed
        self.spi.mode = mode

    def config(self):
        # Config
        # V_Bias (1=on)
        # Conversion Mode (1 = Auto)
        # 1-Shot
        # 3-Wire (0 = Off)
        # Fault Detection (2 Bits)
        # Fault Detection
        # Fault Status
        # 50/60Hz (0 = 60 Hz)
        if self.ThreeWire:
            config = 0b11010010  # 0xD2
        else:
            config = 0b11000010  # 0xC2

        self.spi.xfer2([0x80, config])
        time.sleep(0.25)
        self.read()

    def read(self):
        MSB = self.spi.xfer2([0x01, 0x00])[1]
        LSB = self.spi.xfer2([0x02, 0x00])[1]

        # Check fault
        if LSB & 0b00000001:
            logger.debug('Fault Detected SPI %i', self.cs)
            self.fault = self.readFault()
        else:
            self.fault = None

        ADC = ((MSB << 8) + LSB) >> 1  # Shift MSB up 8 bits, add to LSB, remove fault bit (last bit)
        R_RTD = float(ADC * self.R_ref) / (2 ** 15)
        return R_RTD

    def readFault(self):
        """ Requests last fault code from the chip, logs it, and returns value.

        @return: Fault code returned from chip
        @rtype: int
        """
        Fault = self.spi.xfer2([0x07, 0x00])[1]

        logger.debug(faultCodes[Fault], self.cs)

        return Fault

    def getFault(self):
        """Get last fault code and description, or None if no fault.

        @return: Fault code and description.
        @rtype: (int, string)
        """
        if self.fault:
            return self.fault, faultCodes[self.fault].format(self.cs)
        else:
            return None

    def close(self):
        self.spi.close()
