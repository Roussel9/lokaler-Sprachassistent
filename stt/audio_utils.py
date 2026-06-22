"""
Lädt Audio für Vosk — minimale Verarbeitung, kein Beschneiden/Verzerren.
Die WAV-Datei aus Gradio ist dieselbe, die der Nutzer abhört.
"""

import wave

import numpy as np
import scipy.io.wavfile as wavfile
import scipy.signal as ss

SAMPLE_RATE = 16000
MIN_DAUER_S = 0.25


def lade_wav_fuer_vosk(wav_pfad: str) -> tuple[np.ndarray, str | None]:
    """Liest die Gradio-WAV-Datei und konvertiert nur das Nötigste für Vosk."""
    try:
        sample_rate, audio = wavfile.read(wav_pfad)
    except Exception:
        return np.array([], dtype=np.int16), f"Audio-Datei konnte nicht gelesen werden: {wav_pfad}"

    return _zu_vosk_pcm(audio, int(sample_rate))


def _zu_vosk_pcm(audio: np.ndarray, sample_rate: int) -> tuple[np.ndarray, str | None]:
    """Nur Mono + 16 kHz + int16 — keine Stille-Entfernung, keine Normalisierung."""
    if audio is None or len(audio) == 0:
        return np.array([], dtype=np.int16), "Kein Audio empfangen."

    audio = np.asarray(audio)

    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    if np.issubdtype(audio.dtype, np.floating):
        audio = np.clip(audio, -1.0, 1.0)
        audio = (audio * 32767.0).astype(np.int16)
    elif audio.dtype == np.int32:
        audio = (audio / 65536).astype(np.int16)
    elif audio.dtype == np.uint8:
        audio = ((audio.astype(np.int16) - 128) * 256)
    else:
        audio = audio.astype(np.int16)

    if sample_rate != SAMPLE_RATE:
        audio_float = audio.astype(np.float64) / 32768.0
        g = np.gcd(sample_rate, SAMPLE_RATE)
        up = SAMPLE_RATE // g
        down = sample_rate // g
        audio_float = ss.resample_poly(audio_float, up, down)
        audio = np.clip(audio_float * 32768.0, -32768, 32767).astype(np.int16)

    if len(audio) < int(MIN_DAUER_S * SAMPLE_RATE):
        return audio, f"Aufnahme zu kurz (min. {MIN_DAUER_S}s)."

    return audio, None


def wav_info(wav_pfad: str) -> str:
    """Kurze Info zur WAV-Datei (Debug)."""
    try:
        with wave.open(wav_pfad, "rb") as wf:
            return (
                f"{wf.getframerate()}Hz, "
                f"{wf.getnchannels()}ch, "
                f"{wf.getsampwidth() * 8}bit, "
                f"{wf.getnframes()} samples"
            )
    except Exception:
        return "unbekannt"
