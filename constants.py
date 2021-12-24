# SPDX-FileCopyrightText: 2021 Torgny Bjers
#
# SPDX-License-Identifier: Unlicense
import board
import microcontroller

# Amount of time to wait between refreshing the sensor data
REFRESH_TIME = 10*60

# Constants used in sleep_memory to indicate error
SLEEP_MEMORY_SLOT_BACKOFF = 1
SLEEP_MEMORY_SLOT_BACKOFF_TIMES = 2

# Shortest time we will wait for backoff
MINIMUM_BACKOFF = 15

# Maximum length of backoff in seconds (5 minutes)
MAXIMUM_BACKOFF = 60 * 5

# Maximum number of backoff iterations
MAX_BACKOFF_COUNT = 60 / 5

# Pin used to control standby of the PM25 module
PM25_STANDBY_PIN: microcontroller.Pin = board.D10

# Duration of wait for PM25 sensor to spin up
PM25_SENSOR_WARMUP_SECONDS = 30
