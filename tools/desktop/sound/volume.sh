#!/bin/bash
# desc: set the volume: a number (0-100), up/louder, down/quieter, mute, unmute ("spotify volume" = Spotify's own slider)
# keywords: set, up, down, mute, unmute, turn, max, percent, increase, decrease, raise, lower, louder, quieter
# confirm: no
# args: yes
t=$(echo "$1" | tr 'A-Z' 'a-z'); dev=@DEFAULT_AUDIO_SINK@
# "spotify volume up": Spotify's own volume (MPRIS), not the system one
if echo "$t" | grep -qw spotify; then
  if   echo "$t" | grep -qwE 'up|louder|raise|increase|max|full'; then playerctl -p spotify volume 0.1+
  elif echo "$t" | grep -qwE 'down|quieter|lower|decrease';      then playerctl -p spotify volume 0.1-
  fi
  v=$(playerctl -p spotify volume 2>/dev/null) || { echo "Spotify isn't running"; exit 0; }
  awk -v v="$v" 'BEGIN{printf "spotify volume: %d%%\n", v*100}'; exit 0
fi
n=$(echo "$t" | grep -oE '[0-9]+' | head -1)
if   echo "$t" | grep -qw unmute;                 then wpctl set-mute $dev 0
elif echo "$t" | grep -qw mute;                   then wpctl set-mute $dev 1
elif [ -n "$n" ];                                 then wpctl set-volume $dev "$((n>100?100:n))%"
elif echo "$t" | grep -qwE 'max|full';            then wpctl set-volume $dev 100%
elif echo "$t" | grep -qwE 'up|louder|raise|increase';     then wpctl set-volume -l 1.0 $dev 10%+
elif echo "$t" | grep -qwE 'down|quieter|lower|decrease';  then wpctl set-volume $dev 10%-
fi
wpctl get-volume $dev | awk '{printf "volume: %d%%%s\n", $2*100, ($3?" (muted)":"")}'
