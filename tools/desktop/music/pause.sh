#!/bin/bash
# desc: pause / stop the Spotify music
# keywords: pause, stop, off, kill, shut, silence, enough
# confirm: no
playerctl -p spotify pause 2>/dev/null && echo "music paused" || echo "Spotify isn't running"
