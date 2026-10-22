#!/bin/bash
# desc: search your markdown notes (e.g. an Obsidian vault) for words; returns matching lines
# keywords: search, find, look, wrote, written, remember, about
# confirm: no
# args: yes
#
# $1 = your sentence, e.g. "search my notes for punk". We drop the command
# words and filler, keep the rest as search terms, and grep every .md under
# $NOTES_DIR (set in config.toml; the router passes it in).
dir="${NOTES_DIR:-$HOME/Documents}"
terms=$(echo "$1" | tr 'A-Z' 'a-z' | tr -cs 'a-z0-9' '\n' |
  grep -vxE 'search|find|look|for|my|the|a|in|notes?|vault|obsidian|about|what|did|i|write|wrote|written|remember|me|up|on|of|and|to' | paste -sd'|')
[ -z "$terms" ] && { echo "nothing to search for"; exit 0; }
grep -rliE "$terms" "$dir" --include='*.md' 2>/dev/null | head -5 | while read -r f; do
  echo "== ${f#$dir/}"
  grep -iE -m3 "$terms" "$f" | cut -c1-200 | sed 's/^/   /'
done
