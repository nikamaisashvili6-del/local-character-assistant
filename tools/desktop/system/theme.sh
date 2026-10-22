#!/bin/bash
# desc: switch the desktop between dark mode and light mode
# keywords: dark, light, theme, mode
# confirm: no
# args: yes
if echo "$1" | grep -qi light; then s=default; else s=prefer-dark; fi
gsettings set org.gnome.desktop.interface color-scheme "$s" && echo "theme: $s"
