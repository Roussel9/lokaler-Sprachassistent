"""
Hilfsfunktionen für deutsche Zahlen:
- gesprochene Ziffernfolgen erkennen (eins zwei drei → 123)
- Ziffern für TTS in Wörter umwandeln (123 → einhundertdreiundzwanzig)
"""

from __future__ import annotations

import re


_DIGIT_WORD_TO_DIGIT = {
    "null": "0",
    "nul": "0",
    "zero": "0",
    "eins": "1",
    "ein": "1",
    "eine": "1",
    "zwei": "2",
    "drei": "3",
    "vier": "4",
    "fünf": "5",
    "fuenf": "5",
    "sechs": "6",
    "sieben": "7",
    "acht": "8",
    "neun": "9",
}


def ersetze_gesprochene_ziffernfolgen(text: str) -> str:
    """
    Ersetzt Sequenzen gesprochener Ziffern (mind. 2) durch echte Ziffern.
    Beispiel: "meine pin ist eins zwei drei vier" -> "meine pin ist 1234"
    """
    if not text:
        return text

    words = sorted(_DIGIT_WORD_TO_DIGIT.keys(), key=len, reverse=True)
    alt = "|".join(re.escape(w) for w in words)

    # mind. 2 Ziffern-Wörter, erlaubt beliebige Whitespaces dazwischen
    pattern = re.compile(rf"(?<!\w)((?:{alt})(?:\s+(?:{alt}))+)(?!\w)", re.IGNORECASE)

    def repl(m: re.Match) -> str:
        seq = m.group(1)
        parts = re.split(r"\s+", seq.strip())
        digits = []
        for p in parts:
            d = _DIGIT_WORD_TO_DIGIT.get(p.lower())
            if d is None:
                return seq
            digits.append(d)
        return "".join(digits)

    return pattern.sub(repl, text)


_UNITS = ["null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun"]
_TEENS = {
    10: "zehn",
    11: "elf",
    12: "zwölf",
    13: "dreizehn",
    14: "vierzehn",
    15: "fünfzehn",
    16: "sechzehn",
    17: "siebzehn",
    18: "achtzehn",
    19: "neunzehn",
}
_TENS = {
    20: "zwanzig",
    30: "dreißig",
    40: "vierzig",
    50: "fünfzig",
    60: "sechzig",
    70: "siebzig",
    80: "achtzig",
    90: "neunzig",
}


def zahl_zu_worten_de(n: int) -> str:
    """Konvertiert 0..999999 zu deutschen Wörtern (ohne Leerzeichen)."""
    if n < 0:
        return "minus" + zahl_zu_worten_de(-n)
    if n < 10:
        return _UNITS[n]
    if n < 20:
        return _TEENS[n]
    if n < 100:
        tens = (n // 10) * 10
        unit = n % 10
        if unit == 0:
            return _TENS[tens]
        ein = "ein" if unit == 1 else _UNITS[unit]
        return f"{ein}und{_TENS[tens]}"
    if n < 1000:
        hund = n // 100
        rest = n % 100
        prefix = "einhundert" if hund == 1 else f"{_UNITS[hund]}hundert"
        return prefix if rest == 0 else prefix + zahl_zu_worten_de(rest)
    if n < 1_000_000:
        taus = n // 1000
        rest = n % 1000
        prefix = "eintausend" if taus == 1 else f"{zahl_zu_worten_de(taus)}tausend"
        return prefix if rest == 0 else prefix + zahl_zu_worten_de(rest)
    return str(n)


def ersetze_ziffern_fuer_tts(text: str) -> str:
    """
    Ersetzt Ziffern im Text, damit MMS-TTS sie zuverlässig spricht.
    - Kurze Zahlen (0..999999) werden als Zahl gesprochen.
    - Lange Folgen (>=5 Stellen, z.B. Telefonnummern) werden als Ziffern einzeln gesprochen.
    """
    if not text:
        return text

    def repl(m: re.Match) -> str:
        s = m.group(0)
        # führende Nullen: eher als Ziffern einzeln
        if len(s) >= 2 and s.startswith("0"):
            return " ".join(_UNITS[int(ch)] for ch in s)
        if len(s) >= 5:
            return " ".join(_UNITS[int(ch)] for ch in s)
        try:
            n = int(s)
        except ValueError:
            return s
        if 0 <= n <= 999_999:
            return zahl_zu_worten_de(n)
        return " ".join(_UNITS[int(ch)] for ch in s if ch.isdigit())

    return re.sub(r"\d+", repl, text)

