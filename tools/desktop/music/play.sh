#!/bin/bash
# desc: play or resume Spotify music (starts Spotify if closed); "play X" opens a search for X
# keywords: play, resume, start, turn, put, unpause, change, switch, listen, queue
# confirm: no
# args: yes
what=$(echo "$1" | tr 'A-Z' 'a-z' | sed -E 's/\b(play|resume|start|turn|put|on|some|the|my|music|spotify|song|songs|please|unpause|me|a|change|switch|to|listen|queue|in|by)\b//g' | xargs)
# "play that song" / "play it": no real name, so just resume playback
[[ "$what" =~ ^(that|it|this|something|anything)?$ ]] && what=""
if ! playerctl -p spotify status &>/dev/null; then       # Spotify not running yet
  (spotify &>/dev/null &) ; sleep 6
fi
if [ -n "$what" ]; then
  xdg-open "spotify:search:$what" &>/dev/null            # Spotify jumps to the search
  echo "Spotify search for '$what' is now open on screen. NOTHING is playing yet: the user has to click a track."
else
  playerctl -p spotify play && sleep 1
  echo "playing: $(playerctl -p spotify metadata --format '{{artist}} - {{title}}' 2>/dev/null)"
fi
