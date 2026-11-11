"""
skills.py: the assistant LEARNS by writing itself how-to notes (and sometimes
scripts). Nothing it writes is trusted until a reviewer has looked at it.

The idea comes from Hermes Agent's "skills", with one change: a small local
model is not trusted to add code that will later run on your machine, so every
draft waits in a pending/ folder until it's reviewed.

    something works / you type /learn
        -> the model writes a draft:      skills/pending/<name>.md
        -> you get pinged (notification + a line in the chat)
    you run review_skills.py
        -> a reviewer (by default `claude -p`, with NO tools: it can only read
           the draft) checks it and says APPROVE / REJECT, maybe with a fix
        -> you press a / r / s
    approved note    -> skills/<name>.md        pasted in when its keywords come up
    approved script  -> skills/tools/<name>/    a normal tool the router can pick
    approved alias   -> skills/<name>.md        "say: X / do: Y": when you say X, the
                                                router gets Y instead (your shortcuts)

A skill file is plain markdown you can edit by hand:

    # restart-docker
    keywords: restart, docker, server, stack
    shelf: docker, server            (scripts only: the router's shelf words)
    when: Docker is down or acting up

    1. check status first ...
    ```bash
    systemctl --user restart ...
    ```
"""

import re
import shutil
import subprocess
from datetime import datetime

import config

DIR = config.SKILLS_DIR
PENDING = DIR / "pending"
REJECTED = DIR / "rejected"
TOOLS = DIR / "tools"          # approved scripts; config adds this to the router's tool folders


# --- Reading skills -----------------------------------------------------------

def parse(text):
    """A skill file -> dict(name, keywords, shelf, when, body, script)."""
    info = {"name": "", "keywords": set(), "shelf": set(), "when": "", "body": text.strip(),
            "script": "", "say": "", "do": ""}
    m = re.search(r"^#\s+(.+)$", text, re.M)
    if m:
        info["name"] = slug(m.group(1))
    for key in ("keywords", "shelf"):
        m = re.search(rf"^{key}:\s*(.*)$", text, re.M | re.I)
        if m:
            # "enroll site, restart" -> {enroll, site, restart}: the router and
            # the matcher compare single words, so a phrase would never match.
            info[key] = set(re.findall(r"[a-z0-9]+", m.group(1).lower()))
    for key in ("say", "do"):
        m = re.search(rf"^{key}:\s*(.*)$", text, re.M | re.I)
        if m:
            info[key] = m.group(1).strip().strip('"').lower()
    m = re.search(r"^when:\s*(.*)$", text, re.M | re.I)
    if m:
        info["when"] = m.group(1).strip()
    m = re.search(r"```(?:bash|sh)\n(.*?)```", text, re.S)
    if m:
        info["script"] = m.group(1).strip()
    return info


def load():
    """Approved how-to notes (skills/*.md). Scripts are loaded by the router instead."""
    if not DIR.exists():
        return []
    return [parse(f.read_text()) for f in sorted(DIR.glob("*.md"))]


def for_text(text, skills):
    """The notes whose keywords show up in the message: like the lorebook, but
    a note needs TWO keyword hits, so one common word doesn't drag it in."""
    words = set(re.findall(r"[a-z0-9]+", text.lower()))
    return "\n\n".join(s["body"] for s in skills if len(s["keywords"] & words) >= 2)


def apply_aliases(text, skills):
    """'increase volume' -> 'increase spotify volume' if an approved alias says so.
    Whole-phrase match only, so 'say: next' doesn't fire inside 'next week'."""
    low = text.lower()
    for s in skills:
        if s["say"] and s["do"] and re.search(rf"\b{re.escape(s['say'])}\b", low):
            low = re.sub(rf"\b{re.escape(s['say'])}\b", s["do"], low)
    return low if low != text.lower() else text


def review_command():
    """The exact command to review drafts for THIS config."""
    from pathlib import Path
    script = Path(__file__).resolve().parent / "review_skills.py"
    return f"python3 {script} --config={config.CONFIG_FILE}"


def pending():
    return sorted(PENDING.glob("*.md")) if PENDING.exists() else []


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "skill"


# --- Writing drafts -----------------------------------------------------------

