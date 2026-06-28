"""
tts/piper_worker.py
Dedicated worker thread that owns the Piper voice and synthesizes chunks.

Design: one PiperVoice, one owner thread
----------------------------------------
A Piper ``PiperVoice`` wraps a single ONNX ``InferenceSession``. ONNX Runtime
sessions are not designed to be called concurrently from many threads with
arbitrary interleaving, and the espeak phonemizer inside Piper is guarded by a
global lock. So instead of sharing the voice across threads (the old design,
which is one source of "race conditions"), this worker is the **sole owner** of
the voice. It pulls :class:`TextChunk` objects from a queue, synthesizes each
one, and pushes PCM audio onto the next queue. No other thread ever touches the
voice.

Pipeline position
-----------------
    text_queue  -> [PiperWorker] -> audio_queue
                     (owns PiperVoice)

The worker is purely a consumer/producer between two queues; it knows nothing
about playback or the UI. ``None`` on the input queue is the end-of-stream
sentinel: it is forwarded to the output queue so the downstream player also
shuts down.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
from piper import PiperVoice
from piper.config import SynthesisConfig

from .text_chunker import TextChunk


@dataclass(frozen=True)
class AudioTask:
    """One synthesized sentence ready to be played and shown.

    Attributes:
        display: Verbatim text to reveal in the UI when this audio starts.
        samples: int16 mono PCM for this chunk.
        sample_rate: Sample rate of ``samples`` (Piper's, typically 22050).
        index: 0-based position in the utterance (for ordering/debugging).
    """

    display: str
    samples: np.ndarray  # int16, shape (N,)
    sample_rate: int
    index: int


# Sentinel pushed through the queues to signal end-of-stream. Using a module
# level object (not None) keeps type hints honest and is unambiguous.
class _Sentinel:
    """End-of-stream marker shared by both queues."""

    __slots__ = ()


STREAM_END = _Sentinel()


class PiperWorker(threading.Thread):
    """Consumer of ``TextChunk`` -> producer of :class:`AudioTask`.

    Args:
        voice: A loaded Piper ``PiperVoice``. Ownership transfers to this
            thread for its lifetime; no other thread should call it.
        syn_config: Piper ``SynthesisConfig`` (noise/length scale etc.).
        text_queue: Bounded input queue of :class:`TextChunk` / sentinel.
        audio_queue: Bounded output queue of :class:`AudioTask` / sentinel.
        name: Thread name (debugging).
    """

    def __init__(
        self,
        voice: PiperVoice,
        syn_config: SynthesisConfig,
        text_queue: "queue.Queue[Optional[object]]",
        audio_queue: "queue.Queue[Optional[object]]",
        name: str = "PiperWorker",
    ) -> None:
        super().__init__(name=name, daemon=True)
        self._voice = voice
        self._syn_config = syn_config
        self._text_queue = text_queue
        self._audio_queue = audio_queue
        # Diagnostics: total wall-clock time spent synthesizing, and the count.
        # Read by the pipeline after join(); no lock needed (single writer).
        self.synth_time_s: float = 0.0
        self.chunk_count: int = 0

    # -- thread main --------------------------------------------------------

    def run(self) -> None:
        idx = 0
        while True:
            item = self._text_queue.get()  # blocks until a chunk or sentinel
            if item is STREAM_END:
                # Propagate EOS so the AudioPlayer shuts down too.
                self._audio_queue.put(STREAM_END)
                return

            # Defensive: ignore anything that isn't a real chunk.
            if not isinstance(item, TextChunk):
                continue

            try:
                samples, sample_rate = self._synthesize(item.speak)
            except Exception as exc:  # never kill the pipeline on one bad chunk
                print(f"[PiperWorker] Synthese-Fehler bei Chunk {idx}: {exc}")
                # Emit silence-free task with the text so the UI still advances
                # and stays in sync (no audio, but the sentence is revealed).
                samples = np.zeros(0, dtype=np.int16)
                sample_rate = 22050

            # ``put`` blocks if the audio_queue is full -> natural backpressure:
            # synthesis can't outrun playback, bounding memory.
            self._audio_queue.put(
                AudioTask(
                    display=item.display,
                    samples=samples,
                    sample_rate=sample_rate,
                    index=idx,
                )
            )
            idx += 1

    # -- synthesis ----------------------------------------------------------

    def _synthesize(self, text: str) -> tuple[np.ndarray, int]:
        """Synthesize one chunk to int16 mono PCM via Piper's generator API.

        ``voice.synthesize()`` yields one :class:`AudioChunk` *per sentence*
        already, so for our (already sentence-bounded) input we simply
        concatenate the resulting PCM. ``synthesize_wav`` would also work, but
        going through ``synthesize()`` avoids intermediate WAV containers and
        lets us grab the real sample_rate from the model config.
        """
        if not text or not text.strip():
            return np.zeros(0, dtype=np.int16), self._voice.config.sample_rate

        t0 = time.perf_counter()
        pieces: list[np.ndarray] = []
        sample_rate = self._voice.config.sample_rate
        for audio_chunk in self._voice.synthesize(text, syn_config=self._syn_config):
            # audio_int16_array is a cached int16 view (see piper/voice.py).
            pieces.append(audio_chunk.audio_int16_array)
            sample_rate = audio_chunk.sample_rate

        samples = np.concatenate(pieces) if pieces else np.zeros(0, dtype=np.int16)
        self.synth_time_s += time.perf_counter() - t0
        self.chunk_count += 1
        return samples, sample_rate
