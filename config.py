"""
config.py: loads config.toml (or config.example.toml if you haven't made one).

Everything personal (your name, your notes, where the journal goes) lives in
the config file, so the code itself never has to change.
"""

import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
_file = HERE / "config.toml"
if not _file.exists():
    _file = HERE / "config.example.toml"
CFG = tomllib.loads(_file.read_text())


def path(value):
    """'~/x' -> /home/you/x ; 'journal' -> <project>/journal."""
    p = Path(value).expanduser()
    return p if p.is_absolute() else HERE / p


MODEL = CFG["assistant"]["model"]
WATCHER_MODEL = CFG["assistant"]["watcher_model"]
CONTEXT_TOKENS = CFG["assistant"]["context_tokens"]
PLACE = CFG["assistant"].get("place", "")

USER_NAME = CFG["user"]["name"]
TEASE_NAME = CFG["user"].get("tease_name", "kid")
USER_NOTES = [path(n) for n in CFG["user"].get("notes", [])]

CHARACTER_DIR = path(CFG["character"]["dir"])
JOURNAL_DIR = path(CFG["memory"]["journal_dir"])
JOURNAL_DAYS = CFG["memory"].get("journal_days", 3)
NOTES_DIR = path(CFG["tools"]["notes_dir"])


def character_name():
    """First line of persona.txt is 'You are <Name>: ...'; pull the name out."""
    first = (CHARACTER_DIR / "persona.txt").read_text().split("\n", 1)[0]
    return first.removeprefix("You are ").split(":")[0].split(",")[0].strip() or "Ghost"
