# SPDX-FileCopyrightText: 2021 Torgny Bjers
#
# SPDX-License-Identifier: Unlicense
from aq_magtag import AqMagTag

DEBUG = False
DEBUG_DISPLAY = False

aq = AqMagTag(debug=DEBUG, debug_display=DEBUG_DISPLAY)
aq.setup()
aq.connect()

while True:
    aq.process_events()
