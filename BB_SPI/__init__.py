import time
import RPi.GPIO as GPIO


class SpiDev(object):
    SCLK_pin = -1
    MISO_pin = -1
    MOSI_pin = -1
    CS_pins = None  # type: List(int)
    _max_speed_hz = 7000
    bitlen = 8
    last_cs = 0
    bus = 0
    _mode = None

    def __init__(self, clock=21, miso=19, mosi=20, cs=(18, 17, 16), *args, **kwargs):

        self.SCLK_pin = clock
        self.MISO_pin = miso
        self.MOSI_pin = mosi

        try:
            self.CS_pins = [i for i in cs]
        except IndexError:
            self.CS_pins = [cs]
            self.last_cs = cs

        self._mode = [0b01] * len(self.CS_pins)

        if 'clockspeed' in kwargs:
            self.max_speed_hz = kwargs['clockspeed']
        else:
            self.max_speed_hz = self._max_speed_hz

        self.MASKs = [1 << i for i in range(self.bitlen - 1, -1, -1)]

        self.spi_setup()

    @property
    def mode(self):
        return self._mode[self.last_cs]

    @mode.setter
    def mode(self, mode):
        self._mode[self.last_cs] = mode

    @property
    def max_speed_hz(self):
        return self._max_speed_hz

    @max_speed_hz.setter
    def max_speed_hz(self, clockspeed):

        self._max_speed_hz = clockspeed
        self.t_CSSC = 100e-9
        self.t_SCCS = 100e-9
        self.t_CSH = 200e-9
        self.t_SCLK = max(250e-9, 1. / self._max_speed_hz)
        self.t_SPWH = max(100e-9, 0.5 / self._max_speed_hz)
        self.t_SPWL = max(100e-9, 0.5 / self._max_speed_hz)
        self.t_DIST = 50e-9
        self.t_DIHD = 50e-9

    def spi_setup(self):
        GPIO.setmode(GPIO.BCM)
        # set up the SPI interface pins
        GPIO.setup(self.MOSI_pin, GPIO.OUT, initial=False)
        GPIO.setup(self.MISO_pin, GPIO.IN)
        GPIO.setup(self.SCLK_pin, GPIO.OUT, initial=bool(self._mode[0] & 0b10))

        for cspin in self.CS_pins:
            GPIO.setup(cspin, GPIO.OUT, initial=True)

    def spi_write(self, data, cs=None):
        if cs is None:
            cs = self.last_cs
        else:
            self.last_cs = cs

        CPHA = bool(self._mode[cs] & 0b01)
        CS_ASSERTED = False
        data_out = []
        CLK_IO = bool(self._mode[cs] & 0b10)
        CLK_CH = not CLK_IO
        cs_pin = self.CS_pins[cs]

        # Prepare initial clock state
        GPIO.output(self.SCLK_pin, CLK_IO)

        time.sleep(self.t_CSSC)
        if CPHA:  # Clock is read out on second edge
            GPIO.output(cs_pin, False)
            CS_ASSERTED = True
            time.sleep(self.t_CSSC)
        for byte in data:
            outbyte = 0
            for mask in self.MASKs:
                GPIO.output(self.SCLK_pin, CLK_CH)
                GPIO.output(self.MOSI_pin, bool(byte & mask))
                time.sleep(self.t_SPWH)
                if not CS_ASSERTED:  # Clock is read out on first edge
                    GPIO.output(cs_pin, False)
                    CS_ASSERTED = True
                    time.sleep(self.t_CSSC)
                GPIO.output(self.SCLK_pin, CLK_IO)
                outbyte = (outbyte << 1) | GPIO.input(self.MISO_pin)
                time.sleep(self.t_SPWL)
            data_out.append(outbyte)

        time.sleep(max(0, self.t_SCCS - self.t_SPWL))
        GPIO.output(cs_pin, True)
        GPIO.output(self.SCLK_pin, CLK_CH)

        return data_out

    def spi_read(self, bytes=1, cs=None):
        return self.spi_write(data=([0x00] * bytes), cs=cs)

    def xfer(self, values=None):
        return [self.spi_write(data=i) for i in values]

    def xfer2(self, values=None):
        return self.spi_write(data=values)

    def open(self, bus, device):
        self.bus = bus
        self.last_cs = device

    def readbytes(self, bytes, *args, **kwargs):
        return self.spi_read(bytes=bytes)

    def writebytes(self, values, *args, **kwargs):
        self.xfer2(values)

    def fileno(self):
        pass

    def close(self):
        pass
