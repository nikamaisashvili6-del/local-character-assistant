#!/usr/bin/env python3
"""
local-character-assistant: talk to a character AI in your terminal that can
also DO things on your computer. Runs fully local on Ollama.

Three parts, three files:
  router.py     the WATCHER  reads your words, picks tools from the tools/ tree
  brain.py      the MEMORY   lorebook, rolling summary, journal
  this file     the MOUTH    builds the prompt, the big model answers in character

One turn, start to finish:
  you type -> watcher: any tools needed? -> run them (asks first if risky)
           -> build the prompt: persona + core lore + your notes + journal (fixed,
              cached) + recent chat + your message with the changing bits
              (time, triggered lore, story-so-far, tool results)
           -> the model streams the reply -> remembered for next turn

Nothing leaves your machine. Only the Python standard library is used.
Your settings live in config.toml (copy config.example.toml).

Run:     ./assistant.py                 (model from config.toml)
         ./assistant.py llama3.2:3b     (any other Ollama model)
         ./assistant.py --blind         (the character knows nothing about you)
Inside:  /tools   list what it can do
         /reset   forget this conversation
         /quit    leave; the character writes its journal first (Ctrl+C / Ctrl+D too)
"""

import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))                     # so imports work via a symlink
import brain                                      # noqa: E402
import config                                     # noqa: E402
import router                                     # noqa: E402

# --- Settings ----------------------------------------------------------------

LOG_DIR = HERE / "logs"                           # full chat logs (gitignored, private)
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]   # plain word = model name
BLIND = "--blind" in sys.argv
MODEL = ARGS[0] if ARGS else config.MODEL
CONTEXT_TOKENS = config.CONTEXT_TOKENS
NAME = config.character_name()                    # e.g. "Rook Malone"
SHORT = NAME.split()[0].lower()                   # e.g. "rook", the chat label

KEEP_RECENT = 20          # messages kept word for word (10 back-and-forths)
SUMMARIZE_AT = 30         # when history hits this, the oldest get summarised

RED, CHROME, DIM, BOLD, RESET = "\033[38;5;160m", "\033[38;5;250m", "\033[2m", "\033[1m", "\033[0m"


# --- Talking to the model ----------------------------------------------------

def build_mistral_prompt(system, history, last_user):
    """Write the prompt by hand in Mistral's format, system prompt FIRST.

    Why: Ollama's built-in template for Mistral models puts the system prompt
    right before your LATEST message, so its ~3000 tokens move every turn and
    Ollama re-reads all of them (~50 s on an 8 GB card with CPU spill). With
    the system prompt at the very start, everything up to your new message is
    identical to last turn, Ollama reuses its cache, and only the new words get
    read: replies dropped from ~50 s to ~3-7 s.

    Mistral format:  [INST]system + msg1[/INST] reply1</s>[INST]msg2[/INST]
    """
    turns = history + [{"role": "user", "content": last_user}]
    out, first = "", True
    for m in turns:
        if m["role"] == "user":
            content = (system + "\n\n" + m["content"]) if first else m["content"]
            out += f"[INST]{content}[/INST]"
            first = False
        else:
            out += f" {m['content']}</s>"
    return out


