"""
llm/ollama_client.py
Kommuniziert mit Gemma3 via Ollama.
direkte HTTP-Anfragen an Ollama API.
"""

import json
import time
import urllib.request
import urllib.error


# ─── KONFIGURATION ────────────────────────────────────────────────────────────

OLLAMA_URL  = "http://localhost:11434/api/chat"
MODELL      = "gemma3:1b"

SYSTEM_PROMPT = """Du bist ein hilfreicher lokaler Sprachassistent.
Antworte immer kurz, klar und auf Deutsch.
Bei einfachen Rechenaufgaben antworte nur mit dem Ergebnis (nur die Zahl, ohne Erklärung).
Bei allen anderen Fragen antworte in 2-3 vollständigen Sätzen."""

# ──────────────────────────────────────────────────────────────────────────────


class OllamaClient:
    """
    Direkte HTTP-Kommunikation mit der Ollama API.
    """

    def __init__(self, modell: str = MODELL, url: str = OLLAMA_URL):
        self.modell = modell
        self.url    = url
        self._pruefe_verbindung()

    def _pruefe_verbindung(self):
        """Prüft ob Ollama läuft."""
        try:
            req = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
            print(f"✓ Ollama verbunden. Modell: {self.modell}")
        except Exception:
            raise ConnectionError(
                "Ollama läuft nicht. Bitte starten mit: ollama serve\n"
                "Und Modell laden mit: ollama pull gemma3:1b"
            )

    def _baue_anfrage(self, text: str, verlauf: list) -> dict:
        """
        Baut das JSON-Objekt für die Ollama API.
        
        Format:
        {
            "model": "gemma3:1b",
            "messages": [
                {"role": "system", "content": "..."},
                {"role": "user",   "content": "..."},
                {"role": "assistant", "content": "..."},  ← Verlauf
                {"role": "user",   "content": "aktuelle Frage"}
            ],
            "stream": false
        }
        """
        nachrichten = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        # Gesprächsverlauf hinzufügen (letzte 6 Nachrichten)
        for eintrag in verlauf[-6:]:
            nachrichten.append({"role": "user",      "content": eintrag["frage"]})
            nachrichten.append({"role": "assistant", "content": eintrag["antwort"]})

        # Aktuelle Frage
        nachrichten.append({"role": "user", "content": text})

        return {
            "model":    self.modell,
            "messages": nachrichten,
            "stream":   False,
        }

    def frage(self, text: str, verlauf: list = None) -> dict:
        """
        Schickt eine Frage an Gemma3 und gibt Antwort + Metriken zurück.

        Args:
            text:    die Frage als Text
            verlauf: Liste von {"frage": ..., "antwort": ...} für Kontext

        Returns:
            {
                "antwort":      str,
                "dauer_s":      float,
                "tokens_in":    int,
                "tokens_out":   int,
                "tokens_pro_s": float,
            }
        """
        if verlauf is None:
            verlauf = []

        anfrage_daten = self._baue_anfrage(text, verlauf)

        # JSON → bytes
        anfrage_bytes = json.dumps(anfrage_daten).encode("utf-8")

        # HTTP POST Anfrage selbst bauen
        request = urllib.request.Request(
            url     = self.url,
            data    = anfrage_bytes,
            headers = {"Content-Type": "application/json"},
            method  = "POST",
        )

        start = time.perf_counter()

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                antwort_bytes = response.read()
                dauer = time.perf_counter() - start

            # JSON parsen
            antwort_json = json.loads(antwort_bytes.decode("utf-8"))

            # Antworttext extrahieren
            antwort_text = antwort_json["message"]["content"].strip()

            # Metriken extrahieren
            tokens_in   = antwort_json.get("prompt_eval_count", 0)
            tokens_out  = antwort_json.get("eval_count", 0)
            eval_dur_ns = antwort_json.get("eval_duration", 1)
            tokens_pro_s = tokens_out / (eval_dur_ns / 1e9) if eval_dur_ns > 0 else 0

            return {
                "antwort":      antwort_text,
                "dauer_s":      round(dauer, 2),
                "tokens_in":    tokens_in,
                "tokens_out":   tokens_out,
                "tokens_pro_s": round(tokens_pro_s, 1),
            }

        except urllib.error.URLError as e:
            raise ConnectionError(f"Ollama Anfrage fehlgeschlagen: {e}")


# ─── Schnelltest ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    client = OllamaClient()

    fragen = [
        "Was ist 15 mal 8?",
        "Was ist die Hauptstadt von Deutschland?",
        "Erkläre kurz was ein Sprachassistent ist.",
    ]

    for frage in fragen:
        print(f"\nFrage: {frage}")
        ergebnis = client.frage(frage)
        print(f"Antwort    : {ergebnis['antwort']}")
        print(f"Zeit       : {ergebnis['dauer_s']}s")
        print(f"Tokens/s   : {ergebnis['tokens_pro_s']}")