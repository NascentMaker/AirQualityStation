# SPDX-FileCopyrightText: 2021 Torgny Bjers
#
# SPDX-License-Identifier: Unlicense
import time

import adafruit_pm25
import alarm
import board
import busio
import rtc
from adafruit_bitmap_font import bitmap_font
from adafruit_bitmap_font.bdf import BDF
from adafruit_bitmap_font.pcf import PCF
from adafruit_bitmap_font.ttf import TTF
from adafruit_display_text import label
from adafruit_magtag.magtag import MagTag
from adafruit_pm25.i2c import PM25_I2C

from constants import (
    REFRESH_TIME,
    MAXIMUM_BACKOFF,
    SLEEP_MEMORY_SLOT_BACKOFF_TIMES,
    SLEEP_MEMORY_SLOT_BACKOFF,
    SLEEP_MEMORY_SLOT_PIN_ALARM,
    MINIMUM_BACKOFF,
    MAX_BACKOFF_COUNT,
)
from debug import print_particle_values


def clear_backoff() -> None:
    alarm.sleep_memory[SLEEP_MEMORY_SLOT_BACKOFF] = 0
    alarm.sleep_memory[SLEEP_MEMORY_SLOT_BACKOFF_TIMES] = 0


class AqMagTag:
    # private properties
    _connect_tries: int = 0
    _connected: bool = False
    _debug: bool = False
    _debug_display: bool = False
    _i2c: board.I2C = None
    _label_font: [BDF, PCF, TTF] = None
    _magtag: MagTag = None
    _num_samples: int = 0
    _numbers_font: [BDF, PCF, TTF] = None
    _pin = None
    _pm25: adafruit_pm25.PM25 = None
    _received_pin_alarm: bool = False
    _rtc: rtc.RTC = None
    _secrets: dict = {}
    _stats_font: [BDF, PCF, TTF] = None

    # public properties
    initialized: bool = False

    def __init__(self, debug: bool = False, debug_display: bool = False):
        self._debug = debug
        self._debug_display = debug_display
        self._num_samples = 1 if debug else 10

    def setup(self):
        if self.initialized:
            return
        self._setup_alarms()
        self._setup_magtag()
        self._handle_alarms()
        self._check_battery()
        self._setup_sensors()
        self._load_fonts()
        self._setup_labels()
        self.initialized = True

    def _setup_alarms(self):
        if self._debug:
            print('Setting up alarms... ', end='')
        # Set up alarms for the different buttons and timer
        self.pin_alarm = alarm.pin.PinAlarm(board.D14, value=False)
        self.time_alarm = alarm.time.TimeAlarm(monotonic_time=int(time.monotonic()) + (REFRESH_TIME * 60))
        if self._debug:
            print('OK')

    def _handle_alarms(self):

        if self._debug:
            print('Handle alarms... ', end='')

        if alarm.sleep_memory[SLEEP_MEMORY_SLOT_PIN_ALARM]:
            self._received_pin_alarm = True
            # attempt to decode the pin
            self._pin = getattr(board, dir(board)[alarm.sleep_memory[SLEEP_MEMORY_SLOT_PIN_ALARM]])
            alarm.sleep_memory[SLEEP_MEMORY_SLOT_PIN_ALARM] = False

        if isinstance(alarm.wake_alarm, alarm.pin.PinAlarm):
            self._received_pin_alarm = True
            self._pin = alarm.wake_alarm.pin

        # Handle pin alarm
        if self._received_pin_alarm:
            print(f'Light level: {self._magtag.peripherals.light}')
            # Check what the light level is before we blind someone
            neopixel_brightness = 0.25
            if self._magtag.peripherals.light < 700:
                neopixel_brightness = 0.5
            if self._magtag.peripherals.light < 1500:
                neopixel_brightness = 0.75
            if self._magtag.peripherals.light < 2000:
                neopixel_brightness = 1
            self._magtag.peripherals.neopixel_disable = False
            self._magtag.peripherals.neopixels.brightness = neopixel_brightness
            self._magtag.peripherals.neopixels.fill((255, 255, 255))
            self._magtag.peripherals.neopixels.show()
            time.sleep(6)
            self.deep_sleep()
        elif alarm.wake_alarm:
            for i in range(4):
                time.sleep(0.5)
                self._magtag.peripherals.neopixels[0] = (255, 255, 0)
                time.sleep(0.25)
                self._magtag.peripherals.neopixels[0] = (0, 0, 0)

        if self._debug:
            print('OK')

    def _check_battery(self):
        if self._magtag.peripherals.battery < 3.5:
            if self._debug:
                print(f'Battery voltage at {self._magtag.peripherals.battery}, need to charge.')
            for i in range(3):
                self._magtag.peripherals.play_tone(2600, 0.1)
                time.sleep(0.2)

    def _setup_magtag(self):
        # Create a new MagTag object
        self._magtag = MagTag(default_bg=0xFFFFFF, debug=True)
        # noinspection PyProtectedMember
        self._secrets = self._magtag.network._secrets
        # Default configuration for MagTag
        self._magtag.peripherals.neopixels.auto_write = True
        self._magtag.peripherals.neopixels.brightness = 255
        # Set up the Real Time Clock
        self._rtc = rtc.RTC()
        self._magtag.peripherals.neopixels[0] = (0, 40, 0)

    def _setup_sensors(self):
        # Set up i2c and pm25 sensor
        self._i2c = busio.I2C(board.SCL, board.SDA, frequency=100000)
        if self._debug:
            print('Connect PM25 sensor via I2C... ', end='')
        self._pm25 = PM25_I2C(self._i2c, None)
        if self._debug:
            print('OK')

    def _load_fonts(self):
        self._label_font = bitmap_font.load_font("fonts/FredokaOne-Regular-18.pcf")
        self._numbers_font = bitmap_font.load_font("fonts/FredokaOne-Regular-46.pcf")
        self._stats_font = bitmap_font.load_font("fonts/Tamzen-9.pcf")

    def _setup_labels(self):
        self._pm10value_label = label.Label(self._numbers_font, color=0x000000, anchor_point=(0.5, 0.5), anchored_position=(53, 35))
        self._pm10label_label = label.Label(self._label_font, color=0x666666, text="PM 1.0", anchor_point=(0.5, 0.5), anchored_position=(53, 70))
        self._magtag.splash.append(self._pm10value_label)
        self._magtag.splash.append(self._pm10label_label)

        self._pm25value_label = label.Label(self._numbers_font, color=0x000000, anchor_point=(0.5, 0.5), anchored_position=(148, 35))
        self._pm25label_label = label.Label(self._label_font, color=0x666666, text="PM 2.5", anchor_point=(0.5, 0.5), anchored_position=(148, 70))
        self._magtag.splash.append(self._pm25value_label)
        self._magtag.splash.append(self._pm25label_label)

        self._pm100value_label = label.Label(self._numbers_font, color=0x000000, anchor_point=(0.5, 0.5), anchored_position=(243, 35))
        self._pm100label_label = label.Label(self._label_font, color=0x666666, text="PM 10", anchor_point=(0.5, 0.5), anchored_position=(243, 70))
        self._magtag.splash.append(self._pm100value_label)
        self._magtag.splash.append(self._pm100label_label)

        self._stats_label = label.Label(self._stats_font, color=0x000000, anchor_point=(0, 0), anchored_position=(12, 100))
        self._magtag.splash.append(self._stats_label)

    def deep_sleep(self, backoff: bool = False) -> None:
        self._magtag.peripherals.neopixel_disable = True
        self._magtag.peripherals.speaker_disable = True
        if backoff:
            sleep_length = alarm.sleep_memory[SLEEP_MEMORY_SLOT_BACKOFF]
            print(f'ERROR, EXPONENTIAL BACKOFF: Sleeping for {sleep_length} seconds.')
            backoff_alarm = alarm.time.TimeAlarm(monotonic_time=int(time.monotonic()) + sleep_length)
            alarm.exit_and_deep_sleep_until_alarms(backoff_alarm)
        print(f'Sleeping for {REFRESH_TIME:d} minutes')
        alarm.exit_and_deep_sleep_until_alarms(self.pin_alarm, self.time_alarm)

    def deep_sleep_exponential_backoff(self) -> None:
        sleep_time = alarm.sleep_memory[SLEEP_MEMORY_SLOT_BACKOFF]
        backoff_count = alarm.sleep_memory[SLEEP_MEMORY_SLOT_BACKOFF_TIMES]
        if not sleep_time:
            sleep_time = MINIMUM_BACKOFF
            backoff_count = 0
        if MINIMUM_BACKOFF < sleep_time < MAXIMUM_BACKOFF:
            sleep_time *= 2
        backoff_count += 1
        alarm.sleep_memory[SLEEP_MEMORY_SLOT_BACKOFF] = sleep_time
        alarm.sleep_memory[SLEEP_MEMORY_SLOT_BACKOFF_TIMES] = backoff_count
        if backoff_count >= MAX_BACKOFF_COUNT:
            raise ConnectionError('Unable to connect after backoff expired')
        self.deep_sleep(backoff=True)

    def connect(self):
        self._magtag.peripherals.neopixels[0] = (70, 70, 10)

        while self._connect_tries <= 5:
            try:
                self._magtag.network.connect()
                if self._magtag.network.enabled:
                    self._connected = True
                    break
            except ConnectionError:
                print("Cannot connect to network. Retrying...")
                time.sleep(3)
                self._connect_tries += 1

        if not self._connected:
            print("Cannot connect to network. Sleeping for five minutes.")
            for i in range(5):
                self._magtag.peripherals.play_tone(1200, 0.05)
                time.sleep(0.09)
            self._magtag.exit_and_deep_sleep(60 * 5)
        else:
            print("Connection established.")

        self._magtag.peripherals.neopixels[0] = (0, 255, 0)

        time.sleep(3)

        self._magtag.peripherals.neopixels[0] = 0

    def process_events(self):
        measurements = []
        failed_readings = 0
        if self._debug:
            print(f'Taking {self._num_samples} measurement{"s" if self._num_samples > 1 else ""} from PM25 sensor... ', end='')
        for c in range(self._num_samples):
            if failed_readings > 3:
                self._magtag.peripherals.neopixels[0] = (255, 0, 0)
                self.deep_sleep_exponential_backoff()
            self._magtag.peripherals.neopixels[0] = (255, 255, 0)
            time.sleep(0.25)
            try:
                measurements.append(self._pm25.read())
                self._magtag.peripherals.neopixels[0] = (0, 255, 0)
                time.sleep(0.25)
            except RuntimeError:
                print('Unable to read from sensor, retrying...')
                failed_readings += 1
                self._magtag.peripherals.neopixels[0] = (255, 0, 0)
                continue

        if self._debug:
            print("OK")

        totals = {}

        self._magtag.peripherals.neopixels[0] = (0, 80, 0)

        if measurements and len(measurements):
            columns = measurements[0].keys()
            for column in columns:
                feed_key = column.replace(' ', '-')
                totals[feed_key] = sum(i[column] for i in measurements) / len(measurements)
                if not self._debug:
                    print(f'Push {feed_key} to Adafruit IO... ', end='')
                    # TODO: Fix neopixels aren't working when pushing to feed
                    #       For some reason this isn't working while the MagTag is also pushing out
                    #       stats to the Adafruit IO API. Gotta be a way to have that light blink.
                    self._magtag.peripherals.neopixels[1] = (255, 0, 255)
                    time.sleep(0.25)
                    self._magtag.peripherals.neopixels[1] = (0, 255, 255)
                    failed_push = False
                    for x in range(3):
                        try:
                            self._magtag.push_to_io(feed_key=feed_key, metadata={}, data=totals[feed_key], precision=2)
                            failed_push = False
                            break
                        except RuntimeError:
                            failed_push = True
                            continue
                    print('FAIL' if failed_push else 'OK')

        self._magtag.peripherals.neopixels[1] = (0, 80, 0)

        self._pm10value_label.text = f'{totals["pm10-standard"]:.0f}'
        self._pm25value_label.text = f'{totals["pm25-standard"]:.0f}'
        self._pm100value_label.text = f'{totals["pm100-standard"]:.0f}'

        stats = f'0.3µm/0.1L: {totals["particles-03um"]:.1f}, 0.5µm/0.1L: {totals["particles-05um"]:.1f}, 1.0µm/0.1L: {totals["particles-10um"]:.1f}\n'
        stats += f'2.5µm/0.1L: {totals["particles-25um"]:.1f}, 5.0µm/0.1L: {totals["particles-50um"]:.1f}, 10µm/0.1L: {totals["particles-100um"]:.1f}'

        self._stats_label.text = stats

        board.DISPLAY.show(self._magtag.splash)
        board.DISPLAY.refresh()

        if self._debug:
            print_particle_values(totals)

        clear_backoff()
        self.deep_sleep()
