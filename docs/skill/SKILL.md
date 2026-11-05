---
name: fluma-video
description: Use when the user wants to install or run Fluma, or wants a short-form explainer video made with Fluma from a topic (especially developer / IT topics shown with real screens — real command output, real code and official docs). Installs Fluma, starts the Studio and kicks off the first video's planning chat. Also use when the user gives this skill URL.
compatibility: Needs a terminal, git, network and either Docker or Python 3.10+ / Node.js 20+ / ffmpeg. Linux, macOS, Windows (Docker Desktop / WSL 2).
metadata:
  upstream: "https://github.com/meowassassin/fluma"
---

# Fluma — install, start, first video

Fluma is a local Shorts studio: an in-app agent (the user's own Claude Code or Codex login) plans with the user, studies
reference Shorts, records real screens, checks the result and renders editable Craft projects. Your job is to get it
running and hand the user a Studio with the first video already being planned. Do not try to make the video yourself.

## Required behavior
1. Do not ask for confirmation before cloning, installing or starting. Ask the user only for what the helper reports as missing (exit code 10), all at once.
2. Run the helper **once in the foreground** with a timeout of at least 60 minutes (the first Docker image is about 15 GB). Never poll with `sleep`, `ls`, `ps`, `tail`.
3. Read only the result block at the end of the output. Do not read logs after success.
4. Never print or ask the user to paste API keys or login tokens. Keys go into the Studio's Settings page.

## Steps
1. Get the code (or update it): `git clone https://github.com/meowassassin/fluma ~/fluma` — if it exists, `git -C ~/fluma pull`.
2. Run, with the working directory `~/fluma`:
   ```bash
   python3 scripts/fluma_agent.py start --topic "<the user's topic, if any>"
   ```
   It uses Docker when available (pulls the prebuilt image, builds only if that fails), otherwise installs everything locally
   (`scripts/doctor.py --fix`) and starts the dev server. Add `--local` to skip Docker.

## Exit codes
- **0** `FLUMA_RESULT` — `url=` (open this for the user) · `video=` (the new video id when a topic was given). Tell the user:
  the Studio is at that URL, the agent is already planning the video in the Home chat, and production starts when they press
  **Start production** after checking the storyboard. Finished videos: **Download** next to **Render** in the editor.
- **10** `FLUMA_NEEDS_INPUT` — `needs=` / `how=`: usually "log in to Claude Code or Codex once" (`claude` → `/login`) or a system
  program (ffmpeg, Node.js). Ask once, then rerun the same command.
- **1** `FLUMA_ERROR` — `stage=` / `error=`. Fix what the short error says (e.g. port 4311 used by another Fluma: stop it) and
  rerun once. If it fails again, report the stage and the short error.

## Scope
- One Fluma per machine (port 4311). Do not start a second copy.
- Do not edit Fluma's code or settings files to work around errors.
