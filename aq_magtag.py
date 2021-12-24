# SPDX-FileCopyrightText: 2021 Torgny Bjers
#
# SPDX-License-Identifier: Unlicense
import gc
import time

import adafruit_pm25
import adafruit_sht31d
import alarm
import board
import digitalio
import rtc
from adafruit_bitmap_font import bitmap_font
from adafruit_bitmap_font.bdf import BDF
from adafruit_bitmap_font.pcf import PCF
from adafruit_bitmap_font.ttf import TTF
from adafruit_display_text import label
from adafruit_magtag.magtag import MagTag
from adafruit_pm25.i2c import PM25_I2C

from constants import (
    MAXIMUM_BACKOFF,
    MAX_BACKOFF_COUNT,
    MINIMUM_BACKOFF,
    PM25_SENSOR_WARMUP_SECONDS,
    PM25_STANDBY_PIN,
    REFRESH_TIME,
    SLEEP_MEMORY_SLOT_BACKOFF,
    SLEEP_MEMORY_SLOT_BACKOFF_TIMES,
)


def clear_backoff() -> None:
    """
    Remove the backoff values from the sleep memory.
    """
    alarm.sleep_memory[SLEEP_MEMORY_SLOT_BACKOFF] = 0
    alarm.sleep_memory[SLEEP_MEMORY_SLOT_BACKOFF_TIMES] = 0


