"""
Bereitet LLM-Antworten für MMS-TTS vor: Zahlen + Rechenzeichen.
"""

from __future__ import annotations

import re

from normalization.numbers_de import ersetze_ziffern_fuer_tts


def bereite_text_fuer_tts(text: str) -> str:
    """Vollständige TTS-Vorbereitung: Symbole → deutsche Wörter, dann Zahlen."""
    if not text:
        return text

    t = text.strip()
    t = ersetze_rechen_symbole_fuer_tts(t)
    t = ersetze_ziffern_fuer_tts(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def ersetze_rechen_symbole_fuer_tts(text: str) -> str:
    """Wandelt mathematische Zeichen in sprechbare deutsche Wörter um."""
    t = text

    t = re.sub(r"(\d)\s*%", r"\1 Prozent", t)
    t = re.sub(r"(?<!\d)%", " Prozent ", t)

    t = re.sub(r"(\d)\s*\+\s*(\d)", r"\1 plus \2", t)
    t = re.sub(r"(\d)\s*-\s*(\d)", r"\1 minus \2", t)
    t = re.sub(r"(\d)\s*[×*]\s*(\d)", r"\1 mal \2", t)
    t = re.sub(r"(\d)\s*/\s*(\d)", r"\1 geteilt durch \2", t)
    t = re.sub(r"(\d)\s*÷\s*(\d)", r"\1 geteilt durch \2", t)
    t = re.sub(r"\s*=\s*", " ist gleich ", t)

    # Verbleibende Symbole (z.B. "15+8=23" ohne Leerzeichen)
    t = t.replace("+", " plus ")
    t = re.sub(r"(?<!\w)-(?=\d)", " minus ", t)
    t = t.replace("×", " mal ")
    t = t.replace("*", " mal ")
    t = t.replace("÷", " geteilt durch ")
    t = re.sub(r"(?<!\d)/(?=\d)", " geteilt durch ", t)
    t = t.replace("=", " ist gleich ")

    return t
