"""
main.py
"""

import os
import time

from stt.transcriber   import VoskTranskriberer
from stt.audio_utils   import wav_info
from llm.ollama_client import OllamaClient
from database.db       import Datenbank
from tts.synthesizer   import Synthesizer
from ui.interface      import erstelle_interface
from normalization.numbers_de import ersetze_gesprochene_ziffernfolgen


VOSK_MODELL_PFAD = "models/vosk-model-de-0.21"
PORT             = 7860

print("Starte Sprachassistent...")
transkriberer = VoskTranskriberer(VOSK_MODELL_PFAD)
llm_client    = OllamaClient()
datenbank     = Datenbank()
synthesizer   = Synthesizer()
print("OK Alle Komponenten geladen.\n")


def transkribiere(audio):
  """Nur STT — Text kann danach manuell korrigiert werden."""
  if audio is None:
      return "Kein Audio.", ""

  aufnahme_pfad = audio if isinstance(audio, str) else None
  if not aufnahme_pfad:
      return "Kein Audio.", ""

  stt_start = time.perf_counter()
  frage_text = transkriberer.transkribiere_datei(aufnahme_pfad)
  stt_dauer  = time.perf_counter() - stt_start

  if not frage_text:
      return "Kein Text erkannt. Bitte nochmal sprechen.", ""

  frage_text = ersetze_gesprochene_ziffernfolgen(frage_text)
  zeiten = f"STT: {stt_dauer:.2f}s  |  Audio: {wav_info(aufnahme_pfad)}"
  return frage_text, zeiten


def antworte(frage_text):
  """LLM + TTS — nutzt den (evtl. korrigierten) Text aus dem Feld."""
  frage_text = (frage_text or "").strip()
  if not frage_text or frage_text.startswith("Kein"):
      return "", "", None, "Bitte zuerst transkribieren oder Text eingeben.", lade_verlauf_tabelle()

  gesamt_start = time.perf_counter()

  verlauf   = datenbank.lade_verlauf(anzahl=6)
  llm_start = time.perf_counter()
  ergebnis  = llm_client.frage(frage_text, verlauf)
  llm_dauer = time.perf_counter() - llm_start
  antwort_text = ergebnis["antwort"]

  tts_start = time.perf_counter()
  wav_pfad, _, _ = synthesizer.synthesiere(antwort_text)
  tts_dauer = time.perf_counter() - tts_start
  wav_pfad = os.path.abspath(wav_pfad)

  gesamt_dauer = time.perf_counter() - gesamt_start

  datenbank.speichere(
      frage     = frage_text,
      antwort   = antwort_text,
      dauer_stt = 0,
      dauer_llm = round(llm_dauer, 3),
      dauer_tts = round(tts_dauer, 3),
      dauer_ges = round(gesamt_dauer, 3),
  )

  zeiten = (
      f"LLM: {llm_dauer:.2f}s  |  "
      f"TTS: {tts_dauer:.2f}s  |  "
      f"Gesamt: {gesamt_dauer:.2f}s  |  "
      f"Tokens/s: {ergebnis['tokens_pro_s']}"
  )

  return frage_text, antwort_text, wav_pfad, zeiten, lade_verlauf_tabelle()


def lade_verlauf_tabelle():
    eintraege = datenbank.lade_alle()
    return [
        [
            e["zeitstempel"],
            e["frage"][:50],
            e["antwort"][:80],
            e["dauer_stt"],
            e["dauer_llm"],
            e["dauer_tts"],
            e["dauer_ges"],
        ]
        for e in eintraege
    ]


if __name__ == "__main__":
    demo = erstelle_interface(transkribiere, antworte, lade_verlauf_tabelle)
    demo.launch(
        server_name="127.0.0.1",
        server_port=PORT,
    )
