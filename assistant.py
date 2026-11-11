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
         /ops     tool output only, one-line answers (for busy days); /chat = back to normal
         /learn   save what just worked as a skill draft (/learn <what to save>)
         /skills  list learned skills and drafts waiting for review
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
import skills                                     # noqa: E402

# --- Settings ----------------------------------------------------------------

LOG_DIR = HERE / "logs"                           # full chat logs (gitignored, private)
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]   # plain word = model name
# (--config=path is read by config.py)
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


def use_raw_prompt():
    """Hand-built prompt only where we measured it helps (see config raw_prompt)."""
    if config.RAW_PROMPT == "auto":
        return "mistral-nemo" in MODEL
    return config.RAW_PROMPT == "on"


def _request_raw(prompt):
    """Stream from /api/generate with raw=True (we wrote the template ourselves)."""
    body = {"model": MODEL, "prompt": prompt, "raw": True, "stream": True,
            "options": {"temperature": config.TEMPERATURE, "num_ctx": CONTEXT_TOKENS}}
    req = urllib.request.Request(OLLAMA_URL.replace("/api/chat", "/api/generate"),
                                 json.dumps(body).encode(), {"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=300)


def _request(messages, stream):
    body = {"model": MODEL, "messages": messages, "stream": stream, "think": False,
            "options": {"temperature": config.TEMPERATURE,   # lower = less invention
                        "num_ctx": CONTEXT_TOKENS}}
    req = urllib.request.Request(OLLAMA_URL, json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=300)


def ask_quiet(messages):
    """One answer, no printing. Used by the brain for summaries and the journal."""
    with _request(messages, stream=False) as resp:
        text = json.load(resp)["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def ask_character(messages, show=True):
    """Stream the reply to the screen as it's generated, return the full text.

    Mistral models get the hand-built, cache-friendly prompt; any other model
    goes through Ollama's normal chat endpoint.
    """
    full, hiding = "", False
    held = ""            # first few characters, held back to cut a "Kid," opener
    out = print if show else (lambda *a, **k: None)      # evals run silently
    out(f"{RED}{BOLD}{SHORT} ▸ {RESET}{CHROME}", end="", flush=True)
    if use_raw_prompt():
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
                    out(cut_opener(held), end="", flush=True)
                    held = None                         # from now on print directly
                else:
                    out(piece, end="", flush=True)
            if "</think>" in piece:
                hiding = False
            if chunk.get("done"):
                break
    if held:                                            # very short reply
        out(cut_opener(held), end="")
    out(RESET + "\n")
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


def build_system(persona, lore, notes, journal, me=""):
    """The FIXED part of what it knows: identical every turn, so it gets cached.

    Anything that changes (time, triggered lore, summary, tool results) goes
    next to your latest message instead; see dynamic_note().
    """
    parts = [persona, "# Your memories\n" + lore]
    if notes:
        parts.append(f"# What you know about {config.USER_NAME}\nUse it like an old friend "
                     "would, and when they ask about themselves, answer straight from it.\n\n"
                     + notes)
    if me:
        parts.append("# What you've learned about yourself and working with them\n" + me)
    if journal:
        parts.append("# Your journal (what happened in recent sessions)\n" + journal)
    return {"role": "system", "content": "\n\n".join(parts)}


# A message is a REQUEST if it STARTS like a command ("check my calendar",
# "can you open...", "how many emails"). Anchored to the start on purpose:
# "what do you think about my plan to start a project" is chat, not a command.
REQUEST = re.compile(r"^\s*(please\s+|can you\s+|could you\s+|pls\s+)?"
                     r"(check|show|open|play|read|send|set|turn|start|stop|find|search|"
                     r"look up|how many|what'?s on|close|delete|create|remind)\b", re.I)


# "you told me X", "remember when", "you said": the user claims a shared past.
# Small models play along and invent it. So we check the journal and logs first.
CLAIM = re.compile(r"\b(you (told|said|mentioned|promised|showed)|remember (when|the|that|what)|"
                   r"yesterday you|last time you|we talked about)\b", re.I)
# "desktop/music/next:" or "volume: 100%" in a reply with no tool run = invented.
FAKE_TOOL = re.compile(r"^\s*[\w-]+(/[\w-]+)+:|^\s*(now|volume|music paused)\b", re.I | re.M)

FILLER = set("the a an you me my i told said about that this what when remember yesterday last "
             "time we talked explain mentioned promised showed of to and is was it".split())


def check_claim(text, history):
    """If the message claims a shared past, look for it. Returns a note or ''."""
    if not CLAIM.search(text):
        return ""
    words = [w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in FILLER and len(w) > 2]
    if not words:
        return ""
    past = " ".join(m["content"] for m in history).lower()     # this conversation
    past += " " + brain.recent_journal().lower()                # recent journal days
    for log in sorted(LOG_DIR.glob("*.md"))[-10:]:              # last 10 chat logs
        past += " " + log.read_text().lower()
    found = [w for w in words if w in past]
    if len(found) >= max(1, len(words) // 2):
        return ""                                               # plausible, let it answer
    return (f"memory check: nothing about '{' '.join(words)}' in your journal, logs or this "
            "chat. You never told them that, as far as you can tell. Say so plainly; "
            "don't invent it.")


def dynamic_note(text, lore, summary, results, claim="", howto="", ops=False):
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
    if howto:
        parts.append("how-to notes you saved earlier (reviewed, follow them):\n" + howto)
    if claim:
        parts.append(claim)
    if router.RULE.match(text):
        parts.append("They're setting a rule for later, not asking you to do it now. "
                     "Say in one line you'll remember it once they type /learn.")
    if ops:
        parts.append("ops mode: they're busy. One or two plain lines, facts only, no personality.")
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


# --- One conversation --------------------------------------------------------

class Session:
    """Everything one conversation needs. The terminal loop below and the eval
    script (evals/run_eval.py) both drive this same class, so what gets tested
    is exactly what you talk to."""

    def __init__(self, blind=BLIND, show=True):
        self.show = show                              # False = don't print (evals)
        self.lore_sections = brain.load_lore()
        self.notes = "" if blind else load_user_notes()
        journal = "" if blind else brain.recent_journal()
        self.tools = router.load_tools()
        self.skills = skills.load()
        self.system = build_system(load_persona(), brain.core_lore(self.lore_sections),
                                   self.notes, journal, "" if blind else brain.load_self())
        self.history, self.summary = [], ""           # recent turns + story so far
        self.ops = False                              # /ops: raw tool output, one-liners
        self.topic = ""                               # shelf of the last tool, for "next"

    def reset(self):
        self.history.clear()
        self.summary = ""

    def turn(self, text, confirm=input):
        """One message in, one reply out. Returns (reply, names of tools that ran)."""
        # 1. WATCHER: which tools does this message need? Run them in order;
        #    each tool gets the previous tool's output on stdin.
        results, previous, ran = [], "", []
        routed_text = skills.apply_aliases(text, self.skills)     # your shortcuts
        if routed_text != text and self.show:
            print(f"{DIM}  ↪ {routed_text}{RESET}")
        for task, tool in router.route(routed_text, self.tools, self.topic):
            if self.show:
                print(f"{DIM}  ⚙ {tool['name']}{RESET}")
            previous = router.run(task, tool, previous, confirm=confirm)
            results.append(f"{tool['name']}:\n{previous}")
            ran.append(tool["name"])

        if ran:
            parts = ran[-1].split("/")
            self.topic = parts[-2] if len(parts) > 1 else ""

        # RAW: the tool's own words, printed instantly. No model in between, so
        # a status check takes a second and nothing gets retold or invented.
        if results and (self.ops or config.TOOL_OUTPUT == "raw"):
            output = "\n\n".join(results)
            if self.show:
                print(output + "\n")
            # Stored as the USER's side + a stub reply, never as the model's own
            # words: it copied that format and faked "now: <song>" (that happened).
            self.history += [{"role": "user", "content": f"{text}\n\n[TOOL RESULTS]\n{output}"},
                             {"role": "assistant", "content": "(shown to them)"}]
            return output, ran

        # 2. MEMORY: if the chat is long, boil the oldest part into the summary.
        if len(self.history) >= SUMMARIZE_AT:
            old, self.history = self.history[:-KEEP_RECENT], self.history[-KEEP_RECENT:]
            try:
                self.summary = brain.summarize(old, self.summary, ask_quiet)
            except Exception:
                pass                                  # worst case it forgets, like before

        # 3. LOREBOOK: pick the memories that match the last few messages.
        recent = " ".join(m["content"] for m in self.history[-4:]) + " " + text
        lore = brain.lore_for(recent, self.lore_sections)
        howto = skills.for_text(text, self.skills)

        # 4. MOUTH: fixed system (cached) + recent chat + your message with the
        #    changing bits attached. History stores tool results but not the
        #    time/lore, so past turns stay byte-for-byte identical (= cached).
        user_msg = text + ("\n\n[TOOL RESULTS]\n" + "\n\n".join(results) if results else "")
        messages = ([self.system] + self.history
                    + [{"role": "user", "content": text + dynamic_note(
                        text, lore, self.summary, results, check_claim(text, self.history),
                        howto, self.ops)}])
        reply = ask_character(messages, show=self.show)
        if not results and FAKE_TOOL.search(reply):
            # It wrote something shaped like tool output with no tool run: a fake.
            reply = "No tool ran for that, so nothing happened. Try saying it with the topic (e.g. 'next song')."
            if self.show:
                print(f"{DIM}  [blocked a made-up tool result] {reply}{RESET}\n")
        self.history += [{"role": "user", "content": user_msg},
                         {"role": "assistant", "content": reply}]
        return reply, ran

    def write_journal(self):
        """Journal entry, then self.md rewritten from it. Returns the journal path."""
        if not self.history:
            return None
        path, entry = brain.write_journal(self.history, self.summary, ask_quiet)
        brain.update_self(entry, ask_quiet)
        return path

    def learn(self, hint=""):
        """Draft a skill from this chat into skills/pending/ (needs review to count)."""
        return skills.draft(self.history, ask_quiet, hint)


# --- Terminal loop ------------------------------------------------------------

def main():
    session = Session()
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / datetime.now().strftime("%Y-%m-%d_%H%M.md")

    info = "blind" if BLIND else f"{'knows you · ' if session.notes else ''}{len(session.tools)} tools"
    print(f"\n{RED}{BOLD}  ▓▒░ {NAME.upper()} ░▒▓{RESET}\n"
          f"{DIM}  online · model: {MODEL} · {info} · /tools /ops /learn /reset /quit{RESET}")
    waiting = skills.pending()
    if waiting:
        print(f"{DIM}  {len(waiting)} skill draft(s) waiting. In a terminal: {skills.review_command()}{RESET}")
    print()

    while True:
        try:
            text = input(f"{BOLD}you ▸ {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            text = "/quit"

        if not text:
            continue
        if text == "/quit":
            if session.history and not BLIND:
                print(f"{DIM}  [writing journal...]{RESET}")
                try:
                    print(f"{DIM}  [saved to {session.write_journal()}]{RESET}")
                except Exception as e:
                    print(f"{DIM}  [journal failed: {e}]{RESET}")
                if config.SKILLS_AUTO:
                    try:
                        draft = session.learn()
                        if draft:
                            print(f"{DIM}  [skill draft for review: {draft.name}]{RESET}")
                    except Exception as e:
                        print(f"{DIM}  [skill draft failed: {e}]{RESET}")
            print(f"\n{DIM}  [{NAME} went quiet]{RESET}\n")
            break
        if text == "/reset":
            session.reset()
            print(f"{DIM}  [memory wiped]{RESET}\n")
            continue
        if text in ("/ops", "/chat"):
            session.ops = text == "/ops"
            print(f"{DIM}  [{'ops mode: raw tool output, one-liners' if session.ops else 'chat mode'}]{RESET}\n")
            continue
        if text.startswith("/learn"):
            print(f"{DIM}  [drafting a skill...]{RESET}")
            try:
                draft = session.learn(text[len("/learn"):].strip())
                print(f"{DIM}  [{f'draft saved: {draft.name}. Review it in a terminal: {skills.review_command()}' if draft else 'nothing worth saving found'}]{RESET}\n")
            except Exception as e:
                print(f"{DIM}  [failed: {e}]{RESET}\n")
            continue
        if text == "/skills":
            for s_ in session.skills:
                print(f"{DIM}  ✓ {s_['name']:28} {s_['when']}{RESET}")
            for d in skills.pending():
                print(f"{DIM}  … {d.name} (waiting for review){RESET}")
            if not session.skills and not skills.pending():
                print(f"{DIM}  none yet. /learn after something works{RESET}")
            print()
            continue
        if text == "/tools":
            for t in session.tools:
                flag = " (asks first)" if t["confirm"] else ""
                print(f"{DIM}  {t['name']:28} {t['desc']}{flag}{RESET}")
            print()
            continue

        try:
            reply, _ = session.turn(text)
        except Exception as e:
            print(f"{RESET}{DIM}  [signal lost: {e}]{RESET}\n")
            continue
        with log_path.open("a") as log:
            log.write(f"**you:** {session.history[-2]['content']}\n\n**{SHORT}:** {reply}\n\n")


if __name__ == "__main__":
    main()
