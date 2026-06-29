"""
tts/piper_worker.py
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

    """

    display: str
    samples: np.ndarray  # int16, shape (N,)
    sample_rate: int
    index: int



class _Sentinel:
    """End-of-stream marker shared by both queues."""

    __slots__ = ()


STREAM_END = _Sentinel()


class PiperWorker(threading.Thread):
    

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
        
        self.synth_time_s: float = 0.0
        self.chunk_count: int = 0

    # -- thread main --------------------------------------------------------

    def run(self) -> None:
        idx = 0
        while True:
            item = self._text_queue.get()  # blocks until a chunk or sentinel
            if item is STREAM_END:
                
                self._audio_queue.put(STREAM_END)
                return

            # Defensive: ignore anything that isn't a real chunk.
            if not isinstance(item, TextChunk):
                continue

            try:
                samples, sample_rate = self._synthesize(item.speak)
            except Exception as exc:  # never kill the pipeline on one bad chunk
                print(f"[PiperWorker] Synthese-Fehler bei Chunk {idx}: {exc}")
                
                samples = np.zeros(0, dtype=np.int16)
                sample_rate = 22050

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
