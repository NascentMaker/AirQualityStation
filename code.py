# SPDX-FileCopyrightText: 2021 Torgny Bjers
#
# SPDX-License-Identifier: Unlicense
import time

import alarm
import board
import busio
import rtc
from adafruit_bitmap_font import bitmap_font
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

TESTING = False
reset_pin = None
num_samples = 1 if TESTING else 10

i2c = busio.I2C(board.SCL, board.SDA, frequency=100000)
print('Connect PM25 sensor via I2C... ', end='')
pm25 = PM25_I2C(i2c, reset_pin)
print('OK')


def deep_sleep(backoff: bool = False) -> None:
    magtag.peripherals.neopixel_disable = True
    magtag.peripherals.speaker_disable = True
    magtag.peripherals.deinit()
    i2c.deinit()
    if backoff:
        sleep_length = alarm.sleep_memory[SLEEP_MEMORY_SLOT_BACKOFF]
        print(f'ERROR, EXPONENTIAL BACKOFF: Sleeping for {sleep_length} seconds.')
        backoff_alarm = alarm.time.TimeAlarm(monotonic_time=int(time.monotonic()) + sleep_length)
        alarm.exit_and_deep_sleep_until_alarms(backoff_alarm)
    print(f'Sleeping for {REFRESH_TIME:d} minutes')
    alarm.exit_and_deep_sleep_until_alarms(pin_alarm, time_alarm)


def deep_sleep_exponential_backoff() -> None:
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
    deep_sleep(backoff=True)


def clear_backoff() -> None:
    alarm.sleep_memory[SLEEP_MEMORY_SLOT_BACKOFF] = 0
    alarm.sleep_memory[SLEEP_MEMORY_SLOT_BACKOFF_TIMES] = 0


# Set up alarms for the different buttons and timer
pin_alarm = alarm.pin.PinAlarm(board.D14, value=False)
time_alarm = alarm.time.TimeAlarm(monotonic_time=int(time.monotonic()) + (REFRESH_TIME * 60))

# Create a new MagTag object
magtag = MagTag(default_bg=0xFFFFFF, debug=True)
magtag.peripherals.neopixels.auto_write = True
magtag.peripherals.neopixels.brightness = 255
r = rtc.RTC()

received_pin_alarm = False
pin = None

if alarm.sleep_memory[SLEEP_MEMORY_SLOT_PIN_ALARM]:
    received_pin_alarm = True
    # attempt to decode the pin
    pin = getattr(board, dir(board)[alarm.sleep_memory[SLEEP_MEMORY_SLOT_PIN_ALARM]])
    alarm.sleep_memory[SLEEP_MEMORY_SLOT_PIN_ALARM] = False

if isinstance(alarm.wake_alarm, alarm.pin.PinAlarm):
    received_pin_alarm = True
    pin = alarm.wake_alarm.pin

# Handle pin alarm
if received_pin_alarm:
    print(f'Light level: {magtag.peripherals.light}')
    # Check what the light level is before we blind someone
    NEOPIXEL_BRIGHTNESS = 0.25
    if magtag.peripherals.light < 700:
        NEOPIXEL_BRIGHTNESS = 0.5
    if magtag.peripherals.light < 1500:
        NEOPIXEL_BRIGHTNESS = 0.75
    if magtag.peripherals.light < 2000:
        NEOPIXEL_BRIGHTNESS = 1
    magtag.peripherals.neopixel_disable = False
    magtag.peripherals.neopixels.brightness = NEOPIXEL_BRIGHTNESS
    magtag.peripherals.neopixels.fill((255, 255, 255))
    magtag.peripherals.neopixels.show()
    time.sleep(6)
    deep_sleep()
elif alarm.wake_alarm:
    for i in range(4):
        time.sleep(0.5)
        magtag.peripherals.neopixels[0] = (255, 255, 0)
        time.sleep(0.25)
        magtag.peripherals.neopixels[0] = (0, 0, 0)

magtag.peripherals.neopixels[0] = (0, 40, 0)

# noinspection PyProtectedMember
secrets = magtag.network._secrets

if magtag.peripherals.battery < 3.5:
    print("I need to be charged")
    for i in range(3):
        magtag.peripherals.play_tone(2600, 0.1)
        time.sleep(0.2)

connect_tries = 0
connected = False

label_font = bitmap_font.load_font("fonts/FredokaOne-Regular-18.pcf")
numbers_font = bitmap_font.load_font("fonts/FredokaOne-Regular-46.pcf")
stats_font = bitmap_font.load_font("fonts/Tamzen-9.pcf")

pm10value_label = label.Label(numbers_font, color=0x000000, anchor_point=(0.5, 0.5), anchored_position=(53, 35))
pm10label_label = label.Label(label_font, color=0x666666, text="PM 1.0", anchor_point=(0.5, 0.5), anchored_position=(53, 70))
magtag.splash.append(pm10value_label)
magtag.splash.append(pm10label_label)

pm25value_label = label.Label(numbers_font, color=0x000000, anchor_point=(0.5, 0.5), anchored_position=(148, 35))
pm25label_label = label.Label(label_font, color=0x666666, text="PM 2.5", anchor_point=(0.5, 0.5), anchored_position=(148, 70))
magtag.splash.append(pm25value_label)
magtag.splash.append(pm25label_label)

