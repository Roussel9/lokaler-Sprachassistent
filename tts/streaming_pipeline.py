"""
tts/streaming_pipeline.py
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from piper import PiperVoice
from piper.config import SynthesisConfig

from .audio_player import AudioPlayer
from .piper_worker import STREAM_END, PiperWorker
from .text_chunker import SentenceChunker


_TEXT_QUEUE_SIZE = 4
_AUDIO_QUEUE_SIZE = 4


@dataclass
class PipelineResult:
    """Final report returned by :meth:`StreamingPipeline.wait_done`."""

    full_text: str
    wav_path: Optional[str]
    chunk_count: int
    synth_time_s: float
    play_time_s: float


@dataclass
class StreamingState:
    """Thread-safe snapshot of what the UI should show.

    """

    status: str = "Bereit"
    question: str = ""
    spoken: str = ""
    wav_path: Optional[str] = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def set_status(self, status: str) -> None:
        with self._lock:
            self.status = status

    def set_question(self, question: str) -> None:
        with self._lock:
            self.question = question

    def append_spoken(self, text: str) -> None:
        
        with self._lock:
            self.spoken += text

    def set_wav(self, wav_path: Optional[str]) -> None:
        with self._lock:
            self.wav_path = wav_path

    def reset_spoken(self) -> None:
        with self._lock:
            self.spoken = ""

    def snapshot(self) -> tuple[str, str, str, Optional[str]]:
        """Atomic read of (status, question, spoken, wav_path) for the UI."""
        with self._lock:
            return self.status, self.question, self.spoken, self.wav_path


class StreamingPipeline:
    """Owns the two queues and the two worker threads for one assistant answer.

    """

    def __init__(
        self,
        voice: PiperVoice,
        syn_config: SynthesisConfig,
        state: StreamingState,
        wav_path: Optional[str] = None,
        text_queue_size: int = _TEXT_QUEUE_SIZE,
        audio_queue_size: int = _AUDIO_QUEUE_SIZE,
    ) -> None:
        self._state = state
        self._chunker = SentenceChunker()
        self._text_queue: "queue.Queue" = queue.Queue(maxsize=text_queue_size)
        self._audio_queue: "queue.Queue" = queue.Queue(maxsize=audio_queue_size)

        self._worker = PiperWorker(
            voice=voice,
            syn_config=syn_config,
            text_queue=self._text_queue,
            audio_queue=self._audio_queue,
        )
        self._player = AudioPlayer(
            audio_queue=self._audio_queue,
            on_spoken=state.append_spoken,
            wav_path=wav_path,
        )
        self._started = False
        self._fed_full_text: List[str] = []

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._worker.start()
        self._player.start()

    def feed(self, delta: str) -> None:
        """Accept one token delta from the LLM stream.

        """
        if not self._started:
            self.start()
        self._fed_full_text.append(delta)
        for chunk in self._chunker.feed(delta):
            # Blocks when text_queue is full -> self-pacing.
            self._text_queue.put(chunk)

    def wait_done(self) -> PipelineResult:
        """Flush the tail, signal end-of-stream, join the threads.

        """
        if not self._started:
            self.start()

        for chunk in self._chunker.flush():
            self._text_queue.put(chunk)

        self._text_queue.put(STREAM_END)

        self._worker.join()
        self._player.join()

        full_text = "".join(self._fed_full_text)
        wav = self._player._wav_path if self._player._wav_path else None
        return PipelineResult(
            full_text=full_text,
            wav_path=wav,
            chunk_count=self._worker.chunk_count,
            synth_time_s=round(self._worker.synth_time_s, 3),
            play_time_s=round(self._player.play_time_s, 3),
        )

    def stop(self) -> None:
        """Force-stop (e.g. on interrupt). Idempotent. Best-effort.
        """
        try:
            self._text_queue.put_nowait(STREAM_END)
        except queue.Full:
            pass
        try:
            self._audio_queue.put_nowait(STREAM_END)
        except queue.Full:
            pass
