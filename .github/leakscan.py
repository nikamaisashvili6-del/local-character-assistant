#!/usr/bin/env python3
"""Leak scan: fails if a file about to be published holds something personal.

Always checks: home paths, private-network IPs, e-mail addresses, API keys / tokens, private keys.
Extra words come from --words "a,b,c" or the LEAK_WORDS environment variable (in CI: a repository
secret, so the list itself is never public) and from --settings (your config/settings.json + codename,
used by the local export). Matching is whole-word and case-insensitive.

usage: leakscan.py <dir> [--words a,b] [--settings config/settings.json] [--codename config/codename]
exit 0 = clean, 1 = leaks found (each printed as file:line: what)
"""
import argparse, json, os, re, sys
from pathlib import Path

GENERIC = {
    "home path": r"/home/(?!runner\b|user\b|you\b)[a-z_][\w-]*|/Users/(?!you\b)[A-Za-z][\w-]*",
    "private IP": r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b",
    "e-mail": r"\b[\w.+-]+@(?!users\.noreply\.github\.com|anthropic\.com|example\.(?:com|org))[\w-]+\.[\w.]+\b",
    "token": r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|xox[abp]-[\w-]{10,})\b",
    "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
}
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__"}
SKIP_EXT = {".png", ".jpg", ".ico", ".onnx", ".bin", ".woff", ".woff2"}


def words_from_settings(settings, codename):
    """Every personal value in settings.json becomes a forbidden word (short/common ones skipped)."""
    out = set()
    if settings and Path(settings).exists():
        s = json.loads(Path(settings).read_text())
        for key in ("user", "place", "vault", "vault_name", "mode_name", "services_title"):
            v = s.get(key)
            if isinstance(v, str):
                out |= {w for w in re.split(r"[\s,/~]+", v) if len(w) > 3}
        for unit, label in s.get("services", []) + s.get("user_services", []):
            out |= {unit, label}
        out |= set(s.get("hints", [])) | set(s.get("aliases", {}))
        for k, (title, hint) in s.get("sources", {}).items():
            out |= {p for p in re.split(r"[/:\s,]+", k + " " + title) if len(p) > 3}
        for rx, rep in s.get("heard", []) + s.get("tidy", []):
            out |= {w for w in re.findall(r"[A-Za-z]{3,}", rep)}
    if codename and Path(codename).exists():
        out.add(Path(codename).read_text().strip())
    common = {"Linux", "nginx", "Postgres", "postgresql", "Ollama", "ollama", "Documents", "online", "server",
              "talk", "radios", "Yours", "private", "tools", "shared", "notes", "with", "services",
              "assistant", "Assistant", "stack", "characters", "backup", "Linux,"}
    common = {c.lower() for c in common}
    return {w for w in out if len(w) >= 3 and w.lower() not in common}


def scan(root, words):
    pats = {k: re.compile(v) for k, v in GENERIC.items()}
    if words:
        pats["personal word"] = re.compile(r"(?<![\w])(?:" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")(?![\w])", re.I)
    hits = []
    for f in sorted(Path(root).rglob("*")):
        if f.is_dir() or SKIP_DIRS & set(f.parts) or f.suffix.lower() in SKIP_EXT or f.name == "package-lock.json":
            continue
        try:
            lines = f.read_text(errors="strict").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(lines, 1):
            for what, rx in pats.items():
                m = rx.search(line)
                if m:
                    hits.append(f"{f.relative_to(root)}:{i}: {what}" + ("" if what == "personal word" and os.environ.get("CI") else f" ({m.group(0)[:40]})"))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--words", default=os.environ.get("LEAK_WORDS", ""))
    ap.add_argument("--settings")
    ap.add_argument("--codename")
    a = ap.parse_args()
    words = {w.strip() for w in a.words.split(",") if w.strip()} | words_from_settings(a.settings, a.codename)
    hits = scan(a.dir, words)
    for h in hits:
        print(h)
    print(f"leak scan: {len(hits)} problem(s), {len(words)} personal words checked" if hits else
          f"leak scan: clean ({len(words)} personal words checked)")
    sys.exit(1 if hits else 0)


if __name__ == "__main__":
    main()
