"""
main.py
Sprachassistent mit echtem Streaming-Output-Pipeline (satzweise synchron).

Output-Pipeline (LLM -> TTS -> UI), neu aufgesetzt:

    Ollama token stream
        |  (token delta)
        v
    StreamingPipeline.feed()  -> SentenceChunker -> [text_queue]
                                                          v
                                              PiperWorker (besitzt PiperVoice)
                                                          v
                                                    [audio_queue]
                                                          v
                                AudioPlayer (ein einziger sd.OutputStream)
                                                          v
                                on_spoken(text) -> StreamingState (lock) -> UI

Dadurch:
  * Die erste fertige Saetze wird sofort synthetisiert und abgespielt.
  * Generierung, Synthese und Wiedergabe uelappen sich (Pipelining).
  * Text erscheint genau dann, wenn der zugehoerige Satz gesprochen wird.
"""

import os
import time
import threading
import tempfile
import scipy.io.wavfile as wavfile
from pathlib import Path

from stt.whisper_transcriber import WhisperTranskriberer
from stt.recorder import aufnehmen_bis_stille
from llm.ollama_client import OllamaClient
from database.db import Datenbank
from tts.synthesizer import Synthesizer
from tts.streaming_pipeline import StreamingPipeline, StreamingState
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

# ---------------------------------------------------------------------------
# Thread-sicherer UI-Zustand.
# Frueher waren das ungeschuetzte Modul-Globals, die der Gradio-Timer ohne Lock
# gelesen hat (torn reads). Jetzt leben alle UI-Felder in einem Objekt mit
# eigenem Lock und werden ueber .snapshot() atomar gelesen.
# ---------------------------------------------------------------------------
_state = StreamingState(status="👂 Warte auf Wake Word...")

# Wake-Word-/Abarbeitungs-Steuerung (bleibt wie bisher, nur auf _state umgestellt).
_wake_triggered = False
_wake_lock = threading.Lock()
_processing = False
_listener = None


def on_wake():
    global _wake_triggered, _processing
    with _wake_lock:
        if _processing:
            return
        print("✅ WAKE WORD ERKANNT!")
        _wake_triggered = True
        _state.set_status("🎤 Wake Word erkannt! Bitte sprechen...")


def process_wake():
    """Haupt-Abarbeitungs-Loop: Wake -> Aufnahme -> STT -> gestreamtes LLM+TTS."""
    global _wake_triggered, _processing

    while True:
        time.sleep(0.3)

        with _wake_lock:
            if not _wake_triggered:
                continue
            _wake_triggered = False
            _processing = True

        try:
            _state.set_status("🎙️ Aufnahme läuft...")
            print("🎙️ Aufnahme läuft...")
            audio = aufnehmen_bis_stille(
                max_dauer=8.0, stille_schwelle=150, stille_dauer=1.2
            )

            if len(audio) == 0:
                _state.set_status("❌ Kein Audio erkannt.")
                _state.set_question("")
                with _wake_lock:
                    _processing = False
                continue

            _state.set_status("⏳ Transkribiere...")
            print("⏳ Transkribiere...")
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            wavfile.write(tmp.name, 16000, audio)
            tmp.close()
            frage_text = transkriberer.transkribiere_datei(tmp.name)
            os.unlink(tmp.name)

            if not frage_text:
                _state.set_status("❌ Kein Text erkannt.")
                _state.set_question("")
                with _wake_lock:
                    _processing = False
                continue

            _state.set_question(frage_text)
            _state.set_status(f"📝 Erkannt: {frage_text[:50]}...")
            print(f"📝 Erkannt: {frage_text}")

            _state.set_status("🧠 KI denkt & spricht ...")
            print("🧠 KI denkt & spricht (gestreamt) ...")

            # ── STREAMING-PIPELINE FUER DIESE ANTWORT ────────────────────
            # Frueher: Wort-fuer-Wort sd.play() + danach nochmal ganz
            # synthetisieren (doppelt, asynchron). Jetzt: eine Pipeline pro
            # Antwort. Der AudioPlayer gibt den Text WORTWEISE frei, getacktet
            # vom echten Audio-Takt: jedes Wort erscheint genau, wenn es
            # vorgelesen wird, und das letzte Wort kommt mit dem letzten Sample.
            _state.reset_spoken()
            wav_pfad = OUTPUT_DIR / f"stream_{int(time.time())}.wav"
            pipeline = StreamingPipeline(
                voice=synthesizer.stimme,
                syn_config=synthesizer.synth_config,
                state=_state,
                wav_path=str(wav_pfad),
            )
            pipeline.start()

            t_llm_start = time.perf_counter()

            def on_token(delta):
                # Delta = roher Ollama-Token (kein Wort!). Der Chunker fasst
                # Tokens zu ganzen Saetzen zusammen; feed() blockiert, wenn die
                # Text-Queue voll ist -> Selbsttaktung (kein Vorauseilen).
                pipeline.feed(delta)

            verlauf = datenbank.lade_verlauf(anzahl=6)
            ergebnis = llm_client.frage_streaming(
                frage_text, verlauf, callback=on_token
            )
            dauer_llm = round(time.perf_counter() - t_llm_start, 3)

            # Tail flushen, Sentinel durchreichen, Threads sauber beenden.
            result = pipeline.wait_done()

            # Gesamte gesprochene Antwort als UI-Text fixieren (falls der
            # letzte Satz ohne Satzzeichen endete oder on_spoken leicht hinter
            # der Generierung zuruecklag).
            _state.set_wav(result.wav_path)

            antwort_text = result.full_text.strip() or ergebnis["antwort"].strip()

            # ── DATENBANK MIT ECHTEN ZEITEN ──────────────────────────────
            dauer_ges = round(
                dauer_llm + result.synth_time_s + result.play_time_s, 3
            )
            datenbank.speichere(
                frage=frage_text,
                antwort=antwort_text,
                dauer_stt=0,
                dauer_llm=dauer_llm,
                dauer_tts=result.synth_time_s,
                dauer_ges=dauer_ges,
            )

            _state.set_status(
                f"✅ Fertig! {result.chunk_count} Sätze "
                f"(TTS {result.synth_time_s}s) "
                f"Audio: {Path(result.wav_path).name if result.wav_path else '-'}"
            )
            print(f"✅ Fertig! Audio: {result.wav_path}")

        except Exception as e:
            _state.set_status(f"❌ Fehler: {e}")
            print(f"❌ Fehler: {e}")
        finally:
            with _wake_lock:
                _processing = False
                _wake_triggered = False


def status_fn():
    """Atomarer Snapshot fuer den Gradio-Timer: (status, frage, antwort, wav)."""
    return _state.snapshot()


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
