"""
wakeword/wakeword_listener.py
Wake-Word-Erkennung mit Vosk 
"""

from __future__ import annotations

import json
import threading
import time
from typing import Callable, List, Optional, Set

import numpy as np
import sounddevice as sd
from vosk import KaldiRecognizer, Model, SetLogLevel

SetLogLevel(-1)

_VOSK_MODEL_PATH = "models/vosk-model-small-de-0.15"
_SAMPLE_RATE = 16000
_BLOCK = 400  # 25 ms — etwas feinere Aufloesung fuer kurze Wake-Words
_REARM_SILENCE_BLOCKS = 6  # 6 * 25 ms = 150 ms Stille bis Re-Arm
_SILENCE_RMS = 0.003  # nur fuer Stille-Erkennung, nicht zum Blockieren von Vosk
_MIN_WAKE_SPEECH_BLOCKS = 4  # 100 ms; kuerzere Impulse sind meist Klicks/Rauschen
_MAX_WAKE_SPEECH_BLOCKS = 72  # 1.8 s; Wake-Phrase soll kurz bleiben
_MIN_WAKE_PEAK_RMS = 0.006
_CLIP_LEVEL = 0.98
_MAX_CLIPPED_RATIO = 0.01

# Phrasen fuer Vosk-Grammar (muessen im Modell-Wortschatz vorkommen).
_GRAMMAR_PHRASES = (
    "computer",
    "komputer",
    "kompjuter",
    "computa",
    "komputa",
)
_WAKE_PREFIXES = ("hey", "hallo", "ok", "okay")


def _normalize_token(t: str) -> str:
    return "".join(ch for ch in t.lower() if ch.isalpha())


def _normalize_phrase(text: str) -> str:
    return " ".join(
        tok
        for tok in (
            _normalize_token(part) for part in text.replace("_", " ").split()
        )
        if tok
    )


def _build_grammar(extra_words: Set[str]) -> str:
    wake_tokens = {
        token
        for token in ({_normalize_token(w) for w in _GRAMMAR_PHRASES} | extra_words)
        if token
    }
    phrases = set(wake_tokens)
    for wake_token in wake_tokens:
        for prefix in _WAKE_PREFIXES:
            phrases.add(f"{prefix} {wake_token}")
    phrases = sorted(phrases)
    phrases.append("[unk]")
    return json.dumps(phrases, ensure_ascii=False)


def _text_has_wake_word(text: str, wake_words: Set[str]) -> bool:
    text = _normalize_phrase(text)
    if not text:
        return False
    tokens = text.split()
    wake_tokens = wake_words | {_normalize_token(p) for p in _GRAMMAR_PHRASES}

    if len(tokens) == 1:
        return tokens[0] in wake_tokens
    if len(tokens) == 2:
        return tokens[0] in _WAKE_PREFIXES and tokens[1] in wake_tokens
    return False