class AqMagTag:
    """AqMagTag uses MagTag and abstracts away the complexities.

    AqMagTag handles all the heavy lifting for the Air Quality MagTag Station.
    All you need to do is connect the sensors via I2C (Stemma QT) and power
    up your device.

    Args:
        debug: Enable debug output for the application. Disables send to Adafruit IO.
        debug_display: Display the screen layout and go into a loop.

    Attributes:
        initialized: True if the application has initialized.

    Examples:
        To get up and running with AqMagTag, follow this guide.

        >>> from aq_magtag import AqMagTag
        >>> aq = AqMagTag()
        >>> aq.setup()
        >>> aq.connect()
        >>> while True:
        >>>    aq.process_events()
    """

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
    _pm25_standby_pin: digitalio.DigitalInOut = None
    _relative_humidity: float = 0
    _rtc: rtc.RTC = None
    _secrets: dict = {}
    _sht31d = None
    _stats_font: [BDF, PCF, TTF] = None
    _temperature: float = 0

    # public properties
    initialized: bool = False

    def __init__(self, debug: bool = False, debug_display: bool = False) -> None:
        self._debug = debug
        self._debug_display = debug_display
        self._num_samples = 1 if debug else 10
        if not gc.isenabled():
            gc.enable()

    def setup(self) -> None:
        """
        Perform initialization of the modules we are using.
        """
        if self.initialized:
            return
        print('Start setup.')
        self._setup_alarms()
        self._setup_digital_pins()
        self._setup_magtag()
        self._handle_alarms()
        self._setup_sensors()
        self._check_battery()
        self._load_fonts()
        self._setup_labels()
        self.initialized = True
        print('Setup complete.')

    def _setup_alarms(self) -> None:
        """
        Create the necessary alarms needed to wake back up from a deep sleep.
        """
        if self._debug:
            print('Setting up alarms... ', end='')
        # Set up alarms for the different buttons and timer
        self.pin_alarm = alarm.pin.PinAlarm(board.D14, value=False)
        self.time_alarm = alarm.time.TimeAlarm(monotonic_time=int(time.monotonic()) + REFRESH_TIME)
        if self._debug:
            print('OK')

    def _setup_digital_pins(self) -> None:
        if isinstance(alarm.wake_alarm, alarm.pin.PinAlarm):
            return

        # Set up I2C
        if not self._i2c:
            self._i2c = board.I2C()
        if self._debug:
            print('Setting up standby digital pin for PM25... ', end='')
        self._pm25_standby_pin = digitalio.DigitalInOut(PM25_STANDBY_PIN)
        self._pm25_standby_pin.switch_to_output()
        time.sleep(0.1)
        self._pm25_standby_pin.value = True
        if self._debug:
            print('OK')
            print('Waiting for sensor to warm up... ', end='')
        else:
            print(f'Waiting {PM25_SENSOR_WARMUP_SECONDS} seconds for PM25 sensor.')
        time.sleep(PM25_SENSOR_WARMUP_SECONDS or 30)
        if self._debug:
            print('OK')

    def _handle_alarms(self) -> None:
        """
        Determine if alarms have been triggered. If so, process them.
        """
        debug_messages = []
        if self._debug:
            print('Handle alarms... ', end='')

        # Check to see if the wake alarm is a pin alarm
        if isinstance(alarm.wake_alarm, alarm.pin.PinAlarm):
            self._pin = alarm.wake_alarm.pin
            debug_messages.append(str(self._pin))
            # Check what the light level is before we blind someone
            neopixel_brightness = 0.25
            if self._magtag.peripherals.light < 700:
                neopixel_brightness = 0.5
            if self._magtag.peripherals.light < 1500:
                neopixel_brightness = 0.75
            if self._magtag.peripherals.light < 2000:
                neopixel_brightness = 1
            debug_messages.append(f'brightness = {neopixel_brightness}')
            self._magtag.peripherals.neopixel_disable = False
            self._magtag.peripherals.neopixels.brightness = neopixel_brightness
            self._magtag.peripherals.neopixels.fill((255, 255, 255))
            self._magtag.peripherals.neopixels.show()
            if self._debug:
                print('OK')
                print('\n'.join(debug_messages))
            time.sleep(6)
            self.deep_sleep()
        elif isinstance(alarm.wake_alarm, alarm.time.TimeAlarm):
            # If we have received a time alarm, proceed with boot.
            for i in range(4):
                time.sleep(0.5)
                self._magtag.peripherals.neopixels[0] = (255, 255, 0)
                time.sleep(0.25)
                self._magtag.peripherals.neopixels[0] = (0, 0, 0)
        elif not alarm.wake_alarm:
            self._magtag.set_background(0x666666)
            board.DISPLAY.refresh()

        if self._debug:
            print('OK')

    def _check_battery(self) -> None:
        """
        Check the battery level, if it's low, play a tone.
        """
        if self._magtag.peripherals.battery < 3.5:
            print(f'Battery voltage at {self._magtag.peripherals.battery}, need to charge.')
            for i in range(3):
                self._magtag.peripherals.play_tone(2600, 0.1)
                time.sleep(0.2)

    def _setup_sensors(self) -> None:
        """
        Set up connections to our sensors.
        """
        if self._debug:
            print('Connect PM25 sensor via I2C... ', end='')
        else:
            print('Set up sensors.')
        # Set up PM25_I2C sensor
        self._pm25 = PM25_I2C(self._i2c, None)
        if self._debug:
            print('OK')
        if self._debug:
            print('Connect SHT31D sensor via I2C... ', end='')
        self._sht31d = adafruit_sht31d.SHT31D(self._i2c)
        if self._debug:
            print('OK')

    def _setup_magtag(self) -> None:
        """
        Set up the MagTag itself. This is the heart of our system.
        """
        # Create a new MagTag object
        self._magtag = MagTag(default_bg=0xFFFFFF, debug=self._debug or self._debug_display)
        # noinspection PyProtectedMember
        self._secrets = self._magtag.network._secrets
        # Default configuration for MagTag
        self._magtag.peripherals.neopixels.auto_write = True
        self._magtag.peripherals.neopixels.brightness = 255
        # Set up the Real Time Clock
        self._rtc = rtc.RTC()
        self._magtag.peripherals.neopixels[0] = (0, 40, 0)
        print(f'Battery at {self._magtag.peripherals.battery} volt.')

    def _load_fonts(self) -> None:
        """
        Load fonts from the CIRCUITPY drive.
        """
        self._label_font = bitmap_font.load_font("fonts/FredokaOne-Regular-18.pcf")
        self._numbers_font = bitmap_font.load_font("fonts/FredokaOne-Regular-46.pcf")
        self._stats_font = bitmap_font.load_font("fonts/Tamzen-9.pcf")

    def _setup_labels(self) -> None:
        """
        Create the labels that we use to display information on the screen.
        """
        self._pm10value_label = label.Label(
            self._numbers_font,
            color=0x000000,
            anchor_point=(0.5, 0.5),
            anchored_position=(53, 35),
        )
        self._pm10label_label = label.Label(
            self._label_font,
            color=0x666666,
            text="PM 1.0",
            anchor_point=(0.5, 0.5),
            anchored_position=(53, 70),
        )
        self._pm25value_label = label.Label(
            self._numbers_font,
            color=0x000000,
            anchor_point=(0.5, 0.5),
            anchored_position=(148, 35),
        )
        self._pm25label_label = label.Label(
            self._label_font,
            color=0x666666,
            text="PM 2.5",
            anchor_point=(0.5, 0.5),
            anchored_position=(148, 70),
        )
        self._pm100value_label = label.Label(
            self._numbers_font,
            color=0x000000,
            anchor_point=(0.5, 0.5),
            anchored_position=(243, 35),
        )
        self._pm100label_label = label.Label(
            self._label_font,
            color=0x666666,
            text="PM 10",
            anchor_point=(0.5, 0.5),
            anchored_position=(243, 70),
        )
        self._stats_label = label.Label(
            self._stats_font,
            color=0x000000,
            anchor_point=(0, 0),
            anchored_position=(12, 100),
        )
        self._magtag.splash.append(self._pm10value_label)
        self._magtag.splash.append(self._pm10label_label)
        self._magtag.splash.append(self._pm25value_label)
        self._magtag.splash.append(self._pm25label_label)
        self._magtag.splash.append(self._pm100value_label)
        self._magtag.splash.append(self._pm100label_label)
        self._magtag.splash.append(self._stats_label)
        if gc.isenabled():
            gc.collect()

    def deep_sleep(self, backoff: bool = False) -> None:
        """
        Power down non-critical systems and enter deep sleep.

        Args:
            backoff: if True, then we use an exponential backoff strategy
        """
        self._magtag.peripherals.neopixel_disable = True
        self._magtag.peripherals.speaker_disable = True
        if not isinstance(alarm.wake_alarm, alarm.pin.PinAlarm):
            self._pm25_standby_pin.value = False
        if backoff:
            sleep_length = alarm.sleep_memory[SLEEP_MEMORY_SLOT_BACKOFF]
            print(f'ERROR, EXPONENTIAL BACKOFF: Sleeping for {sleep_length} seconds.')
            backoff_alarm = alarm.time.TimeAlarm(monotonic_time=int(time.monotonic()) + sleep_length)
            alarm.exit_and_deep_sleep_until_alarms(backoff_alarm)
        print(f'Sleeping for {REFRESH_TIME:d} seconds')
        if gc.isenabled():
            gc.collect()
        alarm.exit_and_deep_sleep_until_alarms(self.pin_alarm, self.time_alarm)

    def deep_sleep_exponential_backoff(self) -> None:
        """
        Something's not right. Let's sleep for a while.
        If something's still wrong after we sleep, we'll sleep even longer.
        Like, exponentially so.
        """
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

    def connect(self) -> None:
        """
        Connect to the WiFi network.
        """
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
        if gc.isenabled():
            gc.collect()

    def get_pm25_measurements(self) -> []:
        """
        Get a number of measurements over time to get an average from the instrument.
        """
        measurements = []
        failed_readings = 0
        if self._debug:
            print(f'Taking {self._num_samples} measurement{"s" if self._num_samples > 1 else ""} from PM25 sensor... ',
                  end='')
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

        if gc.isenabled():
            gc.collect()

        return measurements

    def get_pm25_averages(self, measurements: []):
        """
        Get the average from the collected measurements.
        """
        pm25_averages = {}
        if measurements and len(measurements):
            columns = measurements[0].keys()
            for column in columns:
                feed_key = column.replace(' ', '-')
                pm25_averages[feed_key] = sum(i[column] for i in measurements) / len(measurements)
                if not self._debug:
                    self.push_to_io(feed_key=f'air-quality-office.{feed_key}', metadata={},
                                    data=pm25_averages[feed_key], precision=2)
        if gc.isenabled():
            gc.collect()
        return pm25_averages

    def push_to_io(self, feed_key: str, metadata: any, data: any, precision=0) -> bool:
        """Push data to Adafruit IO.

        Includes rudimentary protection against API failures.

        Args:
            feed_key:
            metadata:
            data:
            precision:

        Returns:
            True or False indicate success.
        """
        failed_push = False
        if self._debug:
            print('Cowardly refusing to push data to Adafruit IO in debug mode.')
        else:
            print(f'Push {feed_key} to Adafruit IO... ', end='')
            for x in range(3):
                try:
                    # TODO: Fix neopixels aren't working when pushing to feed
                    #       For some reason this isn't working while the MagTag is also pushing out
                    #       stats to the Adafruit IO API. Gotta be a way to have that light blink.
                    self._magtag.peripherals.neopixels[1] = (255, 0, 255)
                    time.sleep(0.25)
                    self._magtag.peripherals.neopixels[1] = (0, 255, 255)
                    self._magtag.push_to_io(feed_key=feed_key, metadata=metadata, data=data, precision=precision)
                    failed_push = False
                    break
                except RuntimeError:
                    failed_push = True
                    time.sleep(1)
                    continue
            print('FAIL' if failed_push else 'OK')
        return failed_push

    def get_sht31d_readings(self):
        try:
            self._temperature = self._sht31d.temperature
            self._relative_humidity = self._sht31d.relative_humidity
        except OSError:
            return False

        success = True
        success & self.push_to_io(
            feed_key='air-quality-office.temperature-c',
            metadata={},
            data=self._temperature,
            precision=1,
        )
        success & self.push_to_io(
            feed_key='air-quality-office.relative-humidity',
            metadata={},
            data=self._relative_humidity,
            precision=1,
        )
        return success

    def process_events(self) -> None:
        """
        Process events. Call this from the main loop of your `code.py` file.
        """
        self._magtag.set_background(0xFFFFFF)

        self.get_sht31d_readings()
        self._magtag.peripherals.neopixels[1] = (0, 80, 0)
        pm25_averages = self.get_pm25_averages(self.get_pm25_measurements())
        self._magtag.peripherals.neopixels[1] = (0, 80, 0)

        self._pm10value_label.text = f'{pm25_averages["pm10-standard"]:.0f}'
        self._pm25value_label.text = f'{pm25_averages["pm25-standard"]:.0f}'
        self._pm100value_label.text = f'{pm25_averages["pm100-standard"]:.0f}'

        stats = f'0.3µm/0.1L: {pm25_averages["particles-03um"]:.1f}, 0.5µm/0.1L: {pm25_averages["particles-05um"]:.1f}, 1.0µm/0.1L: {pm25_averages["particles-10um"]:.1f}\n'
        stats += f'2.5µm/0.1L: {pm25_averages["particles-25um"]:.1f}, 5.0µm/0.1L: {pm25_averages["particles-50um"]:.1f}, 10µm/0.1L: {pm25_averages["particles-100um"]:.1f}'

        self._stats_label.text = stats

        board.DISPLAY.show(self._magtag.splash)
        board.DISPLAY.refresh()

        if self._debug:
            from debug import print_particle_values
            print_particle_values(pm25_averages)

        clear_backoff()
        self.deep_sleep()
