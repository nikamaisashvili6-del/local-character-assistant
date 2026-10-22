#!/bin/bash
# desc: what song is playing on Spotify right now
# keywords: what, current, currently, now, name, who, this, which
# confirm: no
playerctl -p spotify metadata --format '{{status}}: {{artist}} - {{title}} (album: {{album}})' 2>/dev/null || echo "Spotify isn't running"
