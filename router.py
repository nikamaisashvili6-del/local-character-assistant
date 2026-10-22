"""
router.py: the WATCHER. Reads your message, decides which tools (if any) to run.

The bookshelf idea:
    tools/                      <- the library
      desktop/                  <- bookshelf   (has _shelf.txt: description + keywords)
        music/                  <- shelf       (has _shelf.txt)
          pause.sh              <- book = a script (header says desc/keywords/confirm)

How a message gets routed:
  0. SPLIT    "pause the music and lock the screen"  ->  ["pause the music", "lock the screen"]
  1. DICTIONARY (fast, no model): every word is matched against the keywords of
     each script + its shelf + its bookshelf. Highest score wins.
  2. If two scripts tie, ask llama to pick, BUT only between those few. Small
     models get "pick 1 of 2" right; "pick 1 of 40" they get wrong.
  3. No keyword hit at all = just chatting, no tool, no model call. Fast.

Adding a power = drop a script with the header into a shelf folder.
"""

import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

import config

TOOLS_DIR = Path(__file__).resolve().parent / "tools"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
WATCHER_MODEL = config.WATCHER_MODEL   # the small one; runs on CPU so the big model keeps the GPU

# Words that glue commands together. "pause music and lock screen" splits here.
SPLITTERS = r"\s*(?:\band then\b|\bthen\b|\band\b|\balso\b|[,;])\s*"

# Filler words that should never count as a keyword match or a search term.
STOPWORDS = set("""a an the me my i you u it is are to of on in for and or please can
could would will just yo hey some what whats how do does""".split())


# --- Loading the library -----------------------------------------------------

def _read_header(script):
    """Pull '# desc:', '# keywords:', '# confirm:', '# args:' out of a script's top comments."""
    info = {"desc": "", "keywords": set(), "confirm": False, "args": False}
    for line in script.read_text().splitlines()[:15]:
        m = re.match(r"#\s*(desc|keywords|confirm|args):\s*(.*)", line)
        if not m:
            continue
        key, val = m.groups()
        if key == "keywords":
            info["keywords"] = {w.strip().lower() for w in val.split(",") if w.strip()}
        elif key in ("confirm", "args"):
            info[key] = val.strip().lower() == "yes"
        else:
            info[key] = val.strip()
    return info


def _read_shelf(folder):
    """A shelf's _shelf.txt: line 1 = description, line 2 = keywords."""
    f = folder / "_shelf.txt"
    if not f.exists():
        return "", set()
    lines = f.read_text().splitlines() + ["", ""]
    return lines[0].strip(), {w.strip().lower() for w in lines[1].split(",") if w.strip()}


def load_tools():
    """Walk tools/ and return one dict per script, with its whole path's keywords.

    Each tool remembers its own keywords AND its shelves' keywords separately,
    because a hit on the book ("status") should count more than a hit on the
    bookshelf ("server").
    """
    tools = []
    for script in sorted(TOOLS_DIR.rglob("*")):
        if not script.is_file() or script.name.startswith("_") or not (script.stat().st_mode & 0o111):
            continue                                    # skip _shelf.txt and non-executables
        info = _read_header(script)
        shelf_words = set()
        for folder in script.relative_to(TOOLS_DIR).parents:   # music/, desktop/, '.'
            shelf_words |= _read_shelf(TOOLS_DIR / folder)[1]
        info.update(path=script, name=str(script.relative_to(TOOLS_DIR).with_suffix("")),
                    shelf_words=shelf_words)
        tools.append(info)
    return tools


# --- Step 0: split -----------------------------------------------------------

def split_tasks(message):
    """'pause the music and lock the screen' -> ['pause the music', 'lock the screen']."""
    return [p for p in re.split(SPLITTERS, message.lower()) if p.strip()]


def _words(text):
    return [w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in STOPWORDS]


# --- Step 1: dictionary scoring ----------------------------------------------

