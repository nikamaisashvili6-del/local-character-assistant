# local-character-assistant

A character AI that lives in your terminal **and can actually do things** on your computer: control music, open apps, search the web and your notes, set reminders. Everything runs **locally** on [Ollama](https://ollama.com), so your data never leaves your machine.

It ships with an original character, **Rook Malone**: a 90s punk frontman whose mind a fan rebuilt from tour tapes and diaries, who now haunts your PC. Swap in your own character by editing two text files.

```
  ▓▒░ ROOK MALONE ░▒▓
  online · model: mistral-nemo · knows you · 17 tools · /tools /reset /quit

you ▸ hey rook
rook ▸ What's the static?

you ▸ thinking of starting another side project
rook ▸ Another side project? You're not still working on the last one? Finish that first, then we'll talk about new.

you ▸ asdkjh
rook ▸ Fell asleep on the keyboard again, Alex?

you ▸ check my calendar
rook ▸ Can't reach that, Alex. What's today's plan?
```
*(Real replies from a test session. Tool calls show up as `⚙ desktop/music/pause` lines before the reply.)*

## Why it's built this way

Small local models (3–12B) are great at *talking* and bad at *reliably choosing tools*. Ask one model to do both and it either breaks character or calls the wrong tool. So the work is split:

```
 you ──► WATCHER (router.py)     small model + keyword dictionary
          "does this need a tool?"  walks a tree of tool folders
              │ yes → runs the script(s), collects their output
              ▼
         MOUTH (assistant.py)     big model, in character
          your words + tool results → answers in the character's voice
              │
              ▼ on /quit
         MEMORY (brain.py)        journal of key points, reread next session
```

| Part | Model | Job |
|---|---|---|
| **Watcher** | keyword dictionary, then `llama3.2:3b` on CPU only for ties | pick the tool(s) |
| **Hands** | plain bash / Python scripts | do the thing |
| **Mouth** | `mistral-nemo` 12B (or any Ollama model) on GPU | talk |
| **Memory** | the mouth model, at the end of a session | write the journal |

## How the pieces work

### The tool tree ("bookshelf" router)
Tools are just executable scripts in folders. Each folder is a "shelf" with a `_shelf.txt` (description + keywords); each script has a small header:

```bash
#!/bin/bash
# desc: pause / stop the Spotify music
# keywords: pause, stop, off, kill, shut, silence, enough
# confirm: no
```

Routing a message:
1. **Split** compound requests: "pause the music and lock the screen" becomes two tasks. A part that lost its verb borrows it ("open vs code and file manager").
2. **Dictionary score:** a tool only fires if the message has a **shelf word** (*music*) **and** an **action word** (*pause*). "I love that song" mentions music but asks for nothing, so it stays a chat.
3. **Tie-break:** only if two tools score the same does the small model choose, and only between those few. A 3B model gets "pick 1 of 2" right; "pick 1 of 40" it gets wrong.
4. Tools marked `confirm: yes` ask `[y/N]` before running.

**Adding a power = dropping a script into a folder.** No code changes.

### Memory
- **Lorebook:** `character/lore.md` is split into sections with `triggers:` words. A section is only sent to the model when one of its words comes up, so the character can have a big backstory without filling the context window.
- **Rolling summary:** long chats get condensed into a "story so far" instead of being forgotten.
- **Journal:** on `/quit` the character writes 3–5 bullets about the session in its own voice (point `journal_dir` at an Obsidian vault if you like) and rereads the last few days on startup.
- **Your notes:** list markdown files about yourself in `config.toml` and the character knows who you are.

### Guardrails against making things up
Small models love to pretend. Things that were added after watching it fail:
- **No-tool notice:** if a message *starts* like a command ("check my calendar") and no tool ran, the request is quoted back with "you have no tool for that". Without this, the model happily reported an empty calendar it had never seen.
- **Tool results are labelled** "this is ALL that actually happened". Without this, it announced a song title when Spotify had only opened a search.
- **Time with a part-of-day word**, so it can't decide it's 3am because your notes say you're a night owl.
- Name-openers ("Kid, ...") and copied example labels are trimmed in code, because the model ignores the rule against them.

### The speed fix: 50 s → 3 s per reply
Ollama's built-in prompt template for Mistral models places the system prompt **right before the latest user message**. With a ~3000-token persona, that means the whole prompt changes every turn and gets re-read from scratch: about 50 s per reply on an 8 GB GPU with part of the model on CPU.

`assistant.py` builds the Mistral prompt itself (`/api/generate` with `raw: true`) with the **fixed** part (persona, core lore, your notes, journal) first, and the **changing** part (time, triggered lore, tool results) attached to the newest message. Everything before the new message is now byte-for-byte identical between turns, so Ollama reuses its cache: **~30 s for the first reply, then ~3–7 s.**

## Setup

Requirements: Linux, Python 3.11+, [Ollama](https://ollama.com). Desktop tools assume GNOME-ish tools (`playerctl`, `wpctl`, `gtk-launch`, `gsettings`, `notify-send`, `systemd --user`); anything missing just makes that one tool fail politely.

```bash
git clone https://github.com/nikamaisashvili6-del/local-character-assistant
cd local-character-assistant
ollama pull mistral-nemo        # the mouth (~7 GB)
ollama pull llama3.2:3b         # the watcher (~2 GB)
cp config.example.toml config.toml   # your name, notes, journal folder
./assistant.py
```

Inside: `/tools` lists what it can do, `/reset` wipes the conversation, `/quit` writes the journal and exits. `./assistant.py --blind` starts it knowing nothing about you; `./assistant.py llama3.2:3b` tries another model.

Hardware it was built on: RTX 5060 8 GB, 14 GB RAM. `mistral-nemo` spills about a third onto the CPU at 8k context, and that's fine.

## Make your own character
Edit `character/persona.txt` (who they are, how they talk, **example dialogues**: these matter more than descriptions) and `character/lore.md` (their memories, with trigger words). `{user_name}` and `{tease_name}` are filled in from `config.toml`.

## Included tools (17)
Music (play / pause / next / previous / what's playing, via `playerctl`) · volume · open apps · Google search · YouTube · open a website · lock screen · dark/light mode · do-not-disturb · reminders and alarms (systemd user timers) · list/cancel reminders · PC health (disk, RAM, GPU) · notes search.

## Limits (honest)
- A 12B model still improvises: ask it to explain something it invented and it will double down with a story.
- One or two tools per message. Long multi-step agent tasks need a much bigger model.
- Spotify can't autoplay a search: "play X" opens the search and you pick the track.
- Reminders don't survive a reboot.

## Credits
Built by **Nika Maisashvili** ([@nikamaisashvili6-del](https://github.com/nikamaisashvili6-del)).
Ideas borrowed from character-AI apps (character cards, lorebooks) and from [Hermes Agent](https://github.com/NousResearch/hermes-agent) (file-based memory, a journal the agent writes itself).

License: MIT
