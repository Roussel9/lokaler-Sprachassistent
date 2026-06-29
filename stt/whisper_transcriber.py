"""
Transkribiert Audio mit Faster-Whisper 
"""

import os
import time
from typing import Tuple

from faster_whisper import WhisperModel


class WhisperTranskriberer:
    """
    Laedt das Whisper-Modell einmal und transkribiert Audio.

    Args:
        model_size: 'tiny' | 'base' | 'small' | 'medium' | 'large-v3'. Default: 'large-v3'.
        device: 'cpu' oder 'cuda'. Default: 'cpu'.
        compute_type: 'int8' auf CPU am schnellsten. Default: 'int8'.
    """

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        print(f"Lade Whisper-Modell: {model_size} ({device}, {compute_type})")
        self.model_size = model_size
        self.model = WhisperModel(
            model_size, device=device, compute_type=compute_type
        )
        print(f"✓ Whisper-Modell geladen: {model_size}")

    def transkribiere_datei(self, wav_pfad: str) -> Tuple[str, float]:
        """Transkribiert eine WAV-Datei. Gibt (text, dauer_s) zurueck."""
        if not wav_pfad or not os.path.exists(wav_pfad):
            return "", 0.0

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
                speech_pad_ms=200,
            ),
        )
        text = " ".join(seg.text for seg in segments).strip()
        dauer = round(time.perf_counter() - start, 3)
        print(
            f"Whisper transkribiert in {dauer:.2f}s "
            f"(Modell {self.model_size}): '{text[:60]}...'"
        )
        return text, dauer

    def transkribiere_audio(self, audio: "np.ndarray", sample_rate: int = 16000):
        """Transkribiert direkt ein numpy-Array (16 kHz, mono). Gibt (text, dauer_s)."""
        import numpy as np
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32) / 32768.0
        start = time.perf_counter()
        segments, _ = self.model.transcribe(
            audio,
            language="de",
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(
                threshold=0.5,
                min_speech_duration_ms=250,
                min_silence_duration_ms=500,
                speech_pad_ms=200,
            ),
        )
        text = " ".join(seg.text for seg in segments).strip()
        dauer = round(time.perf_counter() - start, 3)
        print(
            f"Whisper transkribiert in {dauer:.2f}s "
            f"(Modell {self.model_size}, aus Array): '{text[:60]}...'"
        )
        return text, dauer
