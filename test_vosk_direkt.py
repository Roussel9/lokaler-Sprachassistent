import sys
sys.path.insert(0, ".")

from stt.recorder import aufnehmen_bis_stille
from stt.transcriber import VoskTranskriberer

# Kleines Modell verwenden
transkriberer = VoskTranskriberer("models/vosk-model-de-0.21")

print("Sage jetzt etwas...")
audio = aufnehmen_bis_stille(max_dauer=5.0, stille_schwelle=300)

print(f"Audio Länge: {len(audio)} samples")
text = transkriberer.transkribiere(audio)
print(f"Erkannt: '{text}'")