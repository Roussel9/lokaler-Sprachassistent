"""
tts/synthesizer.py
Owns and loads the Piper voice; provides the synthesis config and a classic
whole-text synthesis helper.

Role in the new pipeline
------------------------
The streaming pipeline (streaming_pipeline.py) needs *one* loaded PiperVoice to
hand to the PiperWorker. Rather than loading the voice a second time, this class
keeps being the single owner of the loaded voice and exposes it (plus the shared
:class:`SynthesisConfig`) so the pipeline can reuse it.

    Synthesizer                       -> owns PiperVoice + SYN_CONFIG
        .stimme   (PiperVoice)            shared with StreamingPipeline
        .synth_config (SynthesisConfig)   shared with StreamingPipeline
        .synthesiere_normal(text)         legacy whole-text -> WAV (kept for
                                           replay/tests/non-streaming use)

What was removed
----------------
The old word-by-word helpers (``synthesiere_wort_sofort``,
``synthesiere_wort_zu_datei``) and the ``StreamingPlayer`` import are gone. They
were the unstable pieces: they called fire-and-forget ``sd.play()`` per token,
which is the root cause of overlapping/skipped audio. Streaming is now done
correctly by the queue-based pipeline.
"""

import time
import urllib.request
import wave
from pathlib import Path

from piper import PiperVoice
from piper.config import SynthesisConfig

from normalization.tts_text import bereite_text_fuer_tts

VOICE_DIR = Path("models/piper")
ONNX_PFAD = VOICE_DIR / "de_DE-thorsten-medium.onnx"
JSON_PFAD = VOICE_DIR / "de_DE-thorsten-medium.onnx.json"
OUTPUT_DIR = Path("outputs/tts")

ONNX_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx"
JSON_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx.json"

# Shared synthesis config: deterministic, normalized, realtime speed.
SYN_CONFIG = SynthesisConfig(
    noise_scale=0.0,
    noise_w_scale=0.0,
    length_scale=1.0,
    normalize_audio=True,
)


class Synthesizer:
    """Loads the Piper voice once and shares it with the streaming pipeline."""

    def __init__(self):
        print("Lade TTS Stimme: Thorsten (deutsch, männlich, offline)")
        self._lade_stimme_falls_noetig()
        self.stimme = PiperVoice.load(str(ONNX_PFAD), config_path=str(JSON_PFAD))
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        # Expose the config so the pipeline reuses the exact same settings.
        self.synth_config = SYN_CONFIG
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
        """Whole-text synthesis -> WAV file. Returns (pfad, synth_dauer_s, audio_dauer_s).

        Retained for non-streaming needs (replay, tests). The main streaming
        flow no longer calls this -- it uses StreamingPipeline instead -- but the
        method is intentionally kept stable and backwards compatible.
        """
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
