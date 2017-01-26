# PiSmoker

##Dependencies
* RPI.GPIO
* spidev
* [Adafruit_Python_CharLCD](https://github.com/adafruit/Adafruit_Python_CharLCD)
* [Python-firebase](https://github.com/ozgur/python-firebase) Use github version instead of pip


## Schematics and Boards
* PiSmoker_pwr_triac_isol -- AC handling board, includes SW PS for backpowering Raspi.
* PiSmoker_sig_v1.1 -- Signal boards, conforms to Pi HAT specifications, including EEPROM.

Signal board and power board for traic based control.  Includes board power with isolation and 4 triacs.  Signaling board has space for 1 RTD via MAX31865, 2 thermocouples (and internal temperature sensor) via ADS1118, and 2 thermocouples and 4 thermistor probes via MCP3208.  Using MAX31865 temperature for CJC for all thermocouples should be possible due to placement underneath connector.

## Work to be done

* TODO: Create EEPROM image.
* TODO: Update software to support new devices, switch pins, etc.
* TODO: Add support for firebox burnout sensor (purpose of TC1, hotbox TC to see if temp is >setpoint, will require testing temps).  Should be able to run igniter if it is sensed early enough without having to clear out the firebox of pellets or blow the temperature range.
* TODO: Add parsing of EEPROM settings.
