"""
Transkribiert Audio mit Faster-Whisper (offline, lokal).
"""

import os
import time
from faster_whisper import WhisperModel

class WhisperTranskriberer:
    """
    Lädt das Whisper-Modell einmal und transkribiert Audio.
    """

    def __init__(self, model_size: str = "base", device: str = "cpu"):
        print(f"Lade Whisper-Modell: {model_size} ({device})")
        self.model = WhisperModel(model_size, device=device, compute_type="int8")
        print(f"✓ Whisper-Modell geladen.")

    def transkribiere_datei(self, wav_pfad: str) -> str:
        if not wav_pfad or not os.path.exists(wav_pfad):
            return ""

        start = time.perf_counter()
        segments, _ = self.model.transcribe(
            wav_pfad,
            language="de",
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(
                threshold=0.5,
                min_speech_duration_ms=250,
                min_silence_duration_ms=500,
            ),
        )
        text = " ".join(seg.text for seg in segments).strip()
        print(f"Whisper transkribiert in {time.perf_counter()-start:.2f}s: '{text[:60]}...'")
        return text