"""SQLite storage for the bot.

Two ideas drive this design, and both exist so you can sell the same bot
to many servers without rewriting it:

1. **Everything is scoped by `guild_id`.** One running bot serves many
   servers, and each one has its own settings, warns and XP. Nothing is
   global.

2. **Settings are a generic key/value table.** Adding a new configurable
   option later needs no database migration — you just start calling
   `set_setting(guild, "my_new_option", value)`. That's what makes
   "can you also make it do X?" a ten-minute job instead of a rewrite.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import aiosqlite


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    guild_id INTEGER NOT NULL,
    key      TEXT    NOT NULL,
    value    TEXT,
    PRIMARY KEY (guild_id, key)
);

CREATE TABLE IF NOT EXISTS warns (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id     INTEGER NOT NULL,
    user_id      INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason       TEXT    NOT NULL,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_warns_lookup ON warns (guild_id, user_id);

CREATE TABLE IF NOT EXISTS levels (
    guild_id        INTEGER NOT NULL,
    user_id         INTEGER NOT NULL,
    xp              INTEGER NOT NULL DEFAULT 0,
    last_message_at REAL    NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_levels_board ON levels (guild_id, xp DESC);
"""


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database.connect() was never awaited")
        return self._conn

    # -----------------------------------------------------------------
    # Per-guild settings
    # -----------------------------------------------------------------

    async def get_setting(self, guild_id: int, key: str, default: Any = None) -> Any:
        async with self.conn.execute(
            "SELECT value FROM settings WHERE guild_id = ? AND key = ?",
            (guild_id, key),
        ) as cursor:
            row = await cursor.fetchone()
        return row["value"] if row else default

    async def set_setting(self, guild_id: int, key: str, value: Any) -> None:
        await self.conn.execute(
            "INSERT INTO settings (guild_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value",
            (guild_id, key, None if value is None else str(value)),
        )
        await self.conn.commit()

    async def get_int_setting(self, guild_id: int, key: str) -> Optional[int]:
        """Settings are stored as text; channel and role IDs need ints back."""
        raw = await self.get_setting(guild_id, key)
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    async def clear_setting(self, guild_id: int, key: str) -> None:
        await self.conn.execute(
            "DELETE FROM settings WHERE guild_id = ? AND key = ?", (guild_id, key)
        )
        await self.conn.commit()

    # -----------------------------------------------------------------
    # Warns
    # -----------------------------------------------------------------

    async def add_warn(
        self, guild_id: int, user_id: int, moderator_id: int, reason: str
    ) -> int:
        cursor = await self.conn.execute(
            "INSERT INTO warns (guild_id, user_id, moderator_id, reason) "
            "VALUES (?, ?, ?, ?)",
            (guild_id, user_id, moderator_id, reason),
        )
        await self.conn.commit()
        return cursor.lastrowid or 0

    async def get_warns(self, guild_id: int, user_id: int) -> list[aiosqlite.Row]:
        async with self.conn.execute(
            "SELECT * FROM warns WHERE guild_id = ? AND user_id = ? "
            "ORDER BY created_at DESC",
            (guild_id, user_id),
        ) as cursor:
            return list(await cursor.fetchall())

    async def clear_warns(self, guild_id: int, user_id: int) -> int:
        cursor = await self.conn.execute(
            "DELETE FROM warns WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        )
        await self.conn.commit()
        return cursor.rowcount

    # -----------------------------------------------------------------
    # Leveling
    # -----------------------------------------------------------------

    async def get_xp(self, guild_id: int, user_id: int) -> tuple[int, float]:
        """Return (xp, last_message_timestamp) for a member."""
        async with self.conn.execute(
            "SELECT xp, last_message_at FROM levels WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
        return (row["xp"], row["last_message_at"]) if row else (0, 0.0)

    async def add_xp(
        self, guild_id: int, user_id: int, amount: int, timestamp: float
    ) -> int:
        """Add XP and return the member's new total."""
        await self.conn.execute(
            "INSERT INTO levels (guild_id, user_id, xp, last_message_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET "
            "xp = xp + excluded.xp, last_message_at = excluded.last_message_at",
            (guild_id, user_id, amount, timestamp),
        )
        await self.conn.commit()
        total, _ = await self.get_xp(guild_id, user_id)
        return total

    async def get_leaderboard(self, guild_id: int, limit: int = 10) -> list[aiosqlite.Row]:
        async with self.conn.execute(
            "SELECT user_id, xp FROM levels WHERE guild_id = ? "
            "ORDER BY xp DESC LIMIT ?",
            (guild_id, limit),
        ) as cursor:
            return list(await cursor.fetchall())

    async def get_rank(self, guild_id: int, user_id: int) -> int:
        """1-based position on the leaderboard. 0 means unranked."""
        async with self.conn.execute(
            "SELECT COUNT(*) + 1 AS rank FROM levels "
            "WHERE guild_id = ? AND xp > (SELECT xp FROM levels "
            "WHERE guild_id = ? AND user_id = ?)",
            (guild_id, guild_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
        return row["rank"] if row else 0
