#!/bin/bash
# desc: go back to the previous Spotify track
# keywords: previous, back, last, again, replay
# confirm: no
playerctl -p spotify previous 2>/dev/null && sleep 1 && echo "now: $(playerctl -p spotify metadata --format '{{artist}} - {{title}}')" || echo "Spotify isn't running"
