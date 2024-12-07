# Helios Power Gauge
The Helios Power Gauge is a simple display of power data for the house, PV, battery and EV wallbox. The project is rather specific to this setup and is not meant to be generalised, but maybe someone still finds something useful.


## Software
Helios was setup on Raspberry Pi OS by copying the necessary files and setting up a systemd unit. Following steps need to be done:
* Install Raspberry Pi OS (tested with Debian 12 Bookworm)
* Activate SPI via `raspi-config`
* Setup all available WiFis: `nmtui`
* Install all requirements: `sudo apt install python3-spidev python3-pil python3-requests python3-pymodbus`
* Copy "helios.py", "arial.ttf" and "car.png" to /home/helios/
* Make script executable: `chmod a+x /home/helios/helios.py`
* Customize API keys, IPs... at the top of helios.py
* Copy "helios.service" to /etc/systemd/system/helios.service
* Activate service: `sudo systemctl enable helios`

The font "arial.ttf" is not distributed and needs to be copied from somewhere else. Or just use another font.


## Hardware
A Raspberry Pi Zero 2 W is the basis for Helios. The display is a Waveshare "2.9inch E-Paper E-Ink Display Module (B) for Raspberry Pi Pico" (see [1], [2], [3] and [4]). Following pins need to be connected between both boards:

    Display       RPi
    17 Busy <---> GPIO24 18
    16 RST  <---> GPIO17 11
    11 DC   <---> GPIO25 22
    12 CS   <---> GPIO8  24
    14 CLK  <---> GPIO11 23
    15 DIN  <---> GPIO10 19
    13 GND  <---> GND    20
    39 VCC  <---> 3V3    17

Be aware that the display contains a level shifter. The signals need to be soldered on the 3.3V side. The power suplly of the Raspberry Pi could be directly done using a USB cable. But since the case is to small to allow or normal plug I opted to solder GND and VCC of a USB cable directly to the board.


## Case
The case was designed using OnShape and the parametric design can be found [here](https://cad.onshape.com/documents/793ead52422ab2c3b7f9ba85/w/d6f01563430c41d83c825577/e/830e2b94e4fecfd9d25fe38c). The exported 3mf files are also found in this repo.

The design contains three parts. The display frame fastens the Rasperry Pi Zero and the Display together and allows the frame to be screwed to the front plate. The front plate contains practically everything else. The backlate slides into the front plate and is fixed with a screw. All screws are either M2.5 or M3 and nuts are glued in to be used as threads.


## Possible improvements
* The 2.9" (B) display is a three color variant that somehow does not like to be set in BW mode. At least I couldn't get it to work. The slow refresh time is pretty annoying. By using the normal 2.9" black and white version this would probably be faster.
* The display driver could probably be improved alot. Custom LUTs and partial refresh could result in basically flicker free refreshes (at least maybe with another display), but I just could not get it to work. Some interesting links can be found under [5], [6], [7] and [8].


## License
This project is licensed under MIT license. The image "car.png" is taken from Font Awesome.


## Links
[1] https://www.waveshare.com/wiki/Pico-ePaper-2.9-B

[2] https://www.waveshare.com/wiki/2.9inch_e-Paper_Module_(B)_Manual

[3] https://files.waveshare.com/upload/a/af/2.9inch-e-paper-b-v3-specification.pdf

[4] https://github.com/waveshareteam/e-Paper/blob/master/RaspberryPi_JetsonNano/python/lib/waveshare_epd/epd2in9b_V3.py

[5] https://github.com/adafruit/Adafruit_EPD/blob/master/src/drivers/Adafruit_UC8151D.cpp

[6] https://github.com/adafruit/Adafruit_CircuitPython_UC8151D/blob/main/adafruit_uc8151d.py

[7] https://github.com/olikraus/u8g2/issues/1393

[8] https://github.com/antirez/uc8151_micropython/
