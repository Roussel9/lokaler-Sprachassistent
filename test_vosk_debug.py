"""
test_vosk_debug.py
Zeigt, was Vosk WIRKLICH erkennt + die Mikrofon-Lautstaerke.
"""

import json
import numpy as np
import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel

SetLogLevel(-1)

print("Lade Vosk...")
model = Model("models/vosk-model-small-de-0.15")
rec = KaldiRecognizer(model, 16000)
print("Bereit. Sprich jetzt (ca. 20s). Sag deutlich 'Computer'.\n")

with sd.InputStream(samplerate=16000, channels=1, dtype="float32") as stream:
    import time
    t0 = time.time()
    while time.time() - t0 < 20:
        block, _ = stream.read(800)
        audio = block.flatten()
        rms = float(np.sqrt(np.mean(audio ** 2)))
        pcm = (audio * 32767.0).astype("<i2").tobytes()

        if rec.AcceptWaveform(pcm):
            final = json.loads(rec.Result())
            txt = final.get("text", "")
            if txt:
                print(f"[RMS={rms:.3f}] FINAL: '{txt}'")
        partial = json.loads(rec.PartialResult())
        ptxt = partial.get("partial", "")
        # Zeige partials nur, wenn sie sich aendern UND laut genug ist
        if ptxt and rms > 0.005:
            print(f"[RMS={rms:.3f}] partial: '{ptxt}'")

print("\n=== Debug-Ende ===")
