# helper sourced by the browser tools: picks Chrome or Firefox from the sentence
browser() { if echo "$1" | grep -qi firefox; then echo firefox; else echo google-chrome; fi; }
strip() { echo "$1" | tr 'A-Z' 'a-z' | sed -E "s/\b($2|in|on|with|chrome|firefox|google|browser|for|the|a|me|please|open|new|tab|search|up)\b//g" | xargs; }
