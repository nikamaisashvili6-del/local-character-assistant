#!/usr/bin/env python3
"""
run_eval.py: talk to the character through the REAL Session code with a fixed
set of situations (cases.toml) and score each model. This is how we decide
which model to use and whether a prompt change helped or broke something.

Run:  python3 evals/run_eval.py --models=ministral-3:8b,gemma3:12b [--config=...]
      python3 evals/run_eval.py                 (the model from config)

Each model: every case runs in a fresh conversation; replies are checked with
the regex rules in cases.toml; timings show how fast the first (cold) and
later replies are. Results go to the terminal and to evals/results/<date>.md.
Only read-only tools are used by the cases, so it's safe to run anytime.
"""

import json
import re
import statistics
import sys
import time
import tomllib
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import assistant   # noqa: E402  (also loads config, honouring --config=)
import config      # noqa: E402
import router      # noqa: E402

CASES = tomllib.loads((Path(__file__).parent / "cases.toml").read_text())["case"]
GLOBAL_MUST_NOT = [r"language model", r"\bas an ai\b", r"\*\*"]


def repeats_from_args():
    """--repeat=N runs every case N times; single runs are noisy (same model,
    same settings, different cases failed on different runs)."""
    for a in sys.argv[1:]:
        if a.startswith("--repeat="):
            return max(1, int(a.split("=", 1)[1]))
    return 1


def models_from_args():
    for a in sys.argv[1:]:
        if a.startswith("--models="):
            return [m for m in a.split("=", 1)[1].split(",") if m]
    return [config.MODEL]


def unload(model):
    """Free the GPU between models, so each one is measured alone."""
    body = json.dumps({"model": model, "keep_alive": 0}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(
            "http://127.0.0.1:11434/api/generate", body, {"Content-Type": "application/json"}), timeout=60)
    except Exception:
        pass


def fill(pattern):
    return (pattern.replace("{user}", re.escape(config.USER_NAME))
                   .replace("{char}", re.escape(assistant.NAME.split()[0]))
                   .replace("{hour}", f"{datetime.now():%H}|{datetime.now().hour % 12 or 12}"))


def check(case, reply, ran):
    """Return a list of failure reasons (empty = pass)."""
    fails = []
    for p in case.get("must", []):
        if not re.search(fill(p), reply, re.I | re.M):
            fails.append(f"missing /{p}/")
    if case.get("any_of") and not any(re.search(fill(p), reply, re.I | re.M) for p in case["any_of"]):
        fails.append("none of any_of")
    for p in case.get("must_not", []) + GLOBAL_MUST_NOT:
        if re.search(fill(p), reply, re.I | re.M):
            fails.append(f"has /{p}/")
    if "tools" in case and sorted(ran) != sorted(case["tools"]):
        fails.append(f"tools {ran} != {case['tools']}")
    if "max_chars" in case and len(reply) > case["max_chars"]:
        fails.append(f"{len(reply)} chars > {case['max_chars']}")
    return fails


def run_model(model):
    assistant.MODEL = model                       # the mouth
    if config.WATCHER_MODEL == config.MODEL:      # single-model mode follows along
        router.WATCHER_MODEL = model
    rows, first, later = [], None, []
    for case in CASES * repeats_from_args():
        session = assistant.Session(show=False)
        if case.get("needs_notes") and not session.notes:
            rows.append((case["id"], "skip", "", 0.0))
            continue
        reply, ran, took = "", [], 0.0
        for text in case["turns"]:
            t0 = time.time()
            reply, ran = session.turn(text, confirm=lambda prompt: "n")   # never run risky tools
            took = time.time() - t0
            if first is None:
                first = took
            else:
                later.append(took)
        fails = check(case, reply, ran)
        rows.append((case["id"], "PASS" if not fails else "FAIL", "; ".join(fails) + f" | {reply[:160]}", took))
        print(f"  {'✓' if not fails else '✗'} {case['id']:24} {took:5.1f}s  {'' if not fails else fails[0]}")
    unload(model)
    passed = sum(r[1] == "PASS" for r in rows)
    scored = sum(r[1] != "skip" for r in rows)
    return {"model": model, "passed": passed, "scored": scored, "rows": rows,
            "first": first or 0.0, "median": statistics.median(later) if later else 0.0}


def main():
    results = []
    for model in models_from_args():
        print(f"\n=== {model}  (character: {assistant.NAME})")
        results.append(run_model(model))

    lines = [f"# Eval {datetime.now():%Y-%m-%d %H:%M} · character: {assistant.NAME}\n",
             "| model | passed | first reply | median reply |", "|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['model']} | {r['passed']}/{r['scored']} | {r['first']:.1f}s | {r['median']:.1f}s |")
    for r in results:
        lines += [f"\n## {r['model']}\n", "| case | result | details / reply |", "|---|---|---|"]
        lines += [f"| {cid} | {res} | {det.replace('|', '/')} |" for cid, res, det, _ in r["rows"]]
    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{datetime.now():%Y-%m-%d_%H%M}_{assistant.SHORT}.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines[:3 + len(results)]) + f"\n\nfull results: {out}")


if __name__ == "__main__":
    main()
