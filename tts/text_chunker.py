"""
tts/text_chunker.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from normalization.tts_text import bereite_text_fuer_tts


_SENTENCE_TERMINATORS = ".!?…"

_SOFT_BOUNDARY = ",;:\n"

_DEFAULT_MAX_WORDS = 25


@dataclass(frozen=True)
class TextChunk:
    """One speakable unit.

    
    """

    display: str
    speak: str

    def __len__(self) -> int:  # convenience for tests
        return len(self.display)


class SentenceChunker:
    """Turn an incremental token stream into a list of :class:`TextChunk`.

    """

    def __init__(self, max_words: int = _DEFAULT_MAX_WORDS) -> None:
        if max_words < 1:
            raise ValueError("max_words must be >= 1")
        self._max_words = max_words
        self._buf: str = ""

    # -- public API ---------------------------------------------------------

    def feed(self, delta: str) -> List[TextChunk]:
        """Accept one token delta and return any completed chunks.

        """
        if not delta:
            return []
        self._buf += delta
        return self._drain(final=False)

    def flush(self) -> List[TextChunk]:
        
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

        """
        if not buf:
            return None, ""

       
        idx = _first_index(buf, _SENTENCE_TERMINATORS)
        if idx is not None:
            
            end = idx + 1
            while end < len(buf) and buf[end].isspace():
                end += 1
            return buf[:end], buf[end:]

        
        word_count = len(buf.split())
        if word_count >= self._max_words:
            soft = _first_index(buf, _SOFT_BOUNDARY)
            if soft is not None:
               
                end = soft + 1
                while end < len(buf) and buf[end].isspace():
                    end += 1
                return buf[:end], buf[end:]
            
            space = _nth_whitespace_after(buf, self._max_words)
            if space is not None:
                return buf[:space], buf[space:]

        
        if final:
            
            return (buf if buf else None), ""
        
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

    """
    words_seen = 0
    for i, ch in enumerate(s):
        if ch.isspace():
            words_seen += 1
            if words_seen >= min_words:
                return i
    return None
