"""
main.py
Sprachassistent mit echtem Wort-für-Wort Streaming – Audio sofort abspielen!
"""

import os
import time
import threading
import tempfile
import numpy as np
import scipy.io.wavfile as wavfile
from pathlib import Path

from stt.whisper_transcriber import WhisperTranskriberer
from stt.recorder import aufnehmen_bis_stille
from llm.ollama_client import OllamaClient
from database.db import Datenbank
from tts.synthesizer import Synthesizer
from ui.interface import erstelle_interface
from wakeword.wakeword_listener import start_wakeword_listener

PORT = 7860
OUTPUT_DIR = Path("outputs/tts")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("Starte Sprachassistent...")
transkriberer = WhisperTranskriberer(model_size="base", device="cpu")
llm_client = OllamaClient()
datenbank = Datenbank()
synthesizer = Synthesizer()
print("✓ Alle Komponenten geladen.\n")

_wake_triggered = False
_wake_lock = threading.Lock()
_last_status = "👂 Warte auf Wake Word..."
_last_frage = ""
_last_antwort = ""
_last_wav = None
_streaming_text = ""
_streaming_audio = []
_processing = False
_listener = None
_current_chunk_index = 0

def on_wake():
    global _wake_triggered, _last_status, _processing
    with _wake_lock:
        if _processing:
            return
        print("✅ WAKE WORD ERKANNT!")
        _wake_triggered = True
        _last_status = "🎤 Wake Word erkannt! Bitte sprechen..."

def process_wake():
    global _wake_triggered, _last_status, _last_frage, _last_antwort, _last_wav
    global _processing, _streaming_text, _streaming_audio, _current_chunk_index

    while True:
        time.sleep(0.3)

        with _wake_lock:
            if not _wake_triggered:
                continue
            _wake_triggered = False
            _processing = True

        try:
            _last_status = "🎙️ Aufnahme läuft..."
            print("🎙️ Aufnahme läuft...")
            audio = aufnehmen_bis_stille(max_dauer=8.0, stille_schwelle=150, stille_dauer=1.2)

            if len(audio) == 0:
                _last_status = "❌ Kein Audio erkannt."
                _last_frage = ""
                with _wake_lock:
                    _processing = False
                continue

            _last_status = "⏳ Transkribiere..."
            print("⏳ Transkribiere...")
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            wavfile.write(tmp.name, 16000, audio)
            tmp.close()
            frage_text = transkriberer.transkribiere_datei(tmp.name)
            os.unlink(tmp.name)

            if not frage_text:
                _last_status = "❌ Kein Text erkannt."
                _last_frage = ""
                with _wake_lock:
                    _processing = False
                continue

            _last_frage = frage_text
            _last_status = f"📝 Erkannt: {frage_text[:50]}..."
            print(f"📝 Erkannt: {frage_text}")

            _last_status = "🧠 KI denkt..."
            print("🧠 KI denkt...")

            # ── STREAMING: Wort für Wort ──────────────────────────────────
            _streaming_text = ""
            _streaming_audio = []
            _current_chunk_index = 0

            def on_word(word):
                global _streaming_text, _last_status, _streaming_audio, _current_chunk_index
                # Text aktualisieren
                _streaming_text += word + " "
                _last_status = f"💬 {_streaming_text[:50]}..."

                # Wort SOFORT abspielen (ohne WAV-Datei)
                synthesizer.synthesiere_wort_sofort(word)
                print(f"🔊 Wort abgespielt: '{word}'")

            # LLM Streaming starten
            verlauf = datenbank.lade_verlauf(anzahl=6)
            ergebnis = llm_client.frage_streaming(frage_text, verlauf, callback=on_word)

            antwort_text = ergebnis["antwort"]
            _last_antwort = antwort_text

            # ── VOLLSTÄNDIGES AUDIO SPEICHERN ────────────────────────────
            # Normale TTS für vollständige Antwort
            wav_pfad, _, _ = synthesizer.synthesiere_normal(antwort_text)
            _last_wav = wav_pfad

            # ── DATENBANK SPEICHERN ──────────────────────────────────────
            datenbank.speichere(
                frage=frage_text,
                antwort=antwort_text,
                dauer_stt=0,
                dauer_llm=round(ergebnis["dauer_s"], 3),
                dauer_tts=0,
                dauer_ges=0,
            )

            _last_status = f"✅ Fertig! Audio: {Path(wav_pfad).name}"
            print(f"✅ Fertig! Audio: {wav_pfad}")

        except Exception as e:
            _last_status = f"❌ Fehler: {e}"
            print(f"❌ Fehler: {e}")
        finally:
            with _wake_lock:
                _processing = False
                _wake_triggered = False

def status_fn():
    global _last_status, _last_frage, _streaming_text, _last_wav
    return _last_status, _last_frage, _streaming_text, _last_wav

def lade_verlauf_tabelle():
    eintraege = datenbank.lade_alle()
    return [
        [e["zeitstempel"], e["frage"][:50], e["antwort"][:80],
         e["dauer_stt"], e["dauer_llm"], e["dauer_tts"], e["dauer_ges"]]
        for e in eintraege
    ]

if __name__ == "__main__":
    print("🚀 Starte UI...")
    _listener = start_wakeword_listener(on_wake, ["assistent", "jarvis"])
    process_thread = threading.Thread(target=process_wake, daemon=True)
    process_thread.start()

    demo = erstelle_interface(None, None, lade_verlauf_tabelle, status_fn)
    demo.launch(server_name="127.0.0.1", server_port=PORT, share=False)
    if _listener:
        _listener.stop()