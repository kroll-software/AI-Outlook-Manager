# core/contact_db.py

import os
import datetime
import sqlite3
from typing import List, Optional
from core.utils import makedir, get_settings_dir

class ContactDB:
    def __init__(self, db_path: str = "contacts.db"):
        self.db_path = db_path
        self._create_tables()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _create_tables(self):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS Contacts (
                    email TEXT PRIMARY KEY,
                    displayname TEXT,
                    created TIMESTAMP,
                    changed TIMESTAMP
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS Lists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS ContactLists (
                    contact_email TEXT,
                    list_id INTEGER,
                    FOREIGN KEY(contact_email) REFERENCES Contacts(email) ON DELETE CASCADE,
                    FOREIGN KEY(list_id) REFERENCES Lists(id) ON DELETE CASCADE,
                    PRIMARY KEY(contact_email, list_id)
                )
            """)
            conn.commit()

    def add_contact(self, email: str, displayname: Optional[str] = None):
        now = datetime.datetime.utcnow()
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO Contacts(email, displayname, created, changed)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE
                SET displayname=excluded.displayname,
                    changed=excluded.changed
            """, (email, displayname, now, now))
            conn.commit()

    def create_list(self, name: str):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO Lists(name) VALUES(?)", (name,))
            conn.commit()

    def delete_list(self, name: str):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM Lists WHERE name=?", (name,))
            conn.commit()
            c.execute("VACUUM")  # physische Dateigröße zurücksetzen

    def list_lists(self) -> List[str]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT name FROM Lists ORDER BY name")
            return [row[0] for row in c.fetchall()]    

    def add_email_to_list(self, email: str, list_name: str, displayname: Optional[str] = None) -> bool:
        """
        Add an email to a list (many-to-many via ContactLists).
        Ensures the contact exists and links it to the given list.

        Returns:
            True if the contact was newly added to the list,
            False if it was already present.
        """
        # Ensure contact exists (creates if missing)
        self.add_contact(email, displayname)

        with self._connect() as conn:
            c = conn.cursor()

            # Resolve list_id
            c.execute("SELECT id FROM Lists WHERE name=?", (list_name,))
            row = c.fetchone()
            if not row:
                raise ValueError(f"List '{list_name}' does not exist.")
            list_id = row[0]

            # Insert into junction table (or ignore if already linked)
            c.execute("""
                INSERT OR IGNORE INTO ContactLists(contact_email, list_id)
                VALUES(?, ?)
            """, (email, list_id))
            conn.commit()

            return c.rowcount > 0  # True = new link created, False = already existed


    def remove_email_from_list(self, email: str, list_name: str):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM Lists WHERE name=?", (list_name,))
            row = c.fetchone()
            if not row:
                raise ValueError(f"List '{list_name}' does not exist.")
            list_id = row[0]
            c.execute("DELETE FROM ContactLists WHERE contact_email=? AND list_id=?", (email, list_id))
            conn.commit()

    def get_emails(self, list_name: str) -> List[str]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM Lists WHERE name=?", (list_name,))
            row = c.fetchone()
            if not row:
                raise ValueError(f"List '{list_name}' does not exist.")
            list_id = row[0]
            c.execute("""
                SELECT c.email
                FROM Contacts c
                JOIN ContactLists cl ON c.email = cl.contact_email
                WHERE cl.list_id=?
                ORDER BY c.email
            """, (list_id,))
            return [row[0] for row in c.fetchall()]


_db_instance: ContactDB = None

def init_contact_db(db_path: str = ".sqlite", db_name: str = "contacts.db"):
    global _db_instance
    if _db_instance:
        print("Error Init Contact DB: DB was already initialized.")
        return    
    makedir(db_path)
    db_path = os.path.join(db_path, db_name)
    _db_instance = ContactDB(db_path=db_path)    

def get_contact_db() -> ContactDB:    
    return _db_instance