def score(task, tool):
    """Book keyword = 2 points, shelf keyword = 1 point. Needs a shelf hit to count.

    Requiring a shelf word stops 'check' alone from firing a tool: "check this
    out" mentions no shelf (music, pc, browser...), so it stays a chat.
    """
    words = set(_words(task))
    shelf_hits = len(words & tool["shelf_words"])
    book_hits = len(words & tool["keywords"])
    # Needs BOTH a shelf word and a book word. "i love that song" hits the music
    # shelf ("song") but no action word, so it stays a chat instead of a tool.
    if shelf_hits == 0 or book_hits == 0:
        return 0
    return shelf_hits + 2 * book_hits


# --- Step 2: llama tie-break -------------------------------------------------

def ask_llama(task, candidates):
    """Ask the small model to pick ONE of a few candidate tools (or none)."""
    menu = "\n".join(f"{i}. {t['desc']}" for i, t in enumerate(candidates, 1))
    prompt = (f'Request: "{task}"\n\nWhich option fits the request best?\n{menu}\n'
              f"0. none of these\n\nAnswer with the number only.")
    body = {"model": WATCHER_MODEL, "stream": False, "think": False,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": 0, "num_gpu": 0}}   # num_gpu 0 = CPU only
    req = urllib.request.Request(OLLAMA_URL, json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    try:
        answer = json.load(urllib.request.urlopen(req, timeout=60))["message"]["content"]
        n = int(re.search(r"\d+", answer).group())
        return candidates[n - 1] if 1 <= n <= len(candidates) else None
    except Exception:
        return candidates[0]                 # model confused/down: trust the dictionary


def route(message, tools):
    """Return a list of (task_text, tool) for every task that needs a tool."""
    plan, verb = [], ""
    for task in split_tasks(message):
        best, tied = _best(task, tools)
        # "open vs code and file manager": the 2nd part lost its verb. If a part
        # matches nothing, borrow the first word of the part before it.
        if best == 0 and verb:
            task = f"{verb} {task}"
            best, tied = _best(task, tools)
        if best == 0:
            continue                                        # just talk
        verb = task.split()[0]
        tool = tied[0] if len(tied) == 1 else ask_llama(task, tied)
        if not tool:
            continue
        for i, (old_task, old_tool) in enumerate(plan):     # same tool twice = run
            if old_tool is tool:                            # once with both parts
                plan[i] = (f"{old_task} and {task}", tool)
                break
        else:
            plan.append((task, tool))
    return plan


def _best(task, tools):
    """Top score for this task and every tool sharing it (a tie if more than one)."""
    scored = sorted(((score(task, t), t) for t in tools), key=lambda x: -x[0])
    best = scored[0][0] if scored else 0
    return best, [t for s, t in scored if s == best]


# --- Step 4: run -------------------------------------------------------------

def run(task, tool, previous_output="", confirm=input):
    """Run one tool. Tools marked 'confirm: yes' ask you first.

    previous_output goes to the script's stdin, so a later tool in the same
    request can use what an earlier one printed.
    """
    if tool["confirm"]:
        if confirm(f"  ⚠ run {tool['name']}? ({tool['desc']}) [y/N] ").strip().lower() not in ("y", "yes"):
            return "(you said no, so it did not run)"
    cmd = [str(tool["path"])]
    if tool["args"]:                     # tool gets your whole sentence as $1 and
        cmd.append(task)                 # picks out what it needs (song, url, time...)
    try:
        env = dict(os.environ, NOTES_DIR=str(config.NOTES_DIR))   # for the notes tool
        out = subprocess.run(cmd, input=previous_output, capture_output=True,
                             text=True, timeout=60, env=env)
        return (out.stdout + out.stderr).strip()[:1500] or "(no output)"
    except Exception as e:
        return f"(tool failed: {e})"


if __name__ == "__main__":
    # Quick test without the character:  python3 router.py "pause the music and lock the screen"
    import sys
    tools = load_tools()
    for task, tool in route(" ".join(sys.argv[1:]), tools):
        print(f"{task!r:45} -> {tool['name']}")
