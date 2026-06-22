"""
Nimmt Audio vom Mikrofon auf und gibt es als numpy Array zurück.
"""

import sounddevice as sd
import numpy as np


SAMPLE_RATE = 16000   # Vosk braucht genau 16000 Hz
CHANNELS    = 1       # Mono — Vosk braucht Mono
DTYPE       = "int16" # 16-bit — Vosk braucht int16


def aufnehmen(dauer_sekunden: float) -> np.ndarray:
    """
    Nimmt Audio für eine bestimmte Dauer auf.
    Args:
        dauer_sekunden: Wie lange aufnehmen (z.B. 5.0)
    Returns:
        numpy Array mit Audio-Daten (int16, mono, 16kHz)
    """
    print(f"🎤 Aufnahme läuft ({dauer_sekunden}s)...")
    
    audio = sd.rec(
        frames=int(dauer_sekunden * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
    )
    sd.wait()  # warten bis Aufnahme fertig
    
    print("✓ Aufnahme fertig.")
    return audio.flatten()  


def aufnehmen_bis_stille(
    max_dauer: float = 10.0,
    stille_schwelle: int = 150,
    stille_dauer: float = 1.5,
    chunk_groesse: int = 1024,
) -> np.ndarray:
    """
    Nimmt auf bis der Nutzer aufhört zu sprechen.
    Stoppt automatisch nach Stille.
    Args:
        max_dauer:       maximale Aufnahmedauer in Sekunden
        stille_schwelle: unter diesem RMS-Wert = Stille
        stille_dauer:    wie lange Stille bis Stopp (Sekunden)
        chunk_groesse:   wie viele Samples pro Block
    Returns:
        numpy Array mit Audio-Daten
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

            # RMS berechnen — misst wie laut der Chunk ist
            rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2))

            if rms < stille_schwelle:
                stille_chunks += 1
                if stille_chunks >= stille_limit:
                    print("✓ Stille erkannt — Aufnahme gestoppt.")
                    break
            else:
                stille_chunks = 0  # Sprache erkannt → Zähler zurücksetzen

    return np.concatenate(alle_chunks)