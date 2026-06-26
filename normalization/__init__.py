# normalization/__init__.py
# nur was noch existiert importieren:
from .numbers_de import (
    ersetze_gesprochene_ziffernfolgen,
    ersetze_ziffern_fuer_tts,
    zahl_zu_worten_de,
)
from .tts_text import bereite_text_fuer_tts, ersetze_rechen_symbole_fuer_tts

# stt_postprocess und stt_cleanup ENTFERNT — nicht mehr nötig mit Whisper