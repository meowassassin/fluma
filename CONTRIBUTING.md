# Contributing to Fluma

**English** · [한국어](CONTRIBUTING.ko.md)

**Come as you are.** Fork it, change it, break it, make it yours. Pull requests, new features, wild experiments,
small fixes, typo fixes, translations, bug reports and half-baked ideas are all welcome — you don't need to ask first.

Fluma is Apache-2.0, so you're also free to use and modify it in your own projects, commercial or not.

## Ways to jump in

- 🐛 **Found something odd?** Open an issue — even "this felt confusing" is useful.
- 💡 **Have an idea?** Open an issue or just send a draft PR. Rough is fine; we can shape it together.
- 🔧 **Want to build something?** Anything goes. A few easy entry points if you want them:

| Idea | Where |
|---|---|
| connect another Craft app (or any tool) as a material maker | `crafts/<app>/craft.json` (`provides`) + an adapter in `scripts/craft/materials.py` |
| better motion for a material type | `scripts/craft/motion.py` (`material_jsx`) |
| a new voice engine | `voices/<name>/` — `voice.json` + `adapter.py` |
| a free 2D / motion model | `genmodels/<name>/model.json` |
| a format preset measured from Shorts you like | `scripts/ref_channel.py` → `scripts/format_presets.py build` |
| a smarter check | `scripts/lint.py`, `scripts/tempo_check.py`, `scripts/edit_density.py` |
| more YouTube analytics | `web/youtube.mjs`, `web/src/features/studio/PublishView.tsx` |
| your language in the UI | `web/src/i18n/*.ts` (the Korean string is the key) |
| docs, examples, demo Shorts | anywhere — README, `docs/`, a new folder, your call |

## Sending a PR

Open it whenever you like — draft PRs are great. If you have a minute, running these first helps:

```bash
python -m pytest tests
npx tsc --noEmit -p web
```

If they fail and you're not sure why, send it anyway and say so; we'll figure it out together.

## A few things we care about (not rules, just taste)

- Study real Shorts before making one — numbers from real Shorts beat hand-tuned magic values.
- Real material over generated guesses — on-screen facts are nicer with a source.
- If something looks wrong, fixing the engine or a check usually helps more than patching one output.
- Render it and look at the frames before calling it done.
- Please keep API keys, OAuth tokens and private data (storyboards, uploads, analytics) out of commits and logs.

Thanks for being here. 💜