class WakeWordListener:
    """Vosk-basierter Wake-Word-Detektor. Laeuft in einem Daemon-Thread."""

    def __init__(
        self,
        callback: Callable[[], None],
        wake_words: Optional[List[str]] = None,
        model_path: str = _VOSK_MODEL_PATH,
    ) -> None:
        if wake_words is None:
            wake_words = ["computer"]
        self.callback = callback
        self.wake_words = {_normalize_token(w) for w in wake_words}
        self._grammar_json = _build_grammar(self.wake_words)
        self._armed = True
        self._silent_blocks = 0
        self._paused = threading.Event()
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self.count = 0
        self._stream_open = False
        self._speech_blocks = 0
        self._speech_peak_rms = 0.0
        self._speech_samples = 0
        self._clipped_samples = 0

        print(f"Lade Vosk Wake-Word-Modell: {model_path}")
        self._model = Model(model_path)
        self._recognizer = self._new_recognizer()
        print(f"✓ Vosk Wake-Word-Modell bereit (Grammar: {self._grammar_json}).")

    def _new_recognizer(self) -> KaldiRecognizer:
        rec = KaldiRecognizer(self._model, _SAMPLE_RATE, self._grammar_json)
        rec.SetWords(False)
        return rec

    def _reset_recognizer(self) -> None:
        self._recognizer = self._new_recognizer()
        self._reset_audio_window()

    def _reset_audio_window(self) -> None:
        self._speech_blocks = 0
        self._speech_peak_rms = 0.0
        self._speech_samples = 0
        self._clipped_samples = 0

    def _track_audio_block(self, audio: np.ndarray, rms: float) -> None:
        if rms < _SILENCE_RMS:
            return
        self._speech_blocks += 1
        self._speech_peak_rms = max(self._speech_peak_rms, rms)
        self._speech_samples += int(audio.size)
        self._clipped_samples += int(np.count_nonzero(np.abs(audio) >= _CLIP_LEVEL))

    def _wake_audio_reject_reason(self) -> Optional[str]:
        if self._speech_blocks < _MIN_WAKE_SPEECH_BLOCKS:
            return "zu kurz/Impuls"
        if self._speech_blocks > _MAX_WAKE_SPEECH_BLOCKS:
            return "zu lange Sprache"
        if self._speech_peak_rms < _MIN_WAKE_PEAK_RMS:
            return "zu leise/Rauschen"
        if self._speech_samples:
            clipped_ratio = self._clipped_samples / self._speech_samples
            if clipped_ratio > _MAX_CLIPPED_RATIO:
                return "uebersteuert"
        return None

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._paused.clear()
        self._thread = threading.Thread(
            target=self._listen, name="WakeWordListener", daemon=True
        )
        self._thread.start()
        print(f"👂 Höre auf Wake-Word(s): {sorted(self.wake_words)}")

    def stop(self) -> None:
        self.running = False
        self._paused.set()
        if self._thread is not None:
            self._thread = None

    def pause(self) -> None:
        """Mikrofon freigeben fuer Aufnahme/TTS (Stream wird geschlossen)."""
        self._paused.set()

    def resume(self) -> None:
        """Nach Verarbeitung: Puffer leeren, bereit fuer naechstes Wake-Word."""
        self._armed = True
        self._silent_blocks = 0
        self._reset_recognizer()
        self._paused.clear()
        time.sleep(0.2)  # Kurze Pause, damit alles stabil ist


    def _listen(self) -> None:
        first_stream = True
        try:
            while self.running:
                if self._paused.is_set():
                    if self._stream_open:
                        self._stream_open = False
                    time.sleep(0.05)
                    continue

                try:
                    with sd.InputStream(
                        samplerate=_SAMPLE_RATE, channels=1, dtype="float32"
                    ) as stream:
                        self._stream_open = True
                        if first_stream:
                            print("✅ Wake-Word-Mikrofon-Stream gestartet")
                            first_stream = False
                        else:
                            print("✅ Wake-Word-Mikrofon wieder aktiv")

                        while self.running and not self._paused.is_set():
                            try:
                                block, _ = stream.read(_BLOCK)
                            except sd.PortAudioError:
                                time.sleep(0.05)
                                continue

                            audio = block.flatten()
                            rms = float(np.sqrt(np.mean(audio ** 2)))

                            if rms < _SILENCE_RMS:
                                self._silent_blocks += 1
                                if (
                                    self._silent_blocks >= _REARM_SILENCE_BLOCKS
                                    and not self._armed
                                ):
                                    self._reset_recognizer()
                                    self._armed = True
                            else:
                                self._silent_blocks = 0
                                self._track_audio_block(audio, rms)

                            # Immer an Vosk — auch leise Sprache nicht verwerfen.
                            pcm = (audio * 32767.0).astype("<i2").tobytes()
                            if self._recognizer.AcceptWaveform(pcm):
                                self._scan_result(self._recognizer.Result())

                        self._stream_open = False

                except sd.PortAudioError as e:
                    self._stream_open = False
                    if self.running and not self._paused.is_set():
                        print(f"⚠ Wake-Word Mikrofon: {e} — retry in 300ms")
                        time.sleep(0.3)
                except Exception as e:
                    self._stream_open = False
                    if self.running:
                        print(f"❌ Wake-Word Fehler: {e}")
                        time.sleep(0.3)
        except Exception as e:
            print(f"❌ Wake-Word Listener beendet: {e}")

    def _scan_result(self, result_json: str) -> None:
        if self._paused.is_set() or not self._armed:
            return
        if not result_json or result_json == "{}":
            return
        try:
            data = json.loads(result_json)
        except json.JSONDecodeError:
            return

        text = data.get("text") or ""
        if not text:
            self._reset_audio_window()
            return
        if not _text_has_wake_word(text, self.wake_words):
            self._reset_audio_window()
            return

        reject_reason = self._wake_audio_reject_reason()
        if reject_reason:
            print(f"Wake-Word verworfen ({reject_reason}): {text.strip()!r}")
            self._reset_recognizer()
            return

        self._armed = False
        self._silent_blocks = 0
        self._reset_recognizer()
        self.count += 1
        print(f"✅ WAKE WORD erkannt: {text.strip()!r}")
        try:
            self.callback()
        except Exception as e:
            print(f"❌ Wake-Word Callback Fehler: {e}")


def start_wakeword_listener(
    callback: Callable[[], None],
    wake_words: Optional[List[str]] = None,
) -> "WakeWordListener":
    listener = WakeWordListener(callback, wake_words=wake_words)
    listener.start()
    return listener
