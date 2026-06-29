"""
Nimmt Audio vom Mikrofon auf und gibt es als numpy Array zurück.
Für Whisper: 16 kHz, Mono, int16.
 zwei Aufnahme-Funktionen:
  - aufnehmen(dauer)              : feste Dauer (kurz, für Tests)
  - aufnehmen_bis_stille(...)     : VAD-gesteuert, stoppt nach Stille
"""

import sounddevice as sd
import numpy as np

SAMPLE_RATE = 16000
CHANNELS    = 1
DTYPE       = "int16"

def aufnehmen(dauer_sekunden: float) -> np.ndarray:
    print(f"🎤 Aufnahme läuft ({dauer_sekunden}s)...")
    audio = sd.rec(
        frames=int(dauer_sekunden * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
    )
    sd.wait()
    print("✓ Aufnahme fertig.")
    return audio.flatten()

def aufnehmen_bis_stille(
    max_dauer: float = 10.0,
    stille_schwelle: int = 150,
    stille_dauer: float = 1.5,
    chunk_groesse: int = 1024,
) -> np.ndarray:
    """Nimmt auf, bis Stille erkannt wird (einfacher RMS-basierter VAD).

    """
    print("🎤 Sprechen... (stoppt automatisch nach Stille)")

    alle_chunks    = []
    stille_chunks  = 0
    max_chunks     = int(max_dauer * SAMPLE_RATE / chunk_groesse)
    chunks_pro_sek = SAMPLE_RATE / chunk_groesse
    stille_limit   = int(stille_dauer * chunks_pro_sek)

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE) as stream:
        for _ in range(max_chunks):
            chunk, _ = stream.read(chunk_groesse)
            chunk = chunk.flatten()
            alle_chunks.append(chunk)

            rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2))

            if rms < stille_schwelle:
                stille_chunks += 1
                if stille_chunks >= stille_limit:
                    print("✓ Stille erkannt — Aufnahme gestoppt.")
                    break
            else:
                stille_chunks = 0

    return np.concatenate(alle_chunks)
