# core/id_map_db.py

import os
import sqlite3
import random
import string
from core.utils import makedir

class IDMapDB:
    def __init__(self, db_path: str = "id_map.db", start_length: int = 4, max_length: int = 8):
        self.db_path = db_path
        self._create_tables()
        self.start_length = start_length
        self.max_length = max_length
        self.length = start_length

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _create_tables(self):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS id_map (
                    short_id TEXT PRIMARY KEY,
                    full_id TEXT UNIQUE
                )
                """
            )
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_full_id ON id_map(full_id)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_short_id ON id_map(short_id)")
            conn.commit()

    # --- Core-Funktionen ---
    def shorten_id(self, full_id: str) -> str:
        """
        Liefert eine kurze ID für full_id. Wenn vorhanden, Rückgabe der bestehenden.
        Ansonsten neue ShortID generieren.
        """
        if not full_id:
            return None
        
        with self._connect() as conn:
            cur = conn.cursor()

            # prüfen, ob schon vorhanden
            cur.execute("SELECT short_id FROM id_map WHERE full_id = ?", (full_id,))
            row = cur.fetchone()
            if row:
                return row[0]

            # ansonsten neue ShortID generieren
            short_id = self._generate_unique_short_id(cur)
            cur.execute("INSERT INTO id_map (short_id, full_id) VALUES (?, ?)", (short_id, full_id))
            conn.commit()
            return short_id

    def expand_id(self, short_id: str) -> str:
        """
        Gibt die Original-ID zu einer kurzen ID zurück, oder None wenn unbekannt.
        """
        if not short_id:
            return None
        
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT full_id FROM id_map WHERE short_id = ?", (short_id,))
            row = cur.fetchone()
            return row[0] if row else short_id

    def clear_db(self):
        """
        Löscht alle Einträge aus der Datenbank.
        """        
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM id_map")
            conn.commit()
            cur.execute("VACUUM")  # physische Dateigröße zurücksetzen
        self.length = self.start_length

    def reset_db(self):
        """
        Löscht die gesamte Datenbankdatei und erstellt sie neu.
        """
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self._create_tables()
        self.length = self.start_length

    # --- Hilfsfunktionen ---
    def _generate_unique_short_id(self, cur) -> str:
        """
        Generiert eine neue zufällige 4-stellige ID.
        Prüft gegen DB, ob sie schon vergeben ist.
        """
        #alphabet = string.printable[:-6]  # 95 druckbare ASCII-Zeichen (ohne Whitespace-Steuerzeichen)
        alphabet = string.ascii_uppercase + string.digits  # 36 Zeichen        
        attempts = 0

        while True:            
            short_id = "".join(random.choices(alphabet, k=self.length))
            cur.execute("SELECT 1 FROM id_map WHERE short_id = ?", (short_id,))
            if not cur.fetchone():
                return short_id
            
            attempts += 1
            if attempts > 100:
                # Letzter Ausweg: Länge erhöhen oder Fehler
                if self.length < self.max_length:
                    self.length += 1
                    attempts = 0  # Reset counter
                else:
                    raise RuntimeError("Unable to generate unique short_id after many attempts")


_db_instance: IDMapDB = None

def init_idmap_db(db_path: str = ".sqlite", db_name: str = "id_map.db"):
    """
    Initialisiert die DB, falls noch nicht geschehen.
    """
    global _db_instance
    if _db_instance:
        print("Error Init IDMap DB: DB was already initialized.")
        return
    makedir(db_path)
    db_path = os.path.join(db_path, db_name)
    _db_instance = IDMapDB(db_path=db_path)

def get_idmap_db() -> IDMapDB:
    return _db_instance