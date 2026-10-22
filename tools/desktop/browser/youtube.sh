#!/bin/bash
# desc: open YouTube, or search YouTube for something
# keywords: youtube, video, videos, watch, yt
# confirm: no
# args: yes
. "$(dirname "$0")/_browser.sh"
q=$(strip "$1" "youtube|video|videos|watch|yt|on|some")
url="https://www.youtube.com"
[ -n "$q" ] && url="https://www.youtube.com/results?search_query=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "$q")"
$(browser "$1") "$url" &>/dev/null &
echo "opened YouTube${q:+ search for '$q'}"
