"""
database/db.py
SQLite Datenbank — speichert alle Gespräche lokal.
"""

import sqlite3
import os
from datetime import datetime


DB_PFAD = "database/gespraeche.db"


class Datenbank:
    """
    Verwaltet die SQLite Datenbank für Gesprächsverläufe.
    """

    def __init__(self, db_pfad: str = DB_PFAD):
        os.makedirs(os.path.dirname(db_pfad), exist_ok=True)
        self.db_pfad = db_pfad
        self._erstelle_tabellen()
        print(f"✓ Datenbank bereit: {db_pfad}")

    def _verbinden(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_pfad)

    def _erstelle_tabellen(self):
        """Erstellt die Tabellen beim ersten Start."""
        with self._verbinden() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS gespraeche (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    zeitstempel TEXT    NOT NULL,
                    frage       TEXT    NOT NULL,
                    antwort     TEXT    NOT NULL,
                    dauer_stt_s REAL,
                    dauer_llm_s REAL,
                    dauer_tts_s REAL,
                    dauer_ges_s REAL
                )
            """)
            self._migrate(conn)
            conn.commit()

    def _migrate(self, conn):
        """Fügt fehlende Spalten in bestehenden Datenbanken hinzu."""
        spalten = {row[1] for row in conn.execute("PRAGMA table_info(gespraeche)")}
        if "dauer_tts_s" not in spalten:
            conn.execute("ALTER TABLE gespraeche ADD COLUMN dauer_tts_s REAL")

    def speichere(self, frage: str, antwort: str,
                  dauer_stt: float = None,
                  dauer_llm: float = None,
                  dauer_tts: float = None,
                  dauer_ges: float = None) -> int:
        """
        Speichert ein Gespräch in der Datenbank.
        Gibt die ID des neuen Eintrags zurück.
        """
        zeitstempel = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._verbinden() as conn:
            cursor = conn.execute("""
                INSERT INTO gespraeche
                    (zeitstempel, frage, antwort, dauer_stt_s, dauer_llm_s, dauer_tts_s, dauer_ges_s)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (zeitstempel, frage, antwort, dauer_stt, dauer_llm, dauer_tts, dauer_ges))
            conn.commit()
            return cursor.lastrowid

    def lade_verlauf(self, anzahl: int = 10) -> list:
        """
        Lädt die letzten N Gespräche für den Kontext.
        Returns: Liste von {"frage": ..., "antwort": ...}
        """
        with self._verbinden() as conn:
            rows = conn.execute("""
                SELECT frage, antwort FROM gespraeche
                ORDER BY id DESC LIMIT ?
            """, (anzahl,)).fetchall()
        # Umgekehrte Reihenfolge — älteste zuerst
        return [{"frage": r[0], "antwort": r[1]} for r in reversed(rows)]

    def lade_alle(self) -> list:
        """Lädt alle Gespräche für die Anzeige in der UI."""
        with self._verbinden() as conn:
            rows = conn.execute("""
                SELECT id, zeitstempel, frage, antwort,
                       dauer_stt_s, dauer_llm_s, dauer_tts_s, dauer_ges_s
                FROM gespraeche ORDER BY id DESC
            """).fetchall()
        return [
            {
                "id":          r[0],
                "zeitstempel": r[1],
                "frage":       r[2],
                "antwort":     r[3],
                "dauer_stt":   r[4],
                "dauer_llm":   r[5],
                "dauer_tts":   r[6],
                "dauer_ges":   r[7],
            }
            for r in rows
        ]

    def loesche_alle(self):
        """Löscht alle Einträge — für Tests."""
        with self._verbinden() as conn:
            conn.execute("DELETE FROM gespraeche")
            conn.commit()
        print("✓ Datenbank geleert.")