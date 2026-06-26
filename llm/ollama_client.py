"""
llm/ollama_client.py
Kommuniziert mit Gemma3 via Ollama – mit Streaming.
"""

import json
import time
import urllib.request
import urllib.error

OLLAMA_URL = "http://localhost:11434/api/chat"
MODELL = "gemma3:1b"

SYSTEM_PROMPT = """Du bist ein hilfreicher lokaler Sprachassistent.
Antworte immer kurz, klar und auf Deutsch.
Bei einfachen Rechenaufgaben antworte nur mit dem Ergebnis (nur die Zahl, ohne Erklärung).
Bei allen anderen Fragen antworte in 2-3 vollständigen Sätzen."""

class OllamaClient:
    def __init__(self, modell: str = MODELL, url: str = OLLAMA_URL):
        self.modell = modell
        self.url = url
        self._pruefe_verbindung()

    def _pruefe_verbindung(self):
        try:
            urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
            print(f"✓ Ollama verbunden. Modell: {self.modell}")
        except Exception:
            raise ConnectionError(
                "Ollama läuft nicht. Bitte starten mit: ollama serve\n"
                "Und Modell laden mit: ollama pull gemma3:1b"
            )

    def _baue_anfrage(self, text: str, verlauf: list) -> dict:
        nachrichten = [{"role": "system", "content": SYSTEM_PROMPT}]
        for eintrag in verlauf[-6:]:
            nachrichten.append({"role": "user", "content": eintrag["frage"]})
            nachrichten.append({"role": "assistant", "content": eintrag["antwort"]})
        nachrichten.append({"role": "user", "content": text})
        return {"model": self.modell, "messages": nachrichten, "stream": True}

    def frage_streaming(self, text: str, verlauf: list = None, callback=None) -> dict:
        """Streaming-Version: ruft callback für jedes Wort auf."""
        if verlauf is None:
            verlauf = []

        anfrage_daten = self._baue_anfrage(text, verlauf)
        anfrage_bytes = json.dumps(anfrage_daten).encode("utf-8")

        request = urllib.request.Request(
            url=self.url,
            data=anfrage_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        start = time.perf_counter()
        antwort_text = ""
        tokens_out = 0

        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                for line in response:
                    line = line.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        if "message" in chunk and "content" in chunk["message"]:
                            new_text = chunk["message"]["content"]
                            if new_text:
                                antwort_text += new_text
                                tokens_out += 1
                                if callback:
                                    callback(new_text)  # Wort für Wort
                    except json.JSONDecodeError:
                        continue

            dauer = time.perf_counter() - start
            return {
                "antwort": antwort_text,
                "dauer_s": round(dauer, 2),
                "tokens_out": tokens_out,
                "tokens_pro_s": round(tokens_out / dauer, 1) if dauer > 0 else 0,
            }

        except urllib.error.URLError as e:
            raise ConnectionError(f"Ollama Anfrage fehlgeschlagen: {e}")

    def frage(self, text: str, verlauf: list = None) -> dict:
        """Nicht-Streaming (kompatibel mit altem Code)."""
        if verlauf is None:
            verlauf = []
        anfrage_daten = self._baue_anfrage(text, verlauf)
        anfrage_daten["stream"] = False
        anfrage_bytes = json.dumps(anfrage_daten).encode("utf-8")

        request = urllib.request.Request(
            url=self.url,
            data=anfrage_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        start = time.perf_counter()
        with urllib.request.urlopen(request, timeout=120) as response:
            antwort_json = json.loads(response.read().decode("utf-8"))
            dauer = time.perf_counter() - start
            antwort_text = antwort_json["message"]["content"].strip()
            tokens_out = antwort_json.get("eval_count", 0)
            return {
                "antwort": antwort_text,
                "dauer_s": round(dauer, 2),
                "tokens_out": tokens_out,
                "tokens_pro_s": round(tokens_out / dauer, 1) if dauer > 0 else 0,
            }