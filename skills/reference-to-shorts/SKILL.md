---
name: reference-to-shorts
description: Analyze a reference YouTube Short and its channel (structure, screen kinds, cut rhythm, music beat, tone, voice) and turn that grammar into a storyboard for the user's own topic. Use when the user shares a Shorts/Reels link and says "make mine like this". Works next to HyperFrames or Remotion skills.
---

# Reference → Shorts (Fluma)

Goal: copy the **grammar** of a reference channel, never its content. Footage, voice and script of the reference are
analysis material only.

## 1. Build the cards (Fluma repo, Python venv)

```bash
python3 scripts/shorts_xray.py <shorts-url>          # cuts, speech (word timing), music beats, layers
python3 scripts/ref_style.py <video-id>              # style card: format line, layout, captions, beat table, voice profile
python3 scripts/ref_channel.py <video-id> --n 5      # channel card from several Shorts of the same channel
```

Or call the MCP server `python3 scripts/mcp_server.py` → `analyze_reference(url, videos)`.

Read `public/trends/channels/<channel>/channel.md` top to bottom. The **format line** decides everything:
- *talk-led*: narration carries it — follow sentence-ending mix, connectives, joke beats, voice profile.
- *music-led*: no or minimal narration — match cut length and BPM, cut on beats.
- *screen kinds* (time ratio): real UI, article, person, footage, product, food, meme, illustration, text card, chart,
  game, 3D. Show the subject itself; keep article captures to the channel's share.

## 2. Confirm intent before producing

Write an intent card (summary · what to take from the reference · must · must_not) and get the user's OK. Every later
correction becomes one more `must` / `must_not` line — not a memory.

## 3. Storyboard

Order scenes by the channel skeleton; for each scene set `beat` (role) and `screen` (kind). Content is the user's topic,
with sourced facts. If the channel is Korean and talk-led, mix sentence endings in the channel's ratio.

## 4. Voice (if narrated)

```bash
python3 scripts/voice_match.py pick storyboards/<id>.json     # compare candidates on one cached sample
python3 scripts/voice_match.py tune storyboards/<id>.json     # emotion / intensity / pitch / phrase ending
python3 scripts/voice_match.py apply storyboards/<id>.json
python3 scripts/voice_match.py verify storyboards/<id>.json   # measure the FULL narration vs. reference
```

## 5. Check and gate

`python3 scripts/lint.py storyboards/<id>.json` (T21 screen mix · L21 article-heavy · T24 narration on music-led · T19
tone drift). Render scenes 1–3 as a draft, let the user approve (`scripts/gate.py draft`), then the final render or any
paid generation.

For tone-only edits use `scripts/tone_edit.py` — it refuses changes to content words.
