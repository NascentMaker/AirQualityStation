# SPDX-FileCopyrightText: 2021 Torgny Bjers
#
# SPDX-License-Identifier: Unlicense

# Amount of time to wait between refreshing the sensor data, in minutes
REFRESH_TIME = 3

# Constants used in sleep_memory to indicate error
SLEEP_MEMORY_SLOT_PIN_ALARM = 0
SLEEP_MEMORY_SLOT_BACKOFF = 1
SLEEP_MEMORY_SLOT_BACKOFF_TIMES = 2

# Shortest time we will wait for backoff
MINIMUM_BACKOFF = 15

# Maximum length of backoff in seconds (5 minutes)
MAXIMUM_BACKOFF = 60*5

MAX_BACKOFF_COUNT = 60/5
