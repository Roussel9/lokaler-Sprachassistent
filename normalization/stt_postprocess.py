"""
Nachbearbeitung von Vosk-STT-Text: Tippfehler, Zahlen, Rechenzeichen.
"""

from __future__ import annotations

import re

from normalization.numbers_de import ersetze_gesprochene_ziffernfolgen


# Häufige Vosk-Fehler bei schlechten Mikrofonen
_TIPPFEHLER = [
    (r"\bmahl\b", "mal"),
    (r"\bpluss?\b", "plus"),
    (r"\bminus\b", "minus"),
    (r"\bgeteilt\s+durch\b", "geteilt durch"),
    (r"\bdurch\b(?=\s+\d|\s+eins|\s+zwei|\s+drei|\s+vier|\s+fünf|\s+fuenf|\s+sechs|\s+sieben|\s+acht|\s+neun|\s+null)", "durch"),
    (r"\bist\s+gleich\b", "ist gleich"),
    (r"\bich\s+bin\b", "ich bin"),
    (r"\bwas\s+ist\b", "was ist"),
    (r"\bwieviel\b", "wie viel"),
    (r"\bwie\s+viel\b", "wie viel"),
]

# Gesprochene Operatoren → einheitliche Schreibweise
_RECHEN_ERSETZUNGEN = [
    (r"\bplus\b", "+"),
    (r"\bminus\b", "-"),
    (r"\bmal\b", "×"),
    (r"\bgeteilt\s+durch\b", "÷"),
    (r"\bdurch\b(?=\s)", "÷"),
    (r"\bist\s+gleich\b", "="),
    (r"\bgleich\b(?=\s*\d)", "="),
    (r"\bprozent\b", "%"),
]


def bereinige_stt_text(text: str) -> str:
    """Bereinigt STT-Ausgabe für bessere Lesbarkeit und LLM-Verständnis."""
    if not text:
        return text

    t = text.strip().lower()
    t = re.sub(r"\s+", " ", t)
    t = _normalisiere_umlaute(t)

    for pattern, ersatz in _TIPPFEHLER:
        t = re.sub(pattern, ersatz, t, flags=re.IGNORECASE)

    t = ersetze_gesprochene_ziffernfolgen(t)
    t = _normalisiere_rechenausdruecke(t)

    # Erster Buchstabe groß (für Anzeige)
    if t:
        t = t[0].upper() + t[1:]

    return t


def _normalisiere_rechenausdruecke(text: str) -> str:
    """Wandelt gesprochene Operatoren in Symbole um, wenn es wie Mathe klingt."""
    if not _enthaelt_rechenkontext(text):
        return text

    t = text
    for pattern, ersatz in _RECHEN_ERSETZUNGEN:
        t = re.sub(pattern, f" {ersatz} ", t, flags=re.IGNORECASE)

    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s*([+\-×÷=])\s*", r" \1 ", t)
    return re.sub(r"\s+", " ", t).strip()


def _normalisiere_umlaute(text: str) -> str:
    """Vosk schreibt oft ohne Umlaute — korrigiert häufige deutsche Wörter."""
    fixes = {
        "fuenf": "fünf",
        "fünfzehn": "fünfzehn",
        "fuenfzehn": "fünfzehn",
        "sechzehn": "sechzehn",
        "siebzehn": "siebzehn",
        "achtzehn": "achtzehn",
        "neunzehn": "neunzehn",
        "groesser": "größer",
        "groess": "groß",
        "ueber": "über",
        "fuer": "für",
        "koennen": "können",
        "moechte": "möchte",
    }
    for alt, neu in fixes.items():
        text = re.sub(rf"\b{re.escape(alt)}\b", neu, text)
    return text


def _enthaelt_rechenkontext(text: str) -> bool:
    """Erkennt ob der Satz wahrscheinlich eine Rechenaufgabe ist."""
    marker = (
        r"\b(plus|minus|mal|geteilt|durch|gleich|prozent|"
        r"was ist|wie viel|rechnen|multipliziert|addiert|subtrahiert)\b|[+\-×÷=]"
    )
    return bool(re.search(marker, text, re.IGNORECASE)) or bool(re.search(r"\d", text))
