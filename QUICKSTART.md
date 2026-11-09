# Quick start

**English** · [한국어](QUICKSTART.ko.md)

Fluma runs locally: a web Studio (Node) plus a Python pipeline, driving the open-source Craft apps.

## Pick a path

| You want | Use | Time |
|---|---|---|
| Let your own agent do it | Give Claude Code or Codex: *Use this skill: https://raw.githubusercontent.com/meowassassin/fluma/main/docs/skill/SKILL.md — make a Short about "…"* | hands-off |
| The easiest start, any OS (Linux · macOS · Windows) | [Docker](#docker) — two commands, everything included | download ~15 GB, once |
| To run it directly on your machine | [Install](#2-install) — `doctor.py --fix` | ~10 min + downloads |
| To change Fluma itself | Install, then `npm --prefix studio run dev` and the [tests](#check--troubleshoot) | — |

Either way you need an agent: a logged-in **Claude Code** or **Codex** CLI on your computer (Docker reuses that login),
or an API key (Anthropic, OpenAI, OpenRouter, Gemini, or a local Ollama) entered in **Settings → Models · Providers**.

### What your computer needs

| | Docker | Direct install |
|---|---|---|
| Disk | about 15 GB (image) + your videos | about 6 GB (.venv 1.3 · Craft apps 3.6 · models ~1 · Chromium 0.7) |
| Memory | 8 GB or more (tested on 16 GB) | same |
| CPU | any 64-bit; analysis and rendering use every core (tested on 8 cores) | same |
| GPU | not needed | not needed |

Smaller: `PROFILE=lite CRAFTS=core MODELS=0 docker compose build`, or `doctor.py --fix --profile lite --core` — missing pieces install themselves on first use.

## 1. Requirements

| Tool | Version | Install |
|---|---|---|
| Python | 3.10+ | your package manager, or [python.org](https://www.python.org) |
| Node.js | 20+ | [nodejs.org](https://nodejs.org) |
| ffmpeg | any recent | `sudo apt install ffmpeg` · `sudo dnf install ffmpeg` · `brew install ffmpeg` · `winget install ffmpeg` |

You also need an agent: a logged-in **Claude Code** or **Codex** CLI, or an API key (Anthropic, OpenAI, OpenRouter,
Gemini, or a local Ollama) entered later in **Settings → Models · Providers**.

## 2. Install

```bash
git clone https://github.com/meowassassin/fluma && cd fluma
python3 engine/doctor.py --fix
```

That one command installs **everything**: `.venv` with all Python packages (`requirements-full.txt`), Chromium,
all 16 open-source [Craft apps](https://github.com/storytold) (MIT / Apache-2.0, about 1.4 GB, checked against their
SHA256SUMS into `tools/crafts/`), the analysis and background-removal models, and the npm packages. It only *tells*
you how to install Node / ffmpeg — it does not need admin rights.

Short on disk? `python3 engine/doctor.py --fix --profile lite --core` installs the minimum (7 core Craft apps, no
models); anything missing is installed automatically the first time it is used.

## 3. Run

```bash
npm --prefix studio run dev     # API on 127.0.0.1:4310, Studio on http://localhost:4311
```

If it says the Studio packages are missing, step 2 (`doctor.py --fix`) was skipped — run `npm --prefix studio install` once and start again. Same command on Windows, macOS and Linux.


Open the Studio, type a topic on Home and plan the video in chat. Press **Start production** when the storyboard
looks right — the agent studies reference Shorts, builds the scenes and renders a draft. The editor's Explorer shows
what the video is made of; ask the agent on the right to change anything.

### Where your files are

| What | Where (direct install) | Docker |
|---|---|---|
| Finished videos | `data/out/<id>-….mp4` | volume `fluma_out` |
| Storyboards | `data/storyboards/<id>.json` | volume `fluma_storyboards` |
| Editable projects (EffectCraft · SoundCraft · FilmCraft) | `data/compositions/<id>/craft/` | volume `fluma_compositions` |
| Reference analysis | `data/public/trends/` | volume `fluma_trends` |
| API keys · YouTube login | `~/.shortsforge/` (0600, never in the repo, the agent cannot read it) | volume `fluma_keys` |

Easiest on any setup: **Download** next to **Render** in the editor saves any render to your computer, named after the video title. From the terminal (Docker): `docker compose cp fluma:/app/data/out ./videos`.

The agent shows images, stills and videos right in the chat — you should not have to look for files.

### Update

```bash
git pull
python3 engine/doctor.py --fix                   # direct install: new packages · Craft app versions
(cd docker && docker compose pull && docker compose up -d)   # Docker: your work stays in the volumes
```

## 3-1. OpenRouter key (optional)

You don't need it — a video comes out end to end on the free local path. With a key, pick a model per capability in **Settings → See · Make · Speak**:
reference video understanding and draft critique (on by default once a key is set), paid voices, transcription and embeddings. There is no image or video generation (every frame is made locally). Lists and prices come from OpenRouter.
Within the per-video cap (default $3) nothing asks; above it, or when a price can't be estimated, the agent shows the amount and asks. Spending shows on the same screen.
An OpenRouter key saved in the agent settings (Models · Providers) is reused.

## 4. Connect YouTube (optional)

Upload and per-scene analytics need your own Google OAuth client — about 10 minutes, once:

1. [Google Cloud Console](https://console.cloud.google.com): create a project, enable **YouTube Data API v3** and **YouTube Analytics API**.
2. **Google Auth Platform** (OAuth consent screen): External, Testing; add your Google account under **Test users** (type it in lowercase).
3. **Clients → Create client → Web application**, authorized redirect URI `http://127.0.0.1:4310/api/youtube/callback` (exactly).
4. Studio → **Settings → YouTube**: paste the client ID and secret → **Save** → **Connect YouTube**, allow all three permissions.

Notes: in Testing mode Google may expire the login after 7 days — press Connect again. Videos uploaded through an
unverified app can be locked to Private; change it in YouTube Studio. Analytics fill in 1–2 days after publishing.

| Problem | Fix |
|---|---|
| `redirect_uri_mismatch` | the redirect URI must be exactly `http://127.0.0.1:4310/api/youtube/callback` |
| "Access blocked: app is in testing" | the account is not a test user of *this* project (the number at the start of the client ID is the project number) |
| "Ineligible account" when adding a test user | type the address in lowercase |

## Docker

The start script adapts to your OS and hardware (it attaches a GPU when there is one and falls back to the CPU otherwise — same result, only 3D renders are slower).

```bash
sh docker/start.sh                                              # Linux · macOS → http://localhost:4311
powershell -ExecutionPolicy Bypass -File docker\start.ps1        # Windows
```

It pulls the prebuilt image (~15 GB, once). To build it yourself: `sh docker/start.sh --build` (~15 min) or `docker\start.ps1 -Build`.
Stop: `cd docker && docker compose down`. Other Docker commands also run in the `docker/` folder (where `docker-compose.yml` lives).
Any CPU works: the image is published for both Intel/AMD (amd64) and Apple Silicon/ARM (arm64), and Docker pulls the right one.
GPU for 3D renders: on Linux the script attaches it automatically. Docker on macOS and Windows cannot pass the GPU into a container, so renders run on the CPU — if you need the GPU there, use the direct install below (it uses that computer's GPU as is).

That's it. The agent uses your own Claude Code and Codex logins (`~/.claude`, `~/.codex`), work persists in Docker
volumes, and the image already contains everything (all Python packages, all 16 Craft apps, the analysis models).
For a smaller image: `PROFILE=lite CRAFTS=core MODELS=0 docker compose build`.

If Docker is not installed: [Docker Desktop](https://www.docker.com/products/docker-desktop/) (macOS · Windows), or Docker Engine on Linux.
On Windows, Docker Desktop uses WSL 2 — [install WSL](https://learn.microsoft.com/windows/wsl/install) first if it asks.

<details><summary>Troubleshooting</summary>

- **`Bind for 127.0.0.1:4311 failed: port is already allocated`** — another Fluma (or dev server) is running. `docker ps` shows which; stop it with `docker compose down` in *its* folder, or stop the dev server.
- **`service "fluma" is not running`** — you ran the command in a different folder from the one you started Fluma in (compose names projects by folder). Run it in the `docker/` folder, or use `docker ps` to find the container name.
- **Agent says it is not logged in** (e.g. Claude Code on macOS keeps its login in the Keychain): `docker compose exec -it fluma claude` → `/login` once.
- **Files created by the container belong to another user (Linux)** — if `id -u` is not 1000, set `FLUMA_UID=…` and `FLUMA_GID=…` in `.env` and rebuild.

</details>

## Check · troubleshoot

```bash
python3 engine/doctor.py           # what is installed and what is missing
python3 engine/doctor.py --sizes   # what takes disk space and what is safe to delete
python3 engine/craft/crafts.py list      # which Craft apps are installed
python -m pytest tests              # core tests
```

- **`ffmpeg: command not found`** — install it with your OS package manager (table above); `doctor.py` prints the exact command.
- **Model download fails (Hugging Face)** — check the network and run `python3 engine/core/prefetch_models.py` again; it retries only what is missing.
- **No sound in renders** — the default voice may be *Silent (for testing)*; pick a voice in Settings → Media → Voice.
- **Windows: Korean text errors when running scripts yourself** — turn on Python UTF-8 mode once: `setx PYTHONUTF8 1` (new terminal after). The Studio already runs scripts that way.
- **Tested by CI on Linux, macOS and Windows** (install, tests, web build, server, a Craft app) — real use is mostly on Linux so far; please open an issue with the `doctor.py` output if something breaks.
