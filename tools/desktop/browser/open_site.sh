#!/bin/bash
# desc: open a website: a URL, or a known one (github, gmail, youtube music, wikipedia)
# keywords: open, go, site, website, url, link, page, github, gmail, wikipedia
# confirm: no
# args: yes
. "$(dirname "$0")/_browser.sh"
t=$(echo "$1" | tr 'A-Z' 'a-z')
url=$(echo "$1" | grep -oE '(https?://)?[a-z0-9.-]+\.[a-z]{2,}(/[^ ]*)?' | head -1)
case "$t" in
  *github*) url="https://github.com" ;;
  *gmail*)  url="https://mail.google.com" ;;
  *wikipedia*) url="https://en.wikipedia.org" ;;
  *"youtube music"*) url="https://music.youtube.com" ;;
esac
[ -z "$url" ] && { echo "no website in that sentence"; exit 0; }
[[ "$url" != http* ]] && url="https://$url"
$(browser "$1") "$url" &>/dev/null &
echo "opened $url in $(browser "$1")"
