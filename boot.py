# SPDX-FileCopyrightText: 2021 Torgny Bjers
#
# SPDX-License-Identifier: Unlicense
import alarm
import board
from constants import SLEEP_MEMORY_SLOT_PIN_ALARM

# Handle pin alarms and store the specific button
if alarm.wake_alarm:
    if isinstance(alarm.wake_alarm, alarm.pin.PinAlarm):
        pin_name = f'{alarm.wake_alarm.pin}'.split('.')[1]
        print(f'Pin alarm from {pin_name}.')
        alarm.sleep_memory[SLEEP_MEMORY_SLOT_PIN_ALARM] = dir(board).index(pin_name)

print('Boot complete.')
