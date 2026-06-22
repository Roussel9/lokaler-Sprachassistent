from stt.recorder import aufnehmen_bis_stille
from stt.transcriber import VoskTranskriberer

tts = VoskTranskriberer("models/vosk-model-small-de-0.15")
audio = aufnehmen_bis_stille()
text = tts.transkribiere(audio)
print(f"Erkannt: {text}")