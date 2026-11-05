# Quick start

**English** · [한국어](QUICKSTART.ko.md)

Fluma runs locally: a web Studio (Node) plus a Python pipeline, driving the open-source Craft apps. About 10 minutes on a fresh Linux machine (plus the Craft app download).

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
python3 scripts/doctor.py --fix
```

That one command installs **everything**: `.venv` with all Python packages (`requirements-full.txt`), Chromium,
all 16 open-source [Craft apps](https://github.com/storytold) (MIT / Apache-2.0, about 1.4 GB, checked against their
SHA256SUMS into `tools/crafts/`), the analysis and background-removal models, and the npm packages. It only *tells*
you how to install Node / ffmpeg — it does not need admin rights.

Short on disk? `python3 scripts/doctor.py --fix --profile lite --core` installs the minimum (7 core Craft apps, no
models); anything missing is installed automatically the first time it is used.

## 3. Run

```bash
npm --prefix web run dev     # API on 127.0.0.1:4310, Studio on http://localhost:4311
```

Open the Studio, type a topic on Home and plan the video in chat. Press **Start production** when the storyboard
looks right — the agent studies reference Shorts, builds the scenes and renders a draft. The editor's Explorer shows
what the video is made of; ask the agent on the right to change anything.

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

```bash
docker compose build
docker compose up -d            # → http://localhost:4311   (stop: docker compose down)
```

That's it. The agent uses your own Claude Code and Codex logins (`~/.claude`, `~/.codex`), work persists in Docker
volumes, and the image already contains everything (all Python packages, all 16 Craft apps, the analysis models).
For a smaller image: `PROFILE=lite CRAFTS=core MODELS=0 docker compose build`.

<details><summary>Troubleshooting</summary>

- Agent says it is not logged in (e.g. Claude Code on macOS keeps its login in the Keychain): `docker compose exec -it fluma claude` → `/login` once
- On Linux, if your user id (`id -u`) is not 1000, set `FLUMA_UID=…` and `FLUMA_GID=…` in `.env`

</details>

## Check · troubleshoot

```bash
python3 scripts/doctor.py           # what is installed and what is missing
python3 scripts/doctor.py --sizes   # what takes disk space and what is safe to delete
python3 scripts/crafts.py list      # which Craft apps are installed
python -m pytest tests              # core tests
```

- **No sound in renders** — the default voice may be *Silent (for testing)*; pick a voice in Settings → Media → Voice.
- **Free 2D models hit a quota** — add a free Hugging Face token in Settings → Media → 2D generation.
- **Windows: Korean text errors when running scripts yourself** — turn on Python UTF-8 mode once: `setx PYTHONUTF8 1` (new terminal after). The Studio already runs scripts that way.
- **Tested by CI on Linux, macOS and Windows** (install, tests, web build, server, a Craft app) — real use is mostly on Linux so far; please open an issue with the `doctor.py` output if something breaks.
