#!/bin/bash
# desc: set the system volume: a number (0-100), up/louder, down/quieter, mute, unmute
# keywords: set, up, down, mute, unmute, turn, max, percent
# confirm: no
# args: yes
t=$(echo "$1" | tr 'A-Z' 'a-z'); dev=@DEFAULT_AUDIO_SINK@
n=$(echo "$t" | grep -oE '[0-9]+' | head -1)
if   echo "$t" | grep -qw unmute;                 then wpctl set-mute $dev 0
elif echo "$t" | grep -qw mute;                   then wpctl set-mute $dev 1
elif [ -n "$n" ];                                 then wpctl set-volume $dev "$((n>100?100:n))%"
elif echo "$t" | grep -qwE 'max|full';            then wpctl set-volume $dev 100%
elif echo "$t" | grep -qwE 'up|louder|raise';     then wpctl set-volume -l 1.0 $dev 10%+
elif echo "$t" | grep -qwE 'down|quieter|lower';  then wpctl set-volume $dev 10%-
fi
wpctl get-volume $dev | awk '{printf "volume: %d%%%s\n", $2*100, ($3?" (muted)":"")}'
