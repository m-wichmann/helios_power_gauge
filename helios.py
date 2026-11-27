#!/usr/bin/env python3

import os
import time
import math
import datetime
import asyncio

import spidev
import gpiozero
from PIL import Image, ImageDraw, ImageFont

from solaredged import SolarEdge
from tmodbus import create_async_tcp_client


VERBOSE = False
DISPLAY_REFRESH_TIME = 10 * 60

# TODO: Add IP and port
CONVERTER_IP = '192.168.0.100'
CONVERTER_PORT = 502
WALLBOX_IP = '192.168.0.101'
WALLBOX_PORT = 502

# TODO: Add RFID card ids and strings
WALLBOX_RFID_CARDS = {
    
}


class Display:
    WIDTH = 296
    HEIGHT = 128

    EPD_CMD_PANEL_SETTING = 0x00
    EPD_CMD_POWER_OFF = 0x02
    EPD_CMD_POWER_ON = 0x04
    EPD_CMD_DEEP_SLEEP = 0x07
    EPD_CMD_DISPLAY_START_BW = 0x10
    EPD_CMD_DISPLAY_REFRESH = 0x12
    EPD_CMD_DISPLAY_START_R = 0x13
    EPD_CMD_VCOM_DATA_INTERVAL = 0x50
    EPD_CMD_RESOLUTION_SETTING = 0x61
    EPD_CMD_GET_STATUS = 0x71
    EPD_PARAM_DEEP_SLEEP_CHECK_CODE = 0xa5

    def __enter__(self):
        self.GPIO_RST_PIN = gpiozero.LED("GPIO17")
        self.GPIO_DC_PIN = gpiozero.LED("GPIO25")
        self.GPIO_BUSY_PIN = gpiozero.Button("GPIO24", pull_up = False)
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)
        self.spi.max_speed_hz = 4_000_000
        self.spi.mode = 0

        self._init_display()
        self.clear()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._sleep()
        self.spi.close()
        self.GPIO_RST_PIN.off()
        self.GPIO_DC_PIN.off()
        del self.spi
        del self.GPIO_RST_PIN
        del self.GPIO_DC_PIN
        del self.GPIO_BUSY_PIN
        return False

    def _set_pin_rst(self, value):
        self.GPIO_RST_PIN.on() if value else self.GPIO_RST_PIN.off()

    def _set_pin_dc(self, value):
        self.GPIO_DC_PIN.on() if value else self.GPIO_DC_PIN.off()

    def _get_pin_busy(self):
        return self.GPIO_BUSY_PIN.value

    def _spi_writebyte(self, data):
        self.spi.writebytes(data)

    def _spi_writebyte2(self, data):
        self.spi.writebytes2(data)

    def _reset(self):
        self._set_pin_rst(1)
        time.sleep(0.200)
        self._set_pin_rst(0)
        time.sleep(0.002)
        self._set_pin_rst(1)
        time.sleep(0.200)

    def _send_command(self, command):
        self._set_pin_dc(0)
        self._spi_writebyte([command])

    def _send_data(self, data):
        self._set_pin_dc(1)
        self._spi_writebyte([data])

    def _send_data2(self, data):
        self._set_pin_dc(1)
        self._spi_writebyte2(data)

    def _read_busy(self):
        self._send_command(Display.EPD_CMD_GET_STATUS)
        while self._get_pin_busy() == 0:
            self._send_command(Display.EPD_CMD_GET_STATUS)
            time.sleep(0.200)

    def _init_display(self):
        self._reset()

        self._send_command(Display.EPD_CMD_POWER_ON)
        self._read_busy()

        self._send_command(Display.EPD_CMD_PANEL_SETTING)
        self._send_data(0x8f)

        self._send_command(Display.EPD_CMD_RESOLUTION_SETTING)
        self._send_data(0x80)
        self._send_data(0x01)
        self._send_data(0x28)

        self._send_command(Display.EPD_CMD_VCOM_DATA_INTERVAL)
        self._send_data(0x77)

        self._send_command(Display.EPD_CMD_POWER_OFF)
        self._read_busy()

    def _sleep(self):
        self._send_command(Display.EPD_CMD_POWER_OFF)
        self._read_busy()
        self._send_command(Display.EPD_CMD_DEEP_SLEEP)
        self._send_data(Display.EPD_PARAM_DEEP_SLEEP_CHECK_CODE)
        time.sleep(2.000)

    def display(self, blackimage, ryimage):
        self._send_command(Display.EPD_CMD_POWER_ON)
        self._read_busy()

        if blackimage is not None:
            if isinstance(blackimage, Image.Image):
                blackimage = self._getbuffer(blackimage)
            self._send_command(Display.EPD_CMD_DISPLAY_START_BW)
            self._send_data2(blackimage)

        if ryimage is not None:
            if isinstance(ryimage, Image.Image):
                ryimage = self._getbuffer(ryimage)
            self._send_command(Display.EPD_CMD_DISPLAY_START_R)
            self._send_data2(ryimage)

        self._send_command(Display.EPD_CMD_DISPLAY_REFRESH)
        time.sleep(0.200)
        self._read_busy()

        self._send_command(Display.EPD_CMD_POWER_OFF)
        self._read_busy()

    def clear(self):
        self.display([0xff] * int(Display.WIDTH * Display.HEIGHT / 8), [0xff] * int(Display.WIDTH * Display.HEIGHT / 8))

    def _getbuffer(self, image):
        """Transpose image data. PIL image uses 0,0 for top left corner with direct pixel access. The display uses
        8 Pixel per byte, with the first pixel beeing the top bit of the first byte and the top right corner of the
        display. The pixels are drawn by cols from top-right to bottom-right, ending bottom-left with the last pixel."""
        buf = [0xFF] * (int(Display.WIDTH/8) * Display.HEIGHT)
        image_monocolor = image.convert('1')
        imwidth, imheight = image_monocolor.size
        pixels = image_monocolor.load()
        for x in range(imwidth):
            for y in range(imheight):
                if pixels[x, y] == 0:
                    x_dst = imwidth - x - 1
                    buf[x_dst * (Display.HEIGHT // 8) + (y // 8)] &= ~(0x80 >> (y % 8))
        return buf


class Designer:
    FONT_PATH = 'arial.ttf'
    RESSOURCE_DIR = os.path.dirname(os.path.realpath(__file__))

    def __init__(self, display):
        self.display = display
        self.font = ImageFont.truetype(os.path.join(Designer.RESSOURCE_DIR, Designer.FONT_PATH), 18)
        self.font_small = ImageFont.truetype(os.path.join(Designer.RESSOURCE_DIR, Designer.FONT_PATH), 11)
        self.image_buffer = None
        self.draw = None

    def _draw_battery(self, state):
        self.draw.rectangle((1+5, 15, 29-5, 20), fill=1, outline=0)
        self.draw.rectangle((1, 20, 29, 102), fill=1, outline=0)
        self.draw.rectangle((3, 22+2*0+14*0, 27, 22+2*0+14*1), fill=0 if state > 90 else 1, outline=0)
        self.draw.rectangle((3, 22+2*1+14*1, 27, 22+2*1+14*2), fill=0 if state > 70 else 1, outline=0)
        self.draw.rectangle((3, 22+2*2+14*2, 27, 22+2*2+14*3), fill=0 if state > 50 else 1, outline=0)
        self.draw.rectangle((3, 22+2*3+14*3, 27, 22+2*3+14*4), fill=0 if state > 30 else 1, outline=0)
        self.draw.rectangle((3, 22+2*4+14*4, 27, 22+2*4+14*5), fill=0 if state > 10 else 1, outline=0)
        self.draw.text((5, 105), f'{state:2.0f}%', font=self.font, fill=0)

    def _draw_house(self, state):
        w = 35
        d = 15
        lt = (self.display.WIDTH/2-w, 60)
        rt = (self.display.WIDTH/2+w, 60)
        lb = (self.display.WIDTH/2-w, 87)
        rb = (self.display.WIDTH/2+w, 87)
        top = (self.display.WIDTH/2, 40)
        text = (self.display.WIDTH/2, 75)

        self.draw.line((lt, lb), fill=0, width=3)
        self.draw.line((lb, rb), fill=0, width=3)
        self.draw.line((rt, rb), fill=0, width=3)

        base_turn = math.degrees(math.atan2(lt[1] - top[1], lt[0] - top[0]))
        temp_x = lt[0] + d * math.cos(math.radians(base_turn))
        temp_y = lt[1] + d * math.sin(math.radians(base_turn))
        self.draw.line(((temp_x, temp_y), (top[0], top[1])), fill=0, width=3)

        base_turn = math.degrees(math.atan2(rt[1] - top[1], rt[0] - top[0]))
        temp_x = rt[0] + d * math.cos(math.radians(base_turn))
        temp_y = rt[1] + d * math.sin(math.radians(base_turn))
        self.draw.line(((temp_x, temp_y), (top[0], top[1])), fill=0, width=3)

        self.draw.text(text, f'{format_measurement(state, "W")}', font=self.font, fill=0, anchor='mm')

    def _draw_car(self, type_str):
        if type_str:
            self.image_buffer.paste(Image.open('car.png'), (250, 45))
            self.draw.text((252, 15), type_str, font=self.font_small, fill=0)

    def _draw_arrow(self, coord0, coord1, invert=False, draw_head=True):
        d = 15
        angle = 35

        if invert:
            coord1, coord0 = coord0, coord1

        base_turn = math.degrees(math.atan2(coord1[1] - coord0[1], coord1[0] - coord0[0]))
        x1_back = coord1[0] + (d*0.8) * math.cos(math.radians(base_turn + 180))
        y1_back = coord1[1] + (d*0.8) * math.sin(math.radians(base_turn + 180))
        x1_top = coord1[0] + d * math.cos(math.radians(base_turn + 180 + angle))
        y1_top = coord1[1] + d * math.sin(math.radians(base_turn + 180 + angle))
        x1_bot = coord1[0] + d * math.cos(math.radians(base_turn + 180 - angle))
        y1_bot = coord1[1] + d * math.sin(math.radians(base_turn + 180 - angle))

        if draw_head:
            self.draw.line(((coord0[0], coord0[1]), (x1_back, y1_back)), fill=0, width=3)
            self.draw.polygon(((coord1[0], coord1[1]), (x1_top, y1_top), (x1_bot, y1_bot)), fill=0, outline=0)
        else:
            self.draw.line(((coord0[0], coord0[1]), (coord1[0], coord1[1])), fill=0, width=3)

    def _draw_timestamp(self):
        current_time = datetime.datetime.now().strftime("%d.%m.%y %H:%M")
        self.draw.text((296, 128), f'{current_time}', font=self.font_small, anchor='rb', fill=0)

    def _draw_labels(self, p_bat, p_pv, p_grid, p_car):
        if p_bat: self.draw.text((40, 75), f'{format_measurement(p_bat, "W")}', font=self.font, fill=0)
        if p_pv: self.draw.text((157, 2), f'{format_measurement(p_pv, "W")}', font=self.font, fill=0)
        if p_grid: self.draw.text((157, 108), f'{format_measurement(p_grid, "W")}', font=self.font, fill=0)
        if p_car: self.draw.text((193, 75), f'{format_measurement(p_car, "W")}', font=self.font, fill=0)

    def draw_data(self, data):
        if VERBOSE:
            print(data)

        self.image_buffer = Image.new(mode='1', size=(self.display.WIDTH, self.display.HEIGHT), color=1)
        self.draw = ImageDraw.Draw(self.image_buffer)

        self._draw_battery(data.battery_charge_level)
        self._draw_house(data.power_usage)

        # set car name to be displayed depending on RFID data
        car_name = WALLBOX_RFID_CARDS.get(data.charger_rfid_card, '')
        self._draw_car(car_name)

        # switch arrow direction to battery depending on charging status
        if data.battery_charge_status == 4:
            # discharging
            self._draw_arrow((35, 64), (90, 64))
        elif data.battery_charge_status == 3:
            # charging
            self._draw_arrow((90, 64), (35, 64))
        elif data.battery_charge_status == 7:
            # idle, do not draw arrow if battery is neither charging nor discharging
            pass

        # draw arrow from PV only when energy is supplied
        if data.power_from_pv > 0:
            self._draw_arrow((self.display.WIDTH/2, 4), (self.display.WIDTH/2, 35))
        else:
            self._draw_arrow((self.display.WIDTH/2, 35), (self.display.WIDTH/2, 4))

        # draw arrow to charging station only when car is charging
        if data.charger_charging_status == 3:
            self._draw_arrow((205, 64), (245, 64))

        # check whether grid is supplying power or energy is fed back into the grid
        if data.power_from_grid > 0:
            self._draw_arrow((self.display.WIDTH/2, 124), (self.display.WIDTH/2, 95))
        else:
            self._draw_arrow((self.display.WIDTH/2, 95), (self.display.WIDTH/2, 124))

        self._draw_labels(abs(data.battery_charge_power), abs(data.power_from_pv), abs(data.power_from_grid), data.charger_active_power)

        self._draw_timestamp()

        if VERBOSE:
            self.image_buffer.save('helios_output.png')

        self.display.display(self.image_buffer, None)


class HeliosException(Exception):
    """Custom exception for Helios Power Gauge."""


def convert_registers_to_uint32(registers):
    """Convert two 16-bit registers to a 32-bit unsigned integer."""
    if len(registers) < 2:
        raise HeliosException('Unexpected Modbus register value: insufficient registers')
    return (registers[0] << 16) | registers[1]


def convert_registers_to_int32(registers):
    """Convert two 16-bit registers to a 32-bit signed integer."""
    if len(registers) < 2:
        raise HeliosException('Unexpected Modbus register value: insufficient registers')
    value = (registers[0] << 16) | registers[1]
    if value >= 0x80000000:
        value -= 0x100000000
    return value


async def read_data_from_charging_station_via_modbus():
    """
    Read all necessary data points from the wallbox by ModbusTCP.

    References:
     - Modbus addresses for wallbox:
       https://a.storyblok.com/f/40131/x/44932c2bc8/kecontactp30modbustcp_pgen.pdf
    """
    async with create_async_tcp_client(WALLBOX_IP, WALLBOX_PORT, unit_id=1) as client:
        # read charging status
        result = await client.read_holding_registers(1000, 2)
        charging_status = convert_registers_to_uint32(result)
        # read total energy (register contains the total energy consumption in 0.1 watt-hours)
        result = await client.read_holding_registers(1036, 2)
        total_energy = convert_registers_to_uint32(result) / 10000
        # read active power (register contains the active power in milliwatts)
        result = await client.read_holding_registers(1020, 2)
        active_power = convert_registers_to_uint32(result) / 1000
        # read RFID card number
        result = await client.read_holding_registers(1500, 2)
        rfid_card = convert_registers_to_uint32(result)
        # read charged energy (register contains the transferred energy of the current session in 0.1 watt-hours)
        result = await client.read_holding_registers(1502, 2)
        charged_energy_for_session = convert_registers_to_uint32(result) / 10000
    return charging_status, total_energy, active_power, rfid_card, charged_energy_for_session


async def read_data_from_converter_via_modbus():
    """
    Read all necessary data points from the converter by ModbusTCP.

    References:
     - Modbus addresses for inverter:
       https://knowledge-center.solaredge.com/sites/kc/files/sunspec-implementation-technical-note.pdf
     - tmodbus:
       https://github.com/wlcrs/tmodbus
    """
    async with create_async_tcp_client(CONVERTER_IP, CONVERTER_PORT, unit_id=1) as client:
        # detect the layout of the inverter
        solaredge = await SolarEdge.async_probe(client)
        await solaredge.async_update()  # one read per sub-system
        inverter = solaredge.inverter
        power_from_pv = inverter.ac_power
        if VERBOSE:
            print(f"{solaredge.common.manufacturer} {solaredge.common.model}: {inverter.status.name}")
        battery = solaredge.batteries[0]
        battery_charge_level = battery.state_of_energy if battery.state_of_energy is not None else 0
        battery_charge_status = battery.status if battery.status else 0
        battery_charge_power = battery.dc_power if battery.dc_power is not None else 0
        meter = solaredge.meters[0]
        power_from_grid = -meter.ac_power
    return battery_charge_level, battery_charge_status, battery_charge_power, power_from_grid, power_from_pv+battery_charge_power


def format_measurement(value, unit):
    """
    Formats a measurement value with the correct unit and always 3 significant
    places depending on the magnitude of the value.
    """
    if not value:
        return f'0 {unit}'
    if unit == 'kWh':
        return f'{value:.0f} {unit}'
    if unit == '%':
        return f'{value:.0f} {unit}'
    try:
        magnitude = int(math.floor(math.log10(abs(float(value)))))
        match magnitude:
            case 0: return f'{value:.0f} {unit}'
            case 1: return f'{value:.0f} {unit}'
            case 2: return f'{value:.0f} {unit}'
            case 3: return f'{value/1000:.1f} k{unit}'
            case 4: return f'{value/1000:.0f} k{unit}'
            case 5: return f'{value/1000:.0f} k{unit}'
            case _: return f'{value:.1f} {unit}'
    except ValueError:
        return f'{value} {unit}'


class MeasuringData:
    def __init__(self):
        self.battery_charge_level = 0
        self.battery_charge_status = 'Unknown'
        self.battery_charge_power = 0
        self.power_from_grid = 0
        self.power_from_pv = 0
        self.power_usage = 0
        self.charger_charging_status = 0
        self.charger_total_energy = 0
        self.charger_active_power = 0
        self.charger_rfid_card = 0
        self.charger_energy_for_session = 0

    async def load_data(self):
        """Asynchronously load data from Modbus."""
        self.battery_charge_level, self.battery_charge_status, self.battery_charge_power, self.power_from_grid, self.power_from_pv = await read_data_from_converter_via_modbus()
        self.charger_charging_status, self.charger_total_energy, self.charger_active_power, self.charger_rfid_card, self.charger_energy_for_session = await read_data_from_charging_station_via_modbus()
        # calculate power usage of house without charger depending on inputs (PV and grid) and outputs (battery and charger)
        self.power_usage = self.power_from_grid + self.power_from_pv - self.battery_charge_power - self.charger_active_power

    def __str__(self):
        charging_status_values = {
            0: 'Start-up of the charging station',
            1: 'The charging station is not ready for charging',
            2: 'The charging station is ready for charging and waits for a reaction from the electric vehicle.',
            3: 'A charging process is active.',
            4: 'An error has occurred.',
            5: 'The charging process is temporarily interrupted because the temperature is too high or the wallbox is in suspended mode.',
        }

        # battery charge status values
        # source: https://github.com/frenck/python-solaredged/blob/dc6c0241d34ad93f118f3a443a26483fd283131a/src/solaredged/const.py#L107
        battery_charge_status_values = {
            0: 'Off',
            1: 'Standby',
            2: 'Init',
            3: 'Charge',
            4: 'Discharge',
            5: 'Fault',
            6: 'Preserve Charge',
            7: 'Idle',
            10: 'Power Saving'
        }

        ret = ''
        ret += f'Battery -> charge level: {self.battery_charge_level} %\n'
        ret += f'Battery -> charge status: {battery_charge_status_values[self.battery_charge_status]}\n'
        ret += f'Battery -> charge power: {self.battery_charge_power} W\n'
        ret += f'Power from grid: {self.power_from_grid} W\n'
        ret += f'Power from PV: {self.power_from_pv} W\n'
        ret += f'Power usage (without charger): {self.power_usage} W\n'
        ret += f'Charger -> charging status: {charging_status_values[self.charger_charging_status]}\n'
        ret += f'Charger -> total energy: {self.charger_total_energy} kWh\n'
        ret += f'Charger -> active power: {self.charger_active_power} W\n'
        ret += f'Charger -> RFID card: {self.charger_rfid_card:0x}\n'
        ret += f'Charger -> energy for current session: {self.charger_energy_for_session} kWh\n'
        return ret


if __name__ == '__main__':
    async def main():
        data = MeasuringData()
        with Display() as display:
            designer = Designer(display)
            while True:
                await data.load_data()
                designer.draw_data(data)
                await asyncio.sleep(DISPLAY_REFRESH_TIME)

    asyncio.run(main())
