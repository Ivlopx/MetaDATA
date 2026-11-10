from datetime import datetime
from pathlib import Path
import sqlite3

from .model import clean
from .image_cache import asset_name


class History:
    """History of selected, classified music, not proof of what passed through the mixer."""
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path)
        self.db.execute("""CREATE TABLE IF NOT EXISTS songs (
            id INTEGER PRIMARY KEY, played_at TEXT NOT NULL,
            source TEXT NOT NULL, artist TEXT NOT NULL, title TEXT NOT NULL)""")
        self.db.commit()
        existing = {row[1] for row in self.db.execute("PRAGMA table_info(songs)")}
        for column, sql_type in (("album", "TEXT"), ("year", "TEXT"), ("genre", "TEXT"),
                                 ("isrc", "TEXT"), ("duration_ms", "INTEGER"), ("artwork_origin", "TEXT"), ("artwork_file", "TEXT")):
            if column not in existing:
                self.db.execute(f"ALTER TABLE songs ADD COLUMN {column} {sql_type}")
        self.db.commit()
        self.last = None

    def record(self, decision):
        track = decision.song
        key = (track.source, clean(track.artist), clean(track.title), clean(track.album)) if track else None
        if key is not None and key != self.last:
            self.db.execute("""INSERT INTO songs(played_at,source,artist,title,album,year,genre,isrc,duration_ms,artwork_origin,artwork_file)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                            (datetime.now().astimezone().isoformat(timespec="seconds"), *key,
                             clean(track.year), clean(track.genre), clean(track.isrc),
                             track.duration_ms, clean(track.artwork_origin), asset_name(track.artwork)))
            self.db.commit()
        self.last = key

    def recent(self, limit=200):
        return self.db.execute("SELECT played_at,source,artist,title,album,year FROM songs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def recent_artwork_files(self, limit=200):
        rows = self.db.execute('SELECT artwork_file FROM songs ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        return list(dict.fromkeys(row[0] for row in rows if row[0]))

    def close(self):
        self.db.close()