def _request_raw(prompt):
    """Stream from /api/generate with raw=True (we wrote the template ourselves)."""
    body = {"model": MODEL, "prompt": prompt, "raw": True, "stream": True,
            "options": {"temperature": 0.6, "num_ctx": CONTEXT_TOKENS}}
    req = urllib.request.Request(OLLAMA_URL.replace("/api/chat", "/api/generate"),
                                 json.dumps(body).encode(), {"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=300)


def _request(messages, stream):
    body = {"model": MODEL, "messages": messages, "stream": stream, "think": False,
            "options": {"temperature": 0.6,      # Mistral models drift off-topic above ~0.7
                        "num_ctx": CONTEXT_TOKENS}}
    req = urllib.request.Request(OLLAMA_URL, json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=300)


def ask_quiet(messages):
    """One answer, no printing. Used by the brain for summaries and the journal."""
    with _request(messages, stream=False) as resp:
        text = json.load(resp)["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def ask_character(messages):
    """Stream the reply to the screen as it's generated, return the full text.

    Mistral models get the hand-built, cache-friendly prompt; any other model
    goes through Ollama's normal chat endpoint.
    """
    full, hiding = "", False
    held = ""            # first few characters, held back to cut a "Kid," opener
    print(f"{RED}{BOLD}{SHORT} ▸ {RESET}{CHROME}", end="", flush=True)
    if "mistral" in MODEL:
        system, *rest = messages
        resp_ctx = _request_raw(build_mistral_prompt(system["content"], rest[:-1], rest[-1]["content"]))
    else:
        resp_ctx = _request(messages, stream=True)
    with resp_ctx as resp:
        for line in resp:                               # one JSON chunk per line
            chunk = json.loads(line)
            piece = chunk.get("message", {}).get("content", "") or chunk.get("response", "")
            full += piece
            if "<think>" in piece:                      # hide leaked "thinking"
                hiding = True
            if not hiding:
                if held is not None:                    # still at the very start
                    held += piece
                    if len(held) < 12 and not chunk.get("done"):
                        continue                        # wait for a few more chars
                    print(cut_opener(held), end="", flush=True)
                    held = None                         # from now on print directly
                else:
                    print(piece, end="", flush=True)
            if "</think>" in piece:
                hiding = False
            if chunk.get("done"):
                break
    if held:                                            # very short reply
        print(cut_opener(held), end="")
    print(RESET + "\n")
    return cut_opener(re.sub(r"<think>.*?</think>", "", full, flags=re.S).strip())


def cut_opener(text):
    """'Kid, you're up early' -> 'You're up early'. Small models love opening
    every reply with a name and ignore the rule against it, so we trim it in
    code. Keeping it out of the history also stops the habit reinforcing itself."""
    # Also drops a leading "rook:" label, copied from the example dialogues.
    text = re.sub(rf"^\s*{re.escape(SHORT)}\s*:\s*", "", text, flags=re.I)
    names = "|".join(re.escape(n) for n in (config.USER_NAME, config.TEASE_NAME) if n)
    out = re.sub(rf"^\s*(hey,?\s+|alright,?\s+|yo,?\s+)?({names})[,.!]?(\s+|$)", "", text, flags=re.I)
    return out[:1].upper() + out[1:] if out != text else out


# --- Building the prompt -----------------------------------------------------

def load_persona():
    """persona.txt with {user_name} / {tease_name} filled in from config."""
    text = (config.CHARACTER_DIR / "persona.txt").read_text().strip()
    return text.replace("{user_name}", config.USER_NAME).replace("{tease_name}", config.TEASE_NAME)


def load_user_notes():
    """Your markdown notes about yourself, minus any '---' frontmatter block."""
    parts = []
    for f in config.USER_NOTES:
        if f.exists():
            text = f.read_text()
            if text.startswith("---"):
                text = text.split("---", 2)[2]
            parts.append(text.strip())
    return "\n\n".join(parts)


def build_system(persona, lore, notes, journal):
    """The FIXED part of what it knows: identical every turn, so it gets cached.

    Anything that changes (time, triggered lore, summary, tool results) goes
    next to your latest message instead; see dynamic_note().
    """
    parts = [persona, "# Your memories\n" + lore]
    if notes:
        parts.append(f"# What you know about {config.USER_NAME}\nUse it like an old friend "
                     "would, and when they ask about themselves, answer straight from it.\n\n"
                     + notes)
    if journal:
        parts.append("# Your journal (what happened in recent sessions)\n" + journal)
    return {"role": "system", "content": "\n\n".join(parts)}


# A message is a REQUEST if it STARTS like a command ("check my calendar",
# "can you open...", "how many emails"). Anchored to the start on purpose:
# "what do you think about my plan to start a project" is chat, not a command.
REQUEST = re.compile(r"^\s*(please\s+|can you\s+|could you\s+|pls\s+)?"
                     r"(check|show|open|play|read|send|set|turn|start|stop|find|search|"
                     r"look up|how many|what'?s on|close|delete|create|remind)\b", re.I)


def dynamic_note(text, lore, summary, results):
    """The CHANGING part, attached to your latest message only (never stored)."""
    # The real clock plus a part-of-day word, so the model can't mistake 21:00
    # for "3am" because your notes say you're a night owl (that happened).
    now = datetime.now()
    part = ("night" if now.hour < 5 else "morning" if now.hour < 12 else
            "afternoon" if now.hour < 18 else "evening" if now.hour < 23 else "night")
    where = f", {config.PLACE}" if config.PLACE else ""
    parts = [f"now: {now:%A %d %B %Y, %H:%M}, {part}{where} (don't announce it)"]
    if summary:
        parts.append("earlier in this chat:\n" + summary)
    if lore:
        parts.append("memories this brings up:\n" + lore)
    if results:
        parts.append("[TOOL RESULTS] (this is ALL that actually happened. Report it as is. "
                     "Don't add song names, numbers or outcomes that aren't written here)\n"
                     + "\n\n".join(results))
    elif REQUEST.search(text):
        # Said right next to the message: a rule deep in the persona wasn't
        # enough, the model still "checked" a calendar it had no access to.
        parts.append(f'{config.USER_NAME} asked: "{text}". You have NO tool for that, so you '
                     "can't see or do it. Tell them straight you can't reach that one (yet). "
                     "Don't make up an answer.")
    return "\n\n(" + "\n\n".join(parts) + ")"


# --- Main loop ---------------------------------------------------------------

def main():
    persona = load_persona()
    lore_sections = brain.load_lore()
    notes = "" if BLIND else load_user_notes()
    journal = "" if BLIND else brain.recent_journal()
    tools = router.load_tools()
    system = build_system(persona, brain.core_lore(lore_sections), notes, journal)

    history, summary = [], ""                     # recent turns + story so far
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / datetime.now().strftime("%Y-%m-%d_%H%M.md")

    info = "blind" if BLIND else f"{'knows you · ' if notes else ''}{len(tools)} tools"
    print(f"\n{RED}{BOLD}  ▓▒░ {NAME.upper()} ░▒▓{RESET}\n"
          f"{DIM}  online · model: {MODEL} · {info} · /tools /reset /quit{RESET}\n")

    while True:
        try:
            text = input(f"{BOLD}you ▸ {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            text = "/quit"

        if not text:
            continue
        if text == "/quit":
            if history and not BLIND:
                print(f"{DIM}  [writing journal...]{RESET}")
                try:
                    path = brain.write_journal(history, summary, ask_quiet)
                    print(f"{DIM}  [saved to {path}]{RESET}")
                except Exception as e:
                    print(f"{DIM}  [journal failed: {e}]{RESET}")
            print(f"\n{DIM}  [{NAME} went quiet]{RESET}\n")
            break
        if text == "/reset":
            history.clear()
            summary = ""
            print(f"{DIM}  [memory wiped]{RESET}\n")
            continue
        if text == "/tools":
            for t in tools:
                flag = " (asks first)" if t["confirm"] else ""
                print(f"{DIM}  {t['name']:28} {t['desc']}{flag}{RESET}")
            print()
            continue

        # 1. WATCHER: which tools does this message need? Run them in order;
        #    each tool gets the previous tool's output on stdin.
        results, previous = [], ""
        for task, tool in router.route(text, tools):
            print(f"{DIM}  ⚙ {tool['name']}{RESET}")
            previous = router.run(task, tool, previous)
            results.append(f"{tool['name']}:\n{previous}")

        # 2. MEMORY: if the chat is long, boil the oldest part into the summary.
        if len(history) >= SUMMARIZE_AT:
            old, history = history[:-KEEP_RECENT], history[-KEEP_RECENT:]
            try:
                summary = brain.summarize(old, summary, ask_quiet)
            except Exception:
                pass                                # worst case it forgets, like before

        # 3. LOREBOOK: pick the memories that match the last few messages.
        recent = " ".join(m["content"] for m in history[-4:]) + " " + text
        lore = brain.lore_for(recent, lore_sections)

        # 4. MOUTH: fixed system (cached) + recent chat + your message with the
        #    changing bits attached. History stores tool results but not the
        #    time/lore, so past turns stay byte-for-byte identical (= cached).
        user_msg = text + ("\n\n[TOOL RESULTS]\n" + "\n\n".join(results) if results else "")
        messages = ([system] + history
                    + [{"role": "user", "content": text + dynamic_note(text, lore, summary, results)}])

        try:
            reply = ask_character(messages)
        except Exception as e:
            print(f"{RESET}{DIM}  [signal lost: {e}]{RESET}\n")
            continue

        history += [{"role": "user", "content": user_msg},
                    {"role": "assistant", "content": reply}]
        with log_path.open("a") as log:
            log.write(f"**you:** {user_msg}\n\n**{SHORT}:** {reply}\n\n")


if __name__ == "__main__":
    main()
