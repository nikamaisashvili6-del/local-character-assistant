#!/bin/bash
# desc: open one note by its name and show it (e.g. "read my note Ideas")
# keywords: read, open, show, note, page
# confirm: no
# args: yes
#
# $1 = your sentence. The words after read/open/show are the note's name; the
# best filename match under $NOTES_DIR wins (exact name first, then contains).
dir="${NOTES_DIR:-$HOME/Documents}"
name=$(echo "$1" | tr 'A-Z' 'a-z' | sed -E 's/^.*\b(read|open|show)( me)?( my)?( the)?( note| page)?( called| named)? *//; s/ *(note|page|in obsidian|from (my )?(vault|notes))$//')
[ -z "$name" ] && { echo "which note?"; exit 0; }
f=$(find "$dir" -iname "$name.md" -not -path '*/.obsidian/*' -not -path '*/.trash/*' 2>/dev/null | head -1)
[ -z "$f" ] && f=$(find "$dir" -iname "*$name*.md" -not -path '*/.obsidian/*' -not -path '*/.trash/*' 2>/dev/null | head -1)
[ -z "$f" ] && { echo "no note called '$name'"; exit 0; }
echo "== ${f#$dir/}"
sed -n '1,60p' "$f" | cut -c1-300
[ "$(wc -l < "$f")" -gt 60 ] && echo "   ... ($(wc -l < "$f") lines, showing 60)"
