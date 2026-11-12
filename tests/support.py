import sqlite3
from pathlib import Path


class SQLiteD1:
    def __init__(self):
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(Path('migrations/0001_initial.sql').read_text())
        self.query("INSERT INTO installation(id,installation_id) VALUES(1,'test-install')")

    def query(self, sql, params=()):
        cursor = self.connection.execute(sql, params)
        rows = [dict(row) for row in cursor.fetchall()]
        self.connection.commit()
        return rows