pm100value_label = label.Label(numbers_font, color=0x000000, anchor_point=(0.5, 0.5), anchored_position=(243, 35))
pm100label_label = label.Label(label_font, color=0x666666, text="PM 10", anchor_point=(0.5, 0.5), anchored_position=(243, 70))
magtag.splash.append(pm100value_label)
magtag.splash.append(pm100label_label)

stats_label = label.Label(stats_font, color=0x000000, anchor_point=(0, 0), anchored_position=(12, 100))
magtag.splash.append(stats_label)

if TESTING:
    import random
    magtag.peripherals.neopixels[3] = (255, 0, 0)
    random.seed(int(time.monotonic()))
    pm10value_label.text = str(random.randint(0, 300))
    pm25value_label.text = str(random.randint(0, 14))
    pm100value_label.text = str(random.randint(1, 4))
    stats_label.text = f'0.3µm/0.1L: {random.randint(120, 500)}'
    board.DISPLAY.show(magtag.splash)
    board.DISPLAY.refresh()
    while True:
        pass

magtag.peripherals.neopixels[0] = (70, 70, 10)

while connect_tries <= 5:
    try:
        magtag.network.connect()
        if magtag.network.enabled:
            connected = True
            break
    except ConnectionError:
        print("Cannot connect to network. Retrying...")
        time.sleep(3)
        connect_tries += 1

if not connected:
    print("Cannot connect to network. Sleeping for five minutes.")
    for i in range(5):
        magtag.peripherals.play_tone(1200, 0.05)
        time.sleep(0.09)
    magtag.exit_and_deep_sleep(60*5)
else:
    print("Connection established.")

magtag.peripherals.neopixels[0] = (0, 255, 0)

time.sleep(3)

magtag.peripherals.neopixels[0] = 0

while True:
    measurements = []
    failed_readings = 0

    print(f'Taking {num_samples} measurement{"s" if num_samples > 1 else ""} from PM25 sensor... ', end='')
    for c in range(num_samples):
        if failed_readings > 3:
            magtag.peripherals.neopixels[0] = (255, 0, 0)
            deep_sleep_exponential_backoff()
        magtag.peripherals.neopixels[0] = (255, 255, 0)
        time.sleep(0.25)
        try:
            measurements.append(pm25.read())
            magtag.peripherals.neopixels[0] = (0, 255, 0)
            time.sleep(0.25)
        except RuntimeError:
            print('Unable to read from sensor, retrying...')
            failed_readings += 1
            magtag.peripherals.neopixels[0] = (255, 0, 0)
            continue

    print("OK")

    totals = {}

    magtag.peripherals.neopixels[0] = (0, 80, 0)

    if measurements and len(measurements):
        columns = measurements[0].keys()
        for column in columns:
            magtag.peripherals.neopixels[1] = (255, 0, 255)
            time.sleep(0.25)
            feed_key = column.replace(' ', '-')
            totals[feed_key] = sum(i[column] for i in measurements) / len(measurements)
            if not TESTING:
                print(f'Push {feed_key} to Adafruit IO... ', end='')
                # TODO: Fix neopixels aren't working when pushing to feed
                #       For some reason this isn't working while the MagTag is also pushing out
                #       stats to the Adafruit IO API. Gotta be a way to have that light blink.
                magtag.peripherals.neopixels[1] = (0, 255, 255)
                magtag.push_to_io(feed_key=feed_key, metadata={}, data=totals[feed_key], precision=2)
                print('OK')

    pm10value_label.text = f'{totals["pm10-standard"]:.0f}'
    pm25value_label.text = f'{totals["pm25-standard"]:.0f}'
    pm100value_label.text = f'{totals["pm100-standard"]:.0f}'

    # pm25.i2c_device.write()

    magtag.peripherals.neopixels[1] = (0, 80, 0)

    print()
    print("Concentration Units (standard)")
    print("---------------------------------------")
    print(
        "PM 1.0: %d\tPM 2.5: %d\tPM 10: %d"
        % (totals["pm10-standard"], totals["pm25-standard"], totals["pm100-standard"])
    )
    print("Concentration Units (environmental)")
    print("---------------------------------------")
    print(
        "PM 1.0: %d\tPM 2.5: %d\tPM 10: %d"
        % (totals["pm10-env"], totals["pm25-env"], totals["pm100-env"])
    )
    print("---------------------------------------")
    print("Particles > 0.3µm / 0.1L air:", totals["particles-03um"])
    print("Particles > 0.5µm / 0.1L air:", totals["particles-05um"])
    print("Particles > 1.0µm / 0.1L air:", totals["particles-10um"])
    print("Particles > 2.5µm / 0.1L air:", totals["particles-25um"])
    print("Particles > 5.0µm / 0.1L air:", totals["particles-50um"])
    print("Particles > 10 µm / 0.1L air:", totals["particles-100um"])
    print("---------------------------------------")

    stats = f'0.3µm/0.1L: {totals["particles-03um"]:.1f}, 0.5µm/0.1L: {totals["particles-05um"]:.1f}, 1.0µm/0.1L: {totals["particles-10um"]:.1f}\n'
    stats += f'2.5µm/0.1L: {totals["particles-25um"]:.1f}, 5.0µm/0.1L: {totals["particles-50um"]:.1f}, 10µm/0.1L: {totals["particles-100um"]:.1f}'

    stats_label.text = stats

    board.DISPLAY.show(magtag.splash)
    board.DISPLAY.refresh()

    clear_backoff()
    deep_sleep()
