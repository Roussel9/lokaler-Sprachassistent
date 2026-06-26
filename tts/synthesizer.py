"""
Text-to-Speech mit Piper – mit Echtzeit-Streaming.
"""

import os
import time
import urllib.request
import wave
import io
from pathlib import Path
from piper import PiperVoice
from piper.config import SynthesisConfig
from normalization.tts_text import bereite_text_fuer_tts
from .streaming_player import StreamingPlayer

VOICE_DIR = Path("models/piper")
ONNX_PFAD = VOICE_DIR / "de_DE-thorsten-medium.onnx"
JSON_PFAD = VOICE_DIR / "de_DE-thorsten-medium.onnx.json"
OUTPUT_DIR = Path("outputs/tts")

ONNX_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx"
JSON_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx.json"

SYN_CONFIG = SynthesisConfig(
    noise_scale=0.0,
    noise_w_scale=0.0,
    length_scale=1.0,
    normalize_audio=True,
)

class Synthesizer:
    def __init__(self):
        print("Lade TTS Stimme: Thorsten (deutsch, männlich, offline)")
        self._lade_stimme_falls_noetig()
        self.stimme = PiperVoice.load(str(ONNX_PFAD), config_path=str(JSON_PFAD))
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.SYN_CONFIG = SYN_CONFIG
        self.streamer = StreamingPlayer(self.stimme)
        print("OK TTS Stimme geladen (Piper / Thorsten).")

    def _lade_stimme_falls_noetig(self):
        if ONNX_PFAD.exists() and JSON_PFAD.exists():
            return
        VOICE_DIR.mkdir(parents=True, exist_ok=True)
        print("Lade Piper-Stimme herunter (~60 MB, nur beim ersten Start)...")
        for url, ziel in ((ONNX_URL, ONNX_PFAD), (JSON_URL, JSON_PFAD)):
            if not ziel.exists():
                urllib.request.urlretrieve(url, ziel)

    def synthesiere_normal(self, text: str, dateiname: str = None) -> tuple:
        text = bereite_text_fuer_tts(text)
        start = time.perf_counter()
        if dateiname is None:
            dateiname = f"tts_{int(time.time())}"
        wav_pfad = OUTPUT_DIR / f"{dateiname}.wav"
        with wave.open(str(wav_pfad), "wb") as wav_file:
            self.stimme.synthesize_wav(text, wav_file, syn_config=SYN_CONFIG)
        dauer_s = time.perf_counter() - start
        with wave.open(str(wav_pfad), "rb") as wf:
            audio_laenge_s = wf.getnframes() / float(wf.getframerate())
        return str(wav_pfad), round(dauer_s, 2), round(audio_laenge_s, 2)

    def synthesiere_wort_sofort(self, wort: str):
        """Synthetisiert ein Wort und spielt es sofort ab."""
        self.streamer.spiele_wort(wort)

    def synthesiere_wort_zu_datei(self, wort: str, index: int) -> str:
        """Synthetisiert ein Wort und speichert es als separate WAV-Datei."""
        wav_pfad = OUTPUT_DIR / f"chunk_{index}_{int(time.time())}.wav"
        try:
            with wave.open(str(wav_pfad), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(22050)
                self.stimme.synthesize_wav(wort, wav_file, syn_config=SYN_CONFIG)
            return str(wav_pfad)
        except Exception as e:
            print(f"Wort-TTS Fehler: {e}")
            return None