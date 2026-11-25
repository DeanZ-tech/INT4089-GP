# Arduino libraries

Select Arduino UNO in Arduino IDE. The project uses these external library versions, confirmed by Group G:

| Library | Version | Purpose | Official source |
| --- | --- | --- | --- |
| Adafruit VL53L0X | 1.2.5 | VL53L0X distance sensor; `Adafruit_VL53L0X.h` | https://github.com/adafruit/Adafruit_VL53L0X |
| U8g2 | 2.36.19 | OLED text display through `U8x8lib.h` | https://github.com/olikraus/u8g2 |

In Arduino IDE, open **Tools → Manage Libraries**, search for each library, select the version above and install it. Install any dependencies requested by Library Manager.

`Wire.h`, `EEPROM.h` and `avr/pgmspace.h` are supplied by the Arduino AVR board/toolchain environment; they do not require separate copies in this repository. Select the UNO board package before compiling.

Official installation guide: https://support.arduino.cc/hc/en-us/articles/5145457742236-Install-libraries-in-the-Arduino-IDE
