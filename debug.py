import random
import time


def print_particle_values(totals):
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


def test_display_layout(board, magtag, pm10value_label, pm25value_label, pm100value_label, stats_label):
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
