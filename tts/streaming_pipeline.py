"""
tts/streaming_pipeline.py
Orchestrates the streaming TTS pipeline and exposes a thread-safe UI snapshot.

Topology (producer -> consumer, each resource has exactly one owner thread)::

    LLM callback (token delta)
        |
        v
    StreamingPipeline.feed()      <-- caller thread (LLM/Ollama reader)
        |
        v
    SentenceChunker               <-- not threaded; runs on the feeder thread
        |
        v  (TextChunk)
    [ text_queue  ]  (bounded)    <-- backpressure point #1
        |
        v
    PiperWorker (owns PiperVoice) <-- thread #1
        |
        v  (AudioTask)
    [ audio_queue ]  (bounded)    <-- backpressure point #2
        |
        v
    AudioPlayer (owns 1 sd.OutputStream) <-- thread #2
        |
        v
    on_spoken(text) -> StreamingState.append_spoken()  <-- UI reveal

The caller's job is tiny: for every Ollama token delta call ``feed(delta)``,
then ``flush()`` + ``wait_done()``. Everything else is handled here.

Why two queues and not one?
    Two queues decouple the two slow stages (synthesis and playback) so they can
    overlap with each other and with generation. Bounded sizes turn "overlap"
    into "self-pacing": if playback falls behind, both queues fill and the
    producer blocks, so memory is bounded and text never races ahead of audio.

Thread-safe UI state
    The Gradio UI polls on a timer from its own thread. All UI-visible fields
    (status, question, spoken-so-far text, latest wav path) live in
    :class:`StreamingState`, guarded by a single lock, so the poller never sees
    a torn read.
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

# Bounded queue depth. Small on purpose: we want the LLM to stay roughly one or
# two sentences ahead of the speaker, not buffer the whole answer. When full,
# ``put`` blocks -> backpressure flows upstream.
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

    Updated only by the assistant's processing thread (status/question) and by
    the AudioPlayer's ``on_spoken`` callback (spoken text). Read by the Gradio
    timer tick. A single lock guards every field -> no torn reads.
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
        # Called from the AudioPlayer thread at the moment a sentence's audio
        # is committed to the speaker. ``text`` is the verbatim display string.
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

    Lifecycle::

        pipe = StreamingPipeline(voice, syn_config, wav_path)
        pipe.start()
        for token in llm_stream:        # in the LLM reader callback
            pipe.feed(token)
        result = pipe.wait_done()       # flush() + join + timings

    ``feed`` is meant to be called from the Ollama streaming loop (the same
    thread that reads the HTTP response). It never blocks for long: it only
    blocks when the text queue is full, which is the intended backpressure.
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

        Chunks produced by the chunker are pushed onto the text queue, which
        blocks if it is full (backpressure). Safe to call from the LLM reader
        thread; must not be called after :meth:`wait_done`.
        """
        if not self._started:
            self.start()
        self._fed_full_text.append(delta)
        for chunk in self._chunker.feed(delta):
            # Blocks when text_queue is full -> self-pacing.
            self._text_queue.put(chunk)

    def wait_done(self) -> PipelineResult:
        """Flush the tail, signal end-of-stream, join the threads.

        Returns a :class:`PipelineResult` with the assembled full text, the WAV
        path (if any), and per-stage wall-clock timings.
        """
        if not self._started:
            self.start()

        # Emit any trailing text that had no sentence terminator.
        for chunk in self._chunker.flush():
            self._text_queue.put(chunk)

        # Sentinels drain the queues in order so both threads exit cleanly.
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

        Puts the sentinel on the text queue so the worker exits; the player
        follows once its queue drains or this is called. Not used in the normal
        flow but provided so the caller can bail out without leaking threads.
        """
        try:
            self._text_queue.put_nowait(STREAM_END)
        except queue.Full:
            pass
        try:
            self._audio_queue.put_nowait(STREAM_END)
        except queue.Full:
            pass
