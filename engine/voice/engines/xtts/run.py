import json, os, sys
os.environ.setdefault("COQUI_TOS_AGREED", "1")   # 설치할 때 사용자가 CPML(비상업)에 동의함
from TTS.api import TTS
q = json.load(open(sys.argv[1], encoding="utf-8"))
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cpu")
tts.tts_to_file(text=q["text"], speaker=q["voice"], language="ko", file_path=q["out"], speed=q["speed"])
