# Lokaler Sprachassistent – Offline, Echtzeit-Streaming

Ein komplett lokaler, datenschutzfreundlicher Sprachassistent, der ohne Internetverbindung auskommt. Die Besonderheit: Text und Audio erscheinen synchron Wort für Wort – während die KI-Antwort generiert wird, wird sie gleichzeitig vorgelesen.

---

##  Inhaltsverzeichnis

- Überblick  
- Features  
- Technische Architektur  
- Voraussetzungen  
- Installation  
- Modelle herunterladen  
- Starten  
- Projektstruktur  
- Workflow  
- Technische Details  
- Fehlerbehebung  


---

##  Überblick

Dieser Sprachassistent wurde im Rahmen eines Praktikums entwickelt und demonstriert die synchronisierte Ausgabe von Text und Sprache in Echtzeit.

Das Kernproblem, das gelöst wurde:  
Bei herkömmlichen Systemen erscheint der Text sofort, aber das Audio kommt erst am Ende. Hier erscheint jedes Wort genau dann, wenn es vorgelesen wird – Text und Audio sind perfekt synchron.

---

##  Features

| Feature | Beschreibung |
|--------|-------------|
| Wake Word-Erkennung | Sag "Computer" – der Assistent aktiviert sich (kein Button-Druck) |
| Offline STT | Whisper erkennt Sprache (deutsch, sehr genau) |
| Offline LLM | Gemma3 via Ollama – komplett lokal, keine API-Kosten |
| Offline TTS | Piper mit Thorsten-Stimme (deutsch, männlich) |
| Echtzeit-Streaming | Antwort erscheint Wort für Wort – synchron zum Audio |
| Datenbank | Alle Gespräche werden lokal gespeichert (SQLite) |
| Web-UI | Gradio-Oberfläche mit Status, Frage, Antwort, Audio und Verlauf |

---

##  Technische Architektur

### Die Pipeline im Überblick

┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ Wake │ │ Mikrofon │ │ Whisper │ │ Gemma3 │
│ Word │───▶│ Aufnahme │───▶│ STT │───▶│ LLM │
│ (Vosk) │ │ │ │ │ │ (Streaming)│
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
│
▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ Audio │◀───│ Piper │◀───│ Sentence │◀───│ Wort-für- │
│ Player │ │ Worker │ │ Chunker │ │ Wort │
│ (Stream) │ │(Synthese) │ │(Sätze bauen)│ │ (Token) │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
│
▼
┌─────────────┐
│ UI │
│ Text + │
│ Audio │
└─────────────┘



---

### Streaming-Pipeline im Detail

LLM-Stream (Wort für Wort)
│
▼
SentenceChunker (sammelt zu Sätzen)
│
▼
┌──────────────────────────────────────────────┐
│ QUEUE-BASIERTE PIPELINE │
│ │
│ [text_queue] → PiperWorker → [audio_queue] │
│ (max 4 Sätze) (Thread 1) (max 4 Audio) │
└──────────────────────────────────────────────┘
│ │
▼ ▼
UI-Text aktualisiert AudioPlayer (Thread 2)
synchron zum Audio kontinuierlicher Stream


Der entscheidende Mechanismus:  
Der AudioPlayer synchronisiert gesprochene Wörter mit dem Audio-Stream und zeigt genau diese Wörter in der UI an.

---

##  Voraussetzungen

| Komponente | Version | Hinweis |
|------------|--------|--------|
| Python | 3.10 oder 3.11 | 3.12 kann Probleme machen |
| Ollama | Neueste | Für Gemma3 |
| RAM | min. 8 GB | Empfohlen 16 GB |
| Speicher | min. 5 GB | Für Modelle |
| Betriebssystem | Windows / Linux / macOS | Getestet |

---

##  Installation

### 1. Repository klonen
```bash
git clone https://github.com/DEIN_BENUTZERNAME/lokaler-sprachassistent.git
cd lokaler-sprachassistent
```

2. Virtuelle Umgebung erstellen
python -m venv venv
source venv/bin/activate
venv\Scripts\activate
3. Abhängigkeiten installieren
pip install -r requirements.txt
📥 Modelle herunterladen
A) Vosk (Wake Word)
wget https://alphacephei.com/vosk/models/vosk-model-small-de-0.15.zip
unzip vosk-model-small-de-0.15.zip
mv vosk-model-small-de-0.15 models/
B) Piper (TTS)

Wird automatisch beim ersten Start geladen.

C) Ollama / Gemma3
ollama pull gemma3:1b
ollama pull gemma3:4b
D) Whisper

Wird automatisch beim ersten Transkribieren heruntergeladen.

### Starten
1. Ollama starten
ollama serve
2. Assistent starten
python main.py
3. UI öffnen
http://127.0.0.1:7860
4. Nutzung

Sage: "Computer" und stelle deine Frage.

### Projektstruktur

Sprachassistent/
│
├── main.py
│
├── stt/
│   ├── recorder.py
│   └── whisper_transcriber.py
│
├── llm/
│   └── ollama_client.py
│
├── tts/
│   ├── synthesizer.py
│   ├── text_chunker.py
│   ├── piper_worker.py
│   ├── audio_player.py
│   └── streaming_pipeline.py
│
├── wakeword/
│   └── wakeword_listener.py
│
├── database/
│   └── db.py
│
├── ui/
│   └── interface.py
│
├── normalization/
│   ├── numbers_de.py
│   └── tts_text.py
│
├── models/
│   ├── vosk-model-small-de-0.15/
│   └── piper/
│
├── outputs/
│   └── tts/
│
├── requirements.txt
└── README.md

### Workflow

1. Du sagst "Computer"
↓
2. WakeWordListener erkennt Aktivierung
↓
3. Mikrofon nimmt Frage auf
↓
4. Whisper transkribiert Text
↓
5. Gemma3 generiert Antwort (Streaming)
↓
6. SentenceChunker bildet Sätze
↓
7. Piper erzeugt Audio
↓
8. AudioPlayer spielt Audio ab
↓
9. UI zeigt synchron Wörter an
↓
10. Speicherung in SQLite
↓
11. Zurück in Idle-Modus

Technische Details

Synchronisation
'''
def _write_samples_word_sync(self, samples, words):
    total = len(samples)
    for start in range(0, total, block):
        self._stream.write(samples[start:end])
        progress = end / total
        n = int(progress * len(words))
        self._reveal_n_words(n)
Backpressure
'''

Das System passt sich automatisch der langsamsten Komponente an.

Wake Word Entscheidung

Vosk wurde gewählt, da Whisper zu ungenau für Wake Words ist.