DRAFT_PROMPT = """Below is a chat between {user} and their assistant. Did it contain a
procedure worth saving for next time: steps that WORKED, a fix, or something
{user} explained how they want done? Only things that actually happened in
the chat. Never invent commands, paths or results.

If not, answer exactly: NONE

If {user} set a SHORTCUT ("when I say X, do Y", "next time I say X, run Y"),
answer in exactly this format and nothing else:
# short-name-with-dashes
say: X (their exact words)
do: Y (a plain command the assistant already understands)
keywords: X's words
when: one line

Otherwise, if yes, answer in exactly this format and nothing else:
# short-name-with-dashes
keywords: 4 to 8 words {user} would use when asking for this again
when: one line, when to use it
(numbered steps, short)

Only if a few shell lines WITHOUT sudo do the whole job, also add (scripts
run without a terminal and can't type passwords; sudo steps stay in the steps
above, for {user} to run):
shelf: 1 to 3 general topic words (like server, music, network)
```bash
the exact commands from the chat
```
{hint}
Chat:
{chat}"""


def draft(history, ask, hint=""):
    """Ask the model for a skill draft from this chat. Returns the saved path or None."""
    chat = "\n".join(f"{m['role']}: {m['content']}" for m in history[-30:])
    if not chat:
        return None
    text = ask([{"role": "user", "content": DRAFT_PROMPT.format(
        user=config.USER_NAME, chat=chat,
        hint=f"\n{config.USER_NAME} asked you to save this: {hint}\n" if hint else "")}]).strip()
    text = re.sub(r"^```(?:markdown|md)?\n(.*)\n```$", r"\1", text, flags=re.S)   # unwrap
    info = parse(text)
    if text.upper().startswith("NONE") or not info["name"] or not (info["keywords"] or info["say"]):
        return None
    if info["script"] and not real_commands(info["script"]):
        # "desktop/sound/volume: volume: 80%" is a tool's output, not a command
        text = re.sub(r"\n*(shelf:.*\n)?```(?:bash|sh)\n.*?```", "", text, flags=re.S).strip()
        info = parse(text)
    if not info["say"] and not info["script"] and not useful_steps(info["body"]):
        return None                       # nothing but copied tool output: junk
    PENDING.mkdir(parents=True, exist_ok=True)
    path = PENDING / f"{datetime.now():%Y-%m-%d_%H%M}_{info['name']}.md"
    path.write_text(text + "\n")
    ping(f"new skill draft: {info['name']}", f"check it: {review_command()}")
    return path


TOOL_ECHO = re.compile(r"^\(?\s*\d*\.?\s*[\w-]+(/[\w-]+)+:")    # "(1. desktop/sound/volume: ..."


def real_commands(script):
    """At least one line that looks like a command, not a comment or tool output."""
    return any(l.strip() and not l.strip().startswith("#") and not TOOL_ECHO.match(l.strip())
               and not re.match(r"^[\w ]+:\s", l.strip()) for l in script.splitlines())


def useful_steps(body):
    """Steps that say something, not just echo what a tool printed."""
    steps = [l for l in body.splitlines()
             if re.match(r"^\(?\s*\d+\.", l.strip())]
    return any(not TOOL_ECHO.match(l.strip()) for l in steps)


def ping(title, body):
    """Desktop notification; silently skipped where notify-send doesn't exist."""
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", "-a", config.character_name(), title, body],
                       capture_output=True)


# --- After review -------------------------------------------------------------

def install(draft_path, text=None):
    """Approve a draft: a note goes to skills/, a script also becomes a tool."""
    text = text or draft_path.read_text()
    info = parse(text)
    (DIR / f"{info['name']}.md").write_text(text)
    made = [DIR / f"{info['name']}.md"]
    if info["script"]:
        shelf = TOOLS / info["name"]
        shelf.mkdir(parents=True, exist_ok=True)
        words = info["shelf"] or {info["name"].split("-")[0]}
        (shelf / "_shelf.txt").write_text(f"{info['when'] or info['name']}\n{', '.join(sorted(words))}\n")
        script = shelf / f"{info['name']}.sh"
        script.write_text("#!/bin/bash\n"
                          f"# desc: {info['when'] or info['name']}\n"
                          f"# keywords: {', '.join(sorted(info['keywords']))}\n"
                          "# confirm: yes\n"          # learned scripts always ask first
                          f"# learned: {datetime.now():%Y-%m-%d}, reviewed\n"
                          + info["script"] + "\n")
        script.chmod(0o755)
        made.append(script)
    draft_path.unlink()
    return made


def reject(draft_path, reason=""):
    REJECTED.mkdir(parents=True, exist_ok=True)
    dest = REJECTED / draft_path.name
    dest.write_text(draft_path.read_text() + (f"\n<!-- rejected: {reason} -->\n" if reason else ""))
    draft_path.unlink()
    return dest
