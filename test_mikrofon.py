# test_mikrofon.py
import sounddevice as sd
import numpy as np

duration = 3
print(f"Aufnahme {duration} Sekunden...")
recording = sd.rec(int(duration * 16000), samplerate=16000, channels=1, dtype='int16')
sd.wait()
print(f"Audio shape: {recording.shape}")
print(f"Min/Max Werte: {recording.min()} / {recording.max()}")
print(f"RMS: {np.sqrt(np.mean(recording.astype(np.float32)**2))}")