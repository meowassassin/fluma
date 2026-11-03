# Quick start

Fluma runs locally: a web Studio (Node) plus a Python pipeline. About 10 minutes on a fresh Linux machine.

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
git clone <this repo> fluma && cd fluma
python3 scripts/doctor.py --fix
```

`doctor.py` creates `.venv`, installs the Python packages (`scripts/requirements.txt`), downloads Chromium for
rendering, and runs `npm install` for the web app and the HyperFrames engine. It only *tells* you how to install
Node / ffmpeg — it does not need admin rights.

Profiles:

| Profile | Adds | Command |
|---|---|---|
| `lite` (default) | storyboard · free Edge voice · HyperFrames · render · checks | `python3 scripts/doctor.py --fix` |
| `analysis` | reference analysis: transcription, OCR, CLIP shot tags | `--profile analysis` |
| `full` | background removal, YouTube upload | `--profile full` |

## 3. Run

```bash
npm --prefix web run dev     # API on 127.0.0.1:4310, Studio on http://localhost:4311
```

Open the Studio, type a topic (or paste a reference Short URL) on Home, and plan the video in chat.

## Docker

```bash
docker compose up --build
```

Then open http://localhost:4311. Your agent CLI login is not inside the container — use an API key in Settings.

## Check · troubleshoot

```bash
python3 scripts/doctor.py           # what is installed and what is missing
python3 scripts/doctor.py --sizes   # what takes disk space and what is safe to delete
python -m pytest tests              # core tests
```

- **No sound in renders** — the default voice may be *Silent (for testing)*; pick a voice in Settings → Media → Voice.
- **Free 2D models hit a quota** — add a free Hugging Face token in Settings → Media → 2D generation.
- **Tested only on Linux** — on macOS / Windows please open an issue with the `doctor.py` output.
