"""
Transkribiert Audio mit Vosk (offline, lokal, kein Internet).
"""

import json
import os

import numpy as np
from vosk import KaldiRecognizer, Model

from normalization.stt_cleanup import bereinige_stt_leicht
from stt.audio_utils import lade_wav_fuer_vosk


SAMPLE_RATE = 16000
CHUNK_BYTES = 8000


class VoskTranskriberer:
    """Lädt das Vosk Modell einmal und transkribiert Audio."""

    def __init__(self, modell_pfad: str):
        if not os.path.exists(modell_pfad):
            raise FileNotFoundError(
                f"Vosk Modell nicht gefunden: {modell_pfad}\n"
                f"Bitte herunterladen von: https://alphacephei.com/vosk/models\n"
                f"→ vosk-model-de-0.21 → entpacken → in models/ Ordner"
            )

        print(f"Lade Vosk Modell: {modell_pfad}")
        self.modell = Model(modell_pfad)
        print("OK Vosk Modell geladen.")

    def transkribiere_datei(self, wav_pfad: str) -> str:
        """Transkribiert WAV — zwei Durchläufe, bestes Ergebnis nach Konfidenz."""
        if not wav_pfad or not os.path.exists(wav_pfad):
            return ""

        audio, fehler = lade_wav_fuer_vosk(wav_pfad)
        if fehler or len(audio) == 0:
            return ""

        kandidaten = [
            self._transkribiere_mit_konfidenz(audio),
            self._transkribiere_mit_konfidenz(self._sanft_verstaerken(audio)),
        ]

        kandidaten = [(t, c) for t, c in kandidaten if t]
        if not kandidaten:
            return ""

        text, _ = max(kandidaten, key=lambda x: (x[1], len(x[0])))
        return bereinige_stt_leicht(text)

    def _sanft_verstaerken(self, audio: np.ndarray) -> np.ndarray:
        rms = float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))
        if rms <= 0 or rms >= 2500:
            return audio
        faktor = min(2500.0 / rms, 2.5)
        return np.clip(audio.astype(np.float32) * faktor, -32768, 32767).astype(np.int16)

    def _transkribiere_mit_konfidenz(self, audio: np.ndarray) -> tuple[str, float]:
        recognizer = KaldiRecognizer(self.modell, SAMPLE_RATE)
        recognizer.SetWords(True)

        audio_bytes = audio.astype(np.int16).tobytes()
        for i in range(0, len(audio_bytes), CHUNK_BYTES):
            recognizer.AcceptWaveform(audio_bytes[i:i + CHUNK_BYTES])

        ergebnis = json.loads(recognizer.FinalResult())
        woerter = ergebnis.get("result", [])

        if woerter:
            text = " ".join(w["word"] for w in woerter).strip()
            konf = sum(float(w.get("conf", 0.0)) for w in woerter) / len(woerter)
            return text, konf

        text = ergebnis.get("text", "").strip()
        return text, 0.3 if text else 0.0
