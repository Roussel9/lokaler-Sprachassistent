"""
Streaming Text-to-Speech mit Piper.
Generiert Audio in Echtzeit während der Text noch geschrieben wird.
"""

import os
import time
import wave
import threading
import queue
import tempfile
from pathlib import Path
from piper import PiperVoice
from piper.config import SynthesisConfig
from normalization.tts_text import bereite_text_fuer_tts

VOICE_DIR = Path("models/piper")
ONNX_PFAD = VOICE_DIR / "de_DE-thorsten-medium.onnx"
JSON_PFAD = VOICE_DIR / "de_DE-thorsten-medium.onnx.json"
OUTPUT_DIR = Path("outputs/tts")

SYN_CONFIG = SynthesisConfig(
    noise_scale=0.0,
    noise_w_scale=0.0,
    length_scale=1.0,
    normalize_audio=True,
)

class StreamingSynthesizer:
    """
    Synthesizer der Text in Echtzeit in Audio umwandelt.
    """
    
    def __init__(self):
        print("Lade Streaming-TTS: Thorsten (deutsch, männlich)")
        self._lade_stimme()
        self.stimme = PiperVoice.load(str(ONNX_PFAD), config_path=str(JSON_PFAD))
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        print("✓ Streaming-TTS bereit")
        
    def _lade_stimme(self):
        if ONNX_PFAD.exists() and JSON_PFAD.exists():
            return
        VOICE_DIR.mkdir(parents=True, exist_ok=True)
        print("Lade Piper-Stimme herunter (~60 MB)...")
        import urllib.request
        for url, ziel in ((ONNX_URL, ONNX_PFAD), (JSON_URL, JSON_PFAD)):
            if not ziel.exists():
                urllib.request.urlretrieve(url, ziel)
    
    def synthesiere_streaming(self, text: str, callback=None):
        """
        Synthetisiert Text und gibt Audio-Stücke in Echtzeit aus.
        
        Args:
            text: Zu synthetisierender Text
            callback: Funktion die Audio-Stücke empfängt (wird in Thread aufgerufen)
        
        Returns:
            Vollständiger Audio-Pfad und Liste der Stücke
        """
        text = bereite_text_fuer_tts(text)
        print(f"Streaming: '{text[:60]}...'")
        
        # Text in Sätze aufteilen (für Streaming)
        sätze = self._teile_in_saetze(text)
        
        audio_stücke = []
        wav_pfad = OUTPUT_DIR / f"stream_{int(time.time())}.wav"
        
        # Erste WAV-Datei für vollständiges Audio
        with wave.open(str(wav_pfad), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            
            for satz in sätze:
                if not satz.strip():
                    continue
                    
                # Satz synthetisieren
                satz_audio = self._synthesize_sentence(satz)
                wav_file.writeframes(satz_audio)
                audio_stücke.append(satz_audio)
                
                # Callback aufrufen (für UI-Update)
                if callback:
                    callback(satz_audio, satz)
        
        return str(wav_pfad), audio_stücke
    
    def _teile_in_saetze(self, text: str) -> list:
        """Teilt Text in Sätze (für Streaming)."""
        import re
        # Satzzeichen: . ! ? und auch , ; für flüssigeres Streaming
        sätze = re.split(r'(?<=[.!?;:])\s+', text)
        return [s.strip() for s in sätze if s.strip()]
    
    def _synthesize_sentence(self, text: str) -> bytes:
        """Synthetisiert einen einzelnen Satz und gibt Audio-Bytes zurück."""
        import io
        with io.BytesIO() as buf:
            with wave.open(buf, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(22050)
                self.stimme.synthesize_wav(text, wav, syn_config=SYN_CONFIG)
            return buf.getvalue()