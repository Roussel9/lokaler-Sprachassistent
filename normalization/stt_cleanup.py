"""
Leichte STT-Nachbearbeitung — nur offensichtliche Tippfehler, kein Umbau des Satzes.
"""

import re


_FIXES = [
    (r"\bmahl\b", "mal"),
    (r"\bpluss?\b", "plus"),
    (r"\bnich\b", "nicht"),
    (r"\bise\b", "ist"),
    (r"\bun\b", "und"),
]


def bereinige_stt_leicht(text: str) -> str:
    if not text:
        return text

    t = re.sub(r"\s+", " ", text.strip())
    for pattern, ersatz in _FIXES:
        t = re.sub(pattern, ersatz, t, flags=re.IGNORECASE)
    return t
