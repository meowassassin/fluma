import json, sys
from supertonic import TTS
q = json.load(open(sys.argv[1], encoding="utf-8"))
tts = TTS(auto_download=True)
style = tts.get_voice_style(voice_name=q["voice"])
wav, _ = tts.synthesize(text=q["text"], voice_style=style, total_steps=10, speed=max(0.7, min(2.0, 1.05 * q["speed"])), lang="ko")
tts.save_audio(wav, q["out"])
