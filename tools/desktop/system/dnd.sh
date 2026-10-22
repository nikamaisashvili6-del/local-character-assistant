#!/bin/bash
# desc: do-not-disturb on or off (hide notification popups)
# keywords: disturb, dnd, notifications, quiet
# confirm: no
# args: yes
if echo "$1" | grep -qiE '\boff\b|enable notif|turn on notif|show'; then v=true; else v=false; fi
gsettings set org.gnome.desktop.notifications show-banners $v
[ $v = false ] && echo "do not disturb ON" || echo "do not disturb OFF"
