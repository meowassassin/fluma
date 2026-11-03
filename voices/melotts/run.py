import json, sys
from melo.api import TTS
q = json.load(open(sys.argv[1], encoding="utf-8"))
m = TTS(language="KR", device="cpu")
m.tts_to_file(q["text"], m.hps.data.spk2id["KR"], q["out"], speed=q["speed"])
