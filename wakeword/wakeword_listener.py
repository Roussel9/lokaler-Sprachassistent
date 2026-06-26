"""
Wake Word-Erkennung mit Whisper tiny – mit Toleranz für ähnliche Wörter.
"""

import threading
import time
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

class WakeWordListener:
    def __init__(self, callback, wake_words=["assistent", "jarvis"]):
        self.callback = callback
        self.wake_words = [w.lower() for w in wake_words]
        self.running = False
        self.model = WhisperModel("tiny", device="cpu", compute_type="int8")
        self.count = 0
        
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._listen, daemon=True)
        self.thread.start()
        print(f"👂 Höre auf: {self.wake_words}")
        
    def stop(self):
        self.running = False
        
    def _listen(self):
        with sd.InputStream(samplerate=16000, channels=1, dtype='float32') as stream:
            print("✅ Mikrofon-Stream gestartet")
            while self.running:
                try:
                    # 2 Sekunden aufnehmen
                    audio, _ = stream.read(32000)
                    audio = audio.flatten()
                    self.count += 1
                    
                    # Lautstärke prüfen
                    rms = np.sqrt(np.mean(audio ** 2))
                    if rms < 0.005:
                        continue
                    
                    # Whisper transkribieren
                    segments, _ = self.model.transcribe(
                        audio,
                        language="de",
                        beam_size=1,
                        vad_filter=True,
                        no_speech_threshold=0.6,
                    )
                    text = " ".join(s.text for s in segments).lower().strip()
                    
                    if text:
                        print(f"📝 Whisper erkannt: '{text}'")
                        # Prüfe ob eines der Wake Words im Text ist (mit Toleranz)
                        for word in self.wake_words:
                            # Exakte Übereinstimmung oder Teilwort
                            if word in text or text in word:
                                print(f"✅ WAKE WORD '{word}' erkannt!")
                                self.callback()
                                time.sleep(2.0)
                                break
                                
                except Exception as e:
                    print(f"❌ Wake Word Fehler: {e}")
                    time.sleep(0.5)

def start_wakeword_listener(callback, wake_words=["assistent", "jarvis"]):
    listener = WakeWordListener(callback, wake_words)
    listener.start()
    return listener