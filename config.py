"""
config.py: loads config.toml (or config.example.toml if you haven't made one).

Everything personal (your name, your notes, where the journal goes) lives in
the config file, so the code itself never has to change.
"""

import os
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _find_config():
    """Which config file? First match wins:
    1. --config=/path/to/config.toml on the command line
    2. the ASSISTANT_CONFIG environment variable
    3. config.toml next to this file, else config.example.toml
    Keeping a character's config in its own folder (outside the repo) is how
    you run a private character on the public engine."""
    for arg in sys.argv[1:]:
        if arg.startswith("--config="):
            return Path(arg.split("=", 1)[1]).expanduser().resolve()
    if os.environ.get("ASSISTANT_CONFIG"):
        return Path(os.environ["ASSISTANT_CONFIG"]).expanduser().resolve()
    own = HERE / "config.toml"
    return own if own.exists() else HERE / "config.example.toml"


CONFIG_FILE = _find_config()
CFG = tomllib.loads(CONFIG_FILE.read_text())
BASE = CONFIG_FILE.parent          # relative paths in a config are relative to it


def path(value):
    """'~/x' -> /home/you/x ; 'journal' -> <folder of the config file>/journal."""
    p = Path(value).expanduser()
    return p if p.is_absolute() else BASE / p


MODEL = CFG["assistant"]["model"]
# Empty watcher_model = single-model mode: the main model also breaks routing
# ties (it's already loaded on the GPU, so no second model, no swapping).
WATCHER_MODEL = CFG["assistant"].get("watcher_model") or MODEL
CONTEXT_TOKENS = CFG["assistant"]["context_tokens"]
TEMPERATURE = CFG["assistant"].get("temperature", 0.6)   # lower = steadier, less invention
PLACE = CFG["assistant"].get("place", "")

USER_NAME = CFG["user"]["name"]
TEASE_NAME = CFG["user"].get("tease_name", "kid")
USER_NOTES = [path(n) for n in CFG["user"].get("notes", [])]

CHARACTER_DIR = path(CFG["character"]["dir"])
JOURNAL_DIR = path(CFG["memory"]["journal_dir"])
JOURNAL_DAYS = CFG["memory"].get("journal_days", 3)
NOTES_DIR = path(CFG["tools"]["notes_dir"])
# Extra tool folders (same shelf layout as tools/), e.g. private tools that
# should never go into the public repo.
EXTRA_TOOL_DIRS = [path(d) for d in CFG["tools"].get("extra_dirs", [])]
# Write the prompt by hand with the system prompt first, for models whose
# Ollama template puts it last (kills caching). "auto" = only mistral-nemo,
# the one we measured; other models are checked by the eval's timings.
RAW_PROMPT = CFG["assistant"].get("raw_prompt", "auto")

# What happens when a tool runs:
#   "character" = the model reads the result and answers in character
#   "raw"       = the tool's output is printed as is, instantly, no model call
#                 (for a plain assistant: a status check shouldn't wait on a story)
TOOL_OUTPUT = CFG["tools"].get("output", "character")

# Skills: how-to notes (and reviewed scripts) the assistant writes for itself.
_skills = CFG.get("skills", {})
SKILLS_DIR = path(_skills.get("dir", "skills"))
SKILLS_AUTO = _skills.get("auto_draft", False)        # draft one on /quit if something worked
SKILLS_REVIEWER = _skills.get("reviewer", "claude -p --tools '' --no-session-persistence")
EXTRA_TOOL_DIRS.append(SKILLS_DIR / "tools")          # approved learned scripts

# self.md: who the assistant has become, rewritten from the journal now and
# then. Short on purpose (capped), so it gets condensed instead of growing.
SELF_FILE = path(CFG["memory"]["self_file"]) if CFG["memory"].get("self_file") else None
SELF_MAX_CHARS = CFG["memory"].get("self_max_chars", 1500)


def character_name():
    """First line of persona.txt is 'You are <Name>: ...'; pull the name out."""
    first = (CHARACTER_DIR / "persona.txt").read_text().split("\n", 1)[0]
    return first.removeprefix("You are ").split(":")[0].split(",")[0].strip() or "Ghost"
