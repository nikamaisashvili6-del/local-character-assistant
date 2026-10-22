#!/bin/bash
# desc: open a desktop app: files, code editor, terminal, mail, obsidian, settings, calculator, steam, discord, spotify, browser
# keywords: vault, files, file, manager, folder, folders, code, vscode, editor, terminal, thunderbird, mail, email, obsidian, settings, calculator, steam, discord, spotify
# confirm: no
# args: yes
#
# word in your sentence -> candidate .desktop launcher names. gtk-launch starts
# an app the same way the app menu does. Different distros name launchers
# differently (snap, flatpak, deb), so each word lists a few candidates and the
# first one that exists wins. Add your own apps to the table.
t=" $(echo "$1" | tr 'A-Z' 'a-z') "
declare -A APPS=(
  [file]="org.gnome.Nautilus nautilus thunar org.kde.dolphin"
  [folder]="org.gnome.Nautilus nautilus thunar org.kde.dolphin"
  [manager]="org.gnome.Nautilus nautilus thunar org.kde.dolphin"
  [code]="code code_code com.visualstudio.code"
  [vscode]="code code_code com.visualstudio.code"
  [editor]="code code_code org.gnome.TextEditor"
  [terminal]="org.gnome.Ptyxis org.gnome.Terminal org.kde.konsole xfce4-terminal"
  [thunderbird]="thunderbird thunderbird_thunderbird org.mozilla.Thunderbird"
  [mail]="thunderbird thunderbird_thunderbird org.mozilla.Thunderbird"
  [email]="thunderbird thunderbird_thunderbird org.mozilla.Thunderbird"
  [obsidian]="obsidian obsidian_obsidian md.obsidian.Obsidian"
  [vault]="obsidian obsidian_obsidian md.obsidian.Obsidian"
  [settings]="org.gnome.Settings gnome-control-center systemsettings"
  [calculator]="org.gnome.Calculator gnome-calculator org.kde.kcalc"
  [steam]="steam com.valvesoftware.Steam"
  [discord]="discord com.discordapp.Discord"
  [spotify]="spotify spotify_spotify com.spotify.Client"
)
opened=""
for word in "${!APPS[@]}"; do
  [[ "$t" == *" $word"* ]] || continue
  for id in ${APPS[$word]}; do
    [[ "$opened" == *"$id"* ]] && break                   # already opened this one
    if gtk-launch "$id" &>/dev/null; then                  # fails fast if not installed
      opened+="$id "; break
    fi
  done
done
[ -n "$opened" ] && echo "opened: $opened" || echo "didn't recognise the app, or it isn't installed"
