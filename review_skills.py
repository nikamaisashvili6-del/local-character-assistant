#!/usr/bin/env python3
"""
review_skills.py: check the skill drafts the assistant wrote, one by one.

For each draft in skills/pending/:
  1. show it
  2. hand it to the reviewer command (default: `claude -p` with NO tools, so
     it can only read the text, never run anything) and show the verdict
  3. you decide:  a = approve   f = approve the reviewer's fixed version
                  r = reject    s = skip for now

Run:  ./review_skills.py [--config=...]        (same config as the assistant)
      ./review_skills.py --no-reviewer         (just you, nothing leaves the PC)

Privacy: with the reviewer on, the DRAFT text is sent to it. Only the draft,
never your chats or notes.
"""

import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config   # noqa: E402
import skills   # noqa: E402

DIM, BOLD, RESET = "\033[2m", "\033[1m", "\033[0m"

REVIEW_PROMPT = """You are reviewing a "skill" that a small local AI assistant wrote for
itself. If approved, the notes get pasted into its prompt later, and a ```bash
block becomes a script that runs on the user's Linux PC (it asks y/N first).

Check:
- Is it safe? Nothing destructive (rm -rf, dd, chmod 777, curl | sh, deleting
  data, sending data anywhere, disabling security) unless clearly intended.
- Does the script look like it would actually work? Real commands, sane flags.
  It runs WITHOUT a terminal: no sudo, no password prompts, nothing interactive.
  sudo steps belong in the numbered notes (the user runs those), not the script.
- Is it useful and specific, not vague or invented filler?
- Keywords: specific enough that it won't fire on normal chat?
- An alias ("say: X" / "do: Y") rewrites X into Y before tools are picked. Is X
  specific enough not to hit normal sentences? Is Y a short plain command?

Answer in this format:
VERDICT: APPROVE or REJECT
WHY: 1 to 3 short lines
If small fixes would make it good, add the full corrected skill after a line
FIXED:
and nothing after it.

The draft:
"""


def review(text):
    """Run the reviewer command on one draft. Returns its answer (or an error line)."""
    cmd = shlex.split(config.SKILLS_REVIEWER)
    try:
        out = subprocess.run(cmd + [REVIEW_PROMPT + text], capture_output=True, text=True,
                             timeout=300)
        return (out.stdout or out.stderr).strip() or "(reviewer said nothing)"
    except FileNotFoundError:
        return f"(reviewer not found: {cmd[0]})"
    except subprocess.TimeoutExpired:
        return "(reviewer timed out)"


def main():
    drafts = skills.pending()
    if not drafts:
        print("no skill drafts waiting")
        return
    use_reviewer = "--no-reviewer" not in sys.argv
    for path in drafts:
        text = path.read_text()
        print(f"\n{BOLD}── {path.name} ──{RESET}\n{text}")
        fixed = None
        if use_reviewer:
            print(f"{DIM}  [asking the reviewer...]{RESET}")
            verdict = review(text)
            print(f"{BOLD}reviewer:{RESET}\n{verdict}\n")
            path.with_suffix(".review.txt").write_text(verdict + "\n")
            m = re.search(r"^FIXED:\s*\n(.*)", verdict, re.S | re.M)
            if m and skills.parse(m.group(1))["name"]:
                fixed = m.group(1).strip() + "\n"
        options = "a=approve" + (" f=approve fixed" if fixed else "") + " r=reject s=skip"
        choice = input(f"{BOLD}{options} ▸ {RESET}").strip().lower()
        if choice in ("a", "f"):
            made = skills.install(path, fixed if choice == "f" and fixed else None)
            for p in made:
                print(f"  ✓ {p}")
        elif choice == "r":
            print(f"  ✗ moved to {skills.reject(path, input('  reason (optional): ').strip())}")
        else:
            print("  skipped")
        review_file = path.with_suffix(".review.txt")
        if not path.exists() and review_file.exists():
            review_file.unlink()                      # verdict only matters while pending


if __name__ == "__main__":
    main()
