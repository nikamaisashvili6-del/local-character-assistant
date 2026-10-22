#!/bin/bash
# desc: skip to the next Spotify track
# keywords: next, skip
# confirm: no
playerctl -p spotify next 2>/dev/null && sleep 1 && echo "now: $(playerctl -p spotify metadata --format '{{artist}} - {{title}}')" || echo "Spotify isn't running"
