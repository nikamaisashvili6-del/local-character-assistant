#!/bin/bash
# desc: search Google for something in the browser
# keywords: google, search, look, lookup
# confirm: no
# args: yes
. "$(dirname "$0")/_browser.sh"
q=$(strip "$1" "look|lookup|googling")
[ -z "$q" ] && { $(browser "$1") "https://www.google.com" &>/dev/null & echo "opened Google"; exit; }
$(browser "$1") "https://www.google.com/search?q=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "$q")" &>/dev/null &
echo "searched Google for '$q' in $(browser "$1")"
