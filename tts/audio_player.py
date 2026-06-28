"""
tts/audio_player.py
Single continuous audio stream that plays synthesized chunks gaplessly.

This module is the single most important fix for the old pipeline. The previous
design called fire-and-forget ``sounddevice.play()`` once per *token* with no
``wait()``: every new call preempted the previous on the shared device, so audio
overlapped, skipped, paused, and never stayed in sync. There is no way to get
gapless, ordered playback from repeated ``play()`` calls.

Correct design: exactly one ``sounddevice.OutputStream`` owned by exactly one
thread, fed sequentially by blocking ``write()``. Key properties:

  * **Gapless & non-overlapping**: samples are written in arrival order to one
    device buffer. No chunk can preempt another.
  * **Natural backpressure**: ``write()`` blocks when the device buffer is full.
    That block propagates up the queues (audio_queue full -> PiperWorker blocks
    -> text_queue full -> LLM feeder blocks), so generation self-paces to the
    speaker. This is what kills "text appears slowly / out of sync": the LLM
    can't run far ahead of the audio.
  * **Sentence-synced text reveal**: just before writing a sentence's samples,
    we fire ``on_spoken(display_text)``. The UI therefore reveals exactly the
    sentence currently being committed to the speaker -- never ahead, never
    behind.
  * **One owner thread**: the OutputStream is opened lazily on the first chunk
    (so wake-word / STT audio devices aren't touched until needed) and closed on
    end-of-stream.

The player also assembles the full utterance into a single WAV file on disk, so
history/replay works exactly like before (one file per answer).
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

# Type alias for the "a chunk started playing" callback.
OnSpoken = Callable[[str], None]


class AudioPlayer(threading.Thread):
    """Consumer of :class:`AudioTask` -> one continuous audio output stream.

    Args:
        audio_queue: Bounded queue of :class:`AudioTask` / ``STREAM_END``.
        on_spoken: Called with the display text of each task right as its audio
            begins playing. Use this to drive the UI reveal. May be ``None``.
        wav_path: If given, the full utterance is written here as a WAV file
            (one file per assistant answer, for replay/history). If ``None``,
            nothing is written to disk.
        name: Thread name (debugging).
    """

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

        # Empty synthesis (error / whitespace-only chunk): show the text at once
        # so the transcript never falls behind.
        if samples.size == 0:
            self._reveal(task.display)
            return

        # Ensure we have exactly one stream at the chunk's sample rate. In
        # practice the Piper model is a fixed sample rate (22050), so this opens
        # once and is reused for the whole utterance.
        self._ensure_stream(task.sample_rate)

        t0 = time.perf_counter()
        # Word-by-word reveal DRIVEN BY THE AUDIO CLOCK: the number of revealed
        # words grows in proportion to how much of this sentence's audio has
        # actually been committed to the speaker (written samples / total). So a
        # word appears only once the audio has reached it, the last word appears
        # exactly as the last samples play, and reveal never races ahead.
        self._cur_words = words
        self._cur_revealed = 0
        self._write_samples_word_sync(samples, words, task.sample_rate)
        self.play_time_s += time.perf_counter() - t0
        self.tasks_played += 1

        # Guarantee the full sentence is shown even if rounding left a trailing
        # word unrevealed.
        if words:
            self._reveal_n_words(len(words))

    def _write_samples_word_sync(
        self, samples: np.ndarray, words: list, sample_rate: int
    ) -> None:
        """Write one chunk to the device in sub-blocks, revealing words as we go.

        ``OutputStream.write`` blocks when the internal PortAudio buffer is full
        -> natural backpressure that makes the whole pipeline self-throttle.

        After each sub-block we compute the fraction of this sentence already
        written and reveal that many words. Mapping is proportional (samples
        <-> time), which keeps text tightly locked to the *actual* playback rate
        of the speaker -- not to any timer. No artificial slowdown: the audio
        still plays at full realtime speed; only the text reveal is paced by it.
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

            # Mirror what is actually played into the recording WAV so the file
            # contains exactly the audio the user heard (for later replay).
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

        Whitespace is kept attached so reconstructed text stays exactly verbatim
        (no missing spaces, no duplicates). Each item is one reveal step.
        """
        import re

        # A "unit" is a run of non-space characters. Whitespace between/around
        # is preserved as separate tokens so joining them reproduces the text.
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
        """Reveal the first ``n`` reveal-units of the CURRENT sentence.

        The current sentence's units are buffered in ``_cur_words``; the prefix
        already revealed is tracked in ``_cur_revealed`` so each new word is
        appended exactly once (never duplicated, never skipped).
        """
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
        # Sample rate changed (shouldn't happen with one voice, but stay safe):
        # tear down the old stream before opening a new one.
        self._close_stream()

        # We model output as float32 for the PortAudio callback; convert from
        # int16 via the dtype on write. Open lazily so the device is only
        # grabbed while the assistant is actually speaking.
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
