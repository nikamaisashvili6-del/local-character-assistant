#!/usr/bin/env python3
# desc: set a reminder or alarm: "in 10 minutes to X", "at 9", "at 21:30 to X"
# keywords: remind, reminder, alarm, set, timer, wake, in, at
# confirm: no
# args: yes
#
# Uses a systemd USER timer, so it fires even if the assistant is closed (not
# after a reboot). When it fires: a desktop notification + an alarm sound x3.
import re, subprocess, sys
from datetime import datetime, timedelta

t = sys.argv[1].lower() if len(sys.argv) > 1 else ""

# WHEN: "in 10 min", "in 2 hours", or "at 9", "at 21:30", "at 9pm"
when = None
m = re.search(r"\bin (\d+)\s*(s|sec|second|m|min|minute|h|hr|hour)s?\b", t)
if m:
    n, unit = int(m.group(1)), m.group(2)[0]
    when = datetime.now() + timedelta(**{{"s": "seconds", "m": "minutes", "h": "hours"}[unit]: n})
m2 = re.search(r"\bat (\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", t)
if not when and m2:
    h, mi, ap = int(m2.group(1)), int(m2.group(2) or 0), m2.group(3)
    if ap == "pm" and h < 12: h += 12
    if ap == "am" and h == 12: h = 0
    when = datetime.now().replace(hour=h, minute=mi, second=0, microsecond=0)
    if when <= datetime.now():
        when += timedelta(days=1)                   # "at 9" when it's 10 = tomorrow
if not when:
    print("couldn't find a time (try 'in 10 minutes' or 'at 21:30')"); sys.exit()

# WHAT: everything after " to ", else a default
what = t.split(" to ", 1)[1].strip() if " to " in t else "time's up"

sound = "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"
action = (f"notify-send -u critical 'Reminder' {what!r}; "
          f"for i in 1 2 3; do pw-play {sound}; done")
unit = f"assistant-alarm-{when:%m%d-%H%M%S}"
subprocess.run(["systemd-run", "--user", f"--unit={unit}", f"--on-calendar={when:%Y-%m-%d %H:%M:%S}",
                "--timer-property=AccuracySec=1s", "/bin/bash", "-c", action],
               capture_output=True, check=True)
print(f"reminder set for {when:%a %H:%M}: {what}")
