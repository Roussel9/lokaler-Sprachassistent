"""
tts/text_chunker.py
Accumulator that turns the Ollama token stream into speakable chunks.

Why this exists
---------------
Ollama (like most LLM servers) emits *token deltas*, not words. A delta can be
a leading space, a partial word (" Herb", "st"), glued punctuation, or a whole
sentence. The old pipeline fed those deltas straight to Piper, which is why
words were skipped, torn, or spoken twice.

SentenceChunker buffers the raw delta stream and emits **complete, character
faithful** chunks. Two guarantees matter for the rest of the pipeline:

  1. Every input character is emitted exactly once (nothing lost, nothing
     duplicated, punctuation preserved) -- the concatenation of all emitted
     chunks (both `display` and `speak`) equals the fed text.
  2. Boundaries land on natural sentence terminators, so each emitted chunk is a
     coherent unit Piper can synthesize and prosodize well.

Chunking strategy (req: complete sentences or ~15-30 words, not word-by-word)
-----------------------------------------------------------------------------
  - Emit on a sentence terminator (``. ! ? …``) immediately after it is seen.
  - Run-on safety: if the buffer crosses ``max_words`` (~25) before any
    terminator, flush at the next comma / colon / newline; if even that is
    absent, flush at the next whitespace so a single chunk never grows
    unbounded. This keeps latency bounded for LLM answers with little
    punctuation without ever splitting a word.
  - The trailing remainder (no terminator at end of stream) is emitted on
    :meth:`flush`.

Two parallel strings per chunk
------------------------------
  - ``display``: the verbatim LLM text (what the user reads on screen).
  - ``speak``:   a normalized copy via ``bereite_text_fuer_tts`` (numbers,
    math symbols -> German words) for Piper.

Because both are derived from the same boundary, the UI reveal stays in 1:1
lockstep with the spoken sentence (sentence-level sync, per the design).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from normalization.tts_text import bereite_text_fuer_tts

# Characters that end a sentence. We emit a chunk as soon as one of these
# appears. Everything else (commas, semicolons, newlines) only triggers a
# boundary as run-on protection, never by itself.
_SENTENCE_TERMINATORS = ".!?…"
# Soft boundary characters used only for run-on protection (long buffer).
_SOFT_BOUNDARY = ",;:\n"
# Default hard cap before run-on protection kicks in.
_DEFAULT_MAX_WORDS = 25


@dataclass(frozen=True)
class TextChunk:
    """One speakable unit.

    Attributes:
        display: Human-readable text for the UI (verbatim from the LLM).
        speak:   Normalized text handed to Piper (numbers/symbols spelled out).
    """

    display: str
    speak: str

    def __len__(self) -> int:  # convenience for tests
        return len(self.display)


class SentenceChunker:
    """Turn an incremental token stream into a list of :class:`TextChunk`.

    Thread model: the chunker is **not** thread-safe by itself. It is driven
    synchronously by whoever owns the LLM callback (the pipeline feeder runs on
    the LLM thread). Emitted chunks are then handed to a thread-safe queue.

    Typical use::

        chunker = SentenceChunker()
        for delta in token_stream:
            for chunk in chunker.feed(delta):
                consume(chunk)
        for chunk in chunker.flush():
            consume(chunk)
    """

    def __init__(self, max_words: int = _DEFAULT_MAX_WORDS) -> None:
        if max_words < 1:
            raise ValueError("max_words must be >= 1")
        self._max_words = max_words
        self._buf: str = ""

    # -- public API ---------------------------------------------------------

    def feed(self, delta: str) -> List[TextChunk]:
        """Accept one token delta and return any completed chunks.

        Returning a list (instead of being a generator) keeps the feeder
        trivial: ``for chunk in chunker.feed(delta): queue.put(chunk)``.
        """
        if not delta:
            return []
        self._buf += delta
        return self._drain(final=False)

    def flush(self) -> List[TextChunk]:
        """Emit whatever remains in the buffer. Always the last call."""
        return self._drain(final=True)

    # -- internals ----------------------------------------------------------

    def _drain(self, final: bool) -> List[TextChunk]:
        out: List[TextChunk] = []
        while True:
            chunk_text, self._buf = self._next_chunk(self._buf, final=final)
            if chunk_text is None:
                break
            out.append(self._make_chunk(chunk_text))
        return out

    def _next_chunk(self, buf: str, *, final: bool) -> tuple[Optional[str], str]:
        """Return ``(chunk_inclusive_of_boundary, remaining_buffer)``.

        Returning ``None`` means "no boundary found, keep buffering". On
        ``final`` we emit the whole remaining buffer (even without a
        terminator) so the tail of the answer is never lost.
        """
        if not buf:
            return None, ""

        # 1) Sentence terminator -> strongest boundary. The terminator is part
        #    of the emitted chunk (inclusive), so punctuation is preserved and
        #    never "missing".
        idx = _first_index(buf, _SENTENCE_TERMINATORS)
        if idx is not None:
            # Include the terminator itself; keep any trailing whitespace with
            # the chunk so the next chunk starts clean.
            end = idx + 1
            while end < len(buf) and buf[end].isspace():
                end += 1
            return buf[:end], buf[end:]

        # 2) Run-on protection: buffer grew large without any terminator.
        word_count = len(buf.split())
        if word_count >= self._max_words:
            soft = _first_index(buf, _SOFT_BOUNDARY)
            if soft is not None:
                # Flush up to and including the soft boundary.
                end = soft + 1
                while end < len(buf) and buf[end].isspace():
                    end += 1
                return buf[:end], buf[end:]
            # No soft boundary: split at the next whitespace AFTER max_words so
            # we never cut inside a word. Find a space beyond the cap.
            space = _nth_whitespace_after(buf, self._max_words)
            if space is not None:
                return buf[:space], buf[space:]

        # 3) Nothing to emit yet.
        if final:
            # End of stream: emit whatever remains. We deliberately keep
            # whitespace-only remainders too, so the concatenation of all chunks
            # reproduces the fed text byte-for-byte (lossless). A whitespace-only
            # chunk is harmless: the worker maps it to empty audio and the UI
            # reveal of a space is invisible.
            return (buf if buf else None), ""
        # Not final: keep buffering. MUST return a 2-tuple so the caller can
        # unpack it; returning nothing here was the crash.
        return None, buf

    @staticmethod
    def _make_chunk(text: str) -> TextChunk:
        # Normalize a COPY for Piper; the display copy stays verbatim.
        return TextChunk(display=text, speak=bereite_text_fuer_tts(text))


def _first_index(s: str, chars: str) -> Optional[int]:
    """First index in ``s`` of any character in ``chars``, or None."""
    for i, ch in enumerate(s):
        if ch in chars:
            return i
    return None


def _nth_whitespace_after(s: str, min_words: int) -> Optional[int]:
    """Index of the first whitespace that ends the (min_words+1)-th word.

    Used for run-on splits: we want at least ``min_words`` words to remain
    intact, then cut at the following space. Returns None if there is no
    suitable space (e.g. a single huge token).
    """
    words_seen = 0
    for i, ch in enumerate(s):
        if ch.isspace():
            words_seen += 1
            if words_seen >= min_words:
                return i
    return None
