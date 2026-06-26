"""
Streaming Audio Player – spielt Audio sofort ab während es generiert wird.
"""

import io
import wave
import sounddevice as sd
import numpy as np
from piper import PiperVoice
from piper.config import SynthesisConfig
from normalization.tts_text import bereite_text_fuer_tts

SYN_CONFIG = SynthesisConfig(
    noise_scale=0.0,
    noise_w_scale=0.0,
    length_scale=1.0,
    normalize_audio=True,
)

class StreamingPlayer:
    def __init__(self, stimme):
        self.stimme = stimme
        self.sample_rate = 22050

    def spiele_wort(self, wort: str):
        """Synthetisiert ein Wort und spielt es sofort ab."""
        try:
            # Wort synthetisieren
            with io.BytesIO() as buf:
                with wave.open(buf, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(self.sample_rate)
                    self.stimme.synthesize_wav(wort, wav, syn_config=SYN_CONFIG)
                buf.seek(0)
                
                # Audio-Daten auslesen
                with wave.open(buf, "rb") as wav:
                    audio_data = wav.readframes(wav.getnframes())
                    audio_np = np.frombuffer(audio_data, dtype=np.int16)
                    
                # Sofort abspielen (non-blocking)
                sd.play(audio_np, self.sample_rate)
                
        except Exception as e:
            print(f"Streaming Fehler: {e}")