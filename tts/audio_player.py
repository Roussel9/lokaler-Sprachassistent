"""
tts/audio_player.py
"""

from __future__ import annotations

import queue
import threading
import time
import wave
from pathlib import Path
from typing import Callable, Optional, Union

import numpy as np
import sounddevice as sd

from .piper_worker import STREAM_END, AudioTask


OnSpoken = Callable[[str], None]


class AudioPlayer(threading.Thread):
    

    def __init__(
        self,
        audio_queue: "queue.Queue[Optional[Union[AudioTask, object]]]",
        on_spoken: Optional[OnSpoken] = None,
        wav_path: Optional[Union[str, Path]] = None,
        name: str = "AudioPlayer",
    ) -> None:
        super().__init__(name=name, daemon=True)
        self._queue = audio_queue
        self._on_spoken = on_spoken
        self._wav_path = str(wav_path) if wav_path else None
        # Single owner thread for the device. ``_stream`` is touched only here.
        self._stream: Optional[sd.OutputStream] = None
        self._stream_sample_rate: int = 0
        self._wav_file: Optional[wave.Wave_write] = None
        self._closed = False
        # Per-sentence word-sync reveal state (only touched on this thread).
        self._cur_words: list = []
        self._cur_revealed: int = 0
        # Diagnostics (single writer -> no lock). Read after join().
        self.play_time_s: float = 0.0
        self.tasks_played: int = 0

    # -- thread main --------------------------------------------------------

    def run(self) -> None:
        try:
            while True:
                task = self._queue.get()  # blocks
                if task is STREAM_END:
                    return
                if not isinstance(task, AudioTask):
                    continue
                self._play_task(task)
        finally:
            self._close()

    # -- per-chunk playback -------------------------------------------------

    def _play_task(self, task: AudioTask) -> None:
        samples = task.samples
        words = self._split_words(task.display)

        if samples.size == 0:
            self._reveal(task.display)
            return

        self._ensure_stream(task.sample_rate)

        t0 = time.perf_counter()
        self._cur_words = words
        self._cur_revealed = 0
        self._write_samples_word_sync(samples, words, task.sample_rate)
        self.play_time_s += time.perf_counter() - t0
        self.tasks_played += 1

        
        if words:
            self._reveal_n_words(len(words))

    def _write_samples_word_sync(
        self, samples: np.ndarray, words: list, sample_rate: int
    ) -> None:
        """Write one chunk to the device in sub-blocks, revealing words as we go.

        """
        if self._stream is None:
            return
        total = samples.shape[0]
        block = 4096
        for start in range(0, total, block):
            if self._closed:
                return
            end = min(start + block, total)
            self._stream.write(samples[start:end])

           
            if self._wav_file is not None:
                self._wav_file.writeframes(samples[start:end].tobytes())

            if words:
                # Fraction of THIS sentence committed so far -> word index.
                frac = end / float(total)
                n = int(frac * len(words))
                if n:
                    self._reveal_n_words(n)

    @staticmethod
    def _split_words(text: str) -> list:
        """Split display text into reveal units (words + standalone punctuation).

        """
        import re

        
        return re.findall(r"\S+|\s+", text)

    # -- reveal helpers -----------------------------------------------------

    def _reveal(self, full_text: str) -> None:
        """Reveal a whole string at once (used for empty-audio fallback)."""
        if self._on_spoken is not None:
            try:
                self._on_spoken(full_text)
            except Exception as exc:  # UI callback must never break playback
                print(f"[AudioPlayer] on_spoken Fehler: {exc}")

    def _reveal_n_words(self, n: int) -> None:
        
        if n <= self._cur_revealed:
            return
        # Append only the newly revealed units, in order.
        new_units = self._cur_words[self._cur_revealed : n]
        if not new_units:
            self._cur_revealed = n
            return
        piece = "".join(new_units)
        self._cur_revealed = n
        if self._on_spoken is not None:
            try:
                self._on_spoken(piece)
            except Exception as exc:
                print(f"[AudioPlayer] on_spoken Fehler: {exc}")

    # -- stream + wav lifecycle --------------------------------------------

    def _ensure_stream(self, sample_rate: int) -> None:
        if self._stream is not None and self._stream_sample_rate == sample_rate:
            return
        
        self._close_stream()

        
        self._stream = sd.OutputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            blocksize=0,  # let PortAudio choose
        )
        self._stream.start()
        self._stream_sample_rate = sample_rate

        if self._wav_path:
            self._wav_file = wave.open(self._wav_path, "wb")
            self._wav_file.setnchannels(1)
            self._wav_file.setsampwidth(2)  # int16
            self._wav_file.setframerate(sample_rate)

    def _close_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None
            self._stream_sample_rate = 0

    def _reveal(self, display: str) -> None:
        if self._on_spoken is not None:
            try:
                self._on_spoken(display)
            except Exception as exc:  # UI callback must never break playback
                print(f"[AudioPlayer] on_spoken Fehler: {exc}")

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._close_stream()
        if self._wav_file is not None:
            try:
                self._wav_file.close()
            except Exception:
                pass
            self._wav_file = None
