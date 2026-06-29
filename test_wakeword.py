"""
test_wakeword.py
Live-Test für die Vosk-Wake-Word-Erkennung 
"""

import time

from wakeword.wakeword_listener import start_wakeword_listener


hits = {"n": 0}


def on_wake():
    hits["n"] += 1
    print(f"\n>>> WAKE WORD #{hits['n']} erkannt!\n")


if __name__ == "__main__":
    print("=== Wake-Word Live-Test (30s) ===")
    print("Sage jetzt mehrmals 'Computer'.\n")
    listener = start_wakeword_listener(on_wake, ["computer"])
    time.sleep(30)
    listener.stop()
    print(f"\n=== Testende. {hits['n']} Wake-Word(s) erkannt. ===")
