"""
brain.py: the character's MEMORY. Three pieces, borrowed from character-AI apps
and from agent frameworks like Hermes Agent:

  1. LOREBOOK  (the "world info" trick from character-AI apps)
     character/lore.md is split into sections, each with "triggers: word, word".
     A section is only pasted in when one of its words shows up in the recent
     chat. "always" sections are pasted every time. Less text per message =
     faster replies, and more room for the conversation.

  2. ROLLING SUMMARY
     When the chat gets long, the oldest messages are boiled down into a short
     "story so far" instead of being forgotten.

  3. JOURNAL  (like Hermes' MEMORY.md)
     On /quit the character writes the key points of the session into a
     markdown journal (point it at an Obsidian vault if you like). On the next
     start it rereads the last few entries, so it remembers yesterday. You can
     open and edit the journal anytime.
"""

import re
from datetime import datetime
from pathlib import Path

import config

LORE_FILE = config.CHARACTER_DIR / "lore.md"
JOURNAL_DIR = config.JOURNAL_DIR
JOURNAL_DAYS = config.JOURNAL_DAYS     # how many past days of journal it rereads on startup


# --- 1. Lorebook -------------------------------------------------------------

def load_lore():
    """Split lore.md into [(triggers, text)], one per '## ' section."""
    sections = []
    for chunk in re.split(r"\n(?=## )", LORE_FILE.read_text()):
        if not chunk.startswith("## "):
            continue                                    # the file's intro paragraph
        m = re.search(r"^triggers:\s*(.*)$", chunk, re.M)
        triggers = {w.strip().lower() for w in m.group(1).split(",")} if m else {"always"}
        text = re.sub(r"^triggers:.*\n", "", chunk, flags=re.M).strip()
        sections.append((triggers, text))
    return sections


def core_lore(sections):
    """The 'always' sections: who he is. Same every turn, so it can be cached."""
    return "\n\n".join(text for triggers, text in sections if "always" in triggers)


def lore_for(recent_text, sections):
    """The triggered sections that match the recent chat (the lorebook part)."""
    words = set(re.findall(r"[a-z0-9]+", recent_text.lower()))
    picked = [text for triggers, text in sections
              if "always" not in triggers and triggers & words]
    return "\n\n".join(picked)


# --- 2. Rolling summary ------------------------------------------------------

def summarize(old_messages, previous_summary, ask):
    """Boil old messages down into a short 'story so far'.

    `ask` is a function that sends messages to the model and returns its text
    (assistant.py passes it in, so this file doesn't care which model it is).
    """
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in old_messages)
    prompt = (f"Summarise this conversation between {config.USER_NAME} (user) and "
              f"{config.character_name()} in at most "
              "6 short bullet points. Keep facts, decisions, names, plans and feelings. "
              "No roleplay, just the facts.\n\n"
              + (f"Earlier summary:\n{previous_summary}\n\n" if previous_summary else "")
              + f"Conversation:\n{convo}")
    return ask([{"role": "user", "content": prompt}])


# --- 3. Journal --------------------------------------------------------------

def recent_journal():
    """The last JOURNAL_DAYS journal files, oldest first, as one block of text."""
    if not JOURNAL_DIR.exists():
        return ""
    files = sorted(JOURNAL_DIR.glob("*.md"))[-JOURNAL_DAYS:]
    return "\n\n".join(f"### {f.stem}\n{f.read_text().strip()}" for f in files)


def write_journal(history, summary, ask):
    """Have the character write the key points of this session into today's journal note."""
    if not history:
        return None
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in history[-40:])
    prompt = (f"You are {config.character_name()} writing in your private journal about today's "
              f"chat with {config.USER_NAME}. Write 3 to 5 short bullet points in your own voice: what you "
              "talked about, what got decided, anything new you learned about them, and "
              "anything to bring up next time. Facts must be accurate. Bullets only.\n\n"
              + (f"Earlier in the chat:\n{summary}\n\n" if summary else "")
              + f"Chat:\n{convo}")
    bullets = ask([{"role": "user", "content": prompt}]).strip()

    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    today = JOURNAL_DIR / f"{datetime.now():%Y-%m-%d}.md"
    with today.open("a") as f:                          # several sessions a day = appended
        f.write(f"**{datetime.now():%H:%M}**\n{bullets}\n\n")
    return today
