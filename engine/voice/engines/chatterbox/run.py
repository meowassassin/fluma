import json, sys
import torchaudio as ta
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
q = json.load(open(sys.argv[1], encoding="utf-8"))
m = ChatterboxMultilingualTTS.from_pretrained(device="cpu")
wav = m.generate(q["text"], language_id="ko")
ta.save(q["out"], wav, m.sr)
