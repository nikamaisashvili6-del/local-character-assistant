#!/bin/bash
# desc: list or cancel reminders/alarms, or stop a ringing alarm
# keywords: list, cancel, stop, clear, delete, remove, show, what, pending
# confirm: no
# args: yes
if echo "$1" | grep -qiE 'cancel|stop|clear|delete|remove'; then
  systemctl --user stop 'assistant-alarm-*' 2>/dev/null; pkill -f 'pw-play .*alarm-clock' 2>/dev/null
  echo "all reminders cancelled / alarm stopped"
else
  systemctl --user list-timers 'assistant-alarm-*' --no-legend | awk '$1!="-"{print "  " $1, $2, $3}' | grep . || echo "no reminders set"
fi
