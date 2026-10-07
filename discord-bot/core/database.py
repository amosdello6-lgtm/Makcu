"""SQLite storage. Everything is scoped by guild_id so one instance can
serve many servers with independent configuration."""

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

CREATE TABLE IF NOT EXISTS tickets (
    channel_id INTEGER PRIMARY KEY,
    guild_id   INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    closed     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_tickets_open ON tickets (guild_id, user_id, closed);

CREATE TABLE IF NOT EXISTS role_menu_options (
    message_id INTEGER NOT NULL,
    guild_id   INTEGER NOT NULL,
    role_id    INTEGER NOT NULL,
    label      TEXT    NOT NULL,
    PRIMARY KEY (message_id, role_id)
);

CREATE TABLE IF NOT EXISTS blocked_words (
    guild_id INTEGER NOT NULL,
    word     TEXT    NOT NULL,
    PRIMARY KEY (guild_id, word)
);
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

    # Settings -- a generic key/value store so new options need no migration.

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

    # Warns

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

    # Leveling

    async def get_xp(self, guild_id: int, user_id: int) -> tuple[int, float]:
        async with self.conn.execute(
            "SELECT xp, last_message_at FROM levels WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
        return (row["xp"], row["last_message_at"]) if row else (0, 0.0)

    async def add_xp(
        self, guild_id: int, user_id: int, amount: int, timestamp: float
    ) -> int:
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
        async with self.conn.execute(
            "SELECT COUNT(*) + 1 AS rank FROM levels "
            "WHERE guild_id = ? AND xp > (SELECT xp FROM levels "
            "WHERE guild_id = ? AND user_id = ?)",
            (guild_id, guild_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
        return row["rank"] if row else 0

    # Tickets

    async def create_ticket(self, channel_id: int, guild_id: int, user_id: int) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO tickets (channel_id, guild_id, user_id) "
            "VALUES (?, ?, ?)",
            (channel_id, guild_id, user_id),
        )
        await self.conn.commit()

    async def get_ticket(self, channel_id: int) -> Optional[aiosqlite.Row]:
        async with self.conn.execute(
            "SELECT * FROM tickets WHERE channel_id = ?", (channel_id,)
        ) as cursor:
            return await cursor.fetchone()

    async def close_ticket(self, channel_id: int) -> None:
        await self.conn.execute(
            "UPDATE tickets SET closed = 1 WHERE channel_id = ?", (channel_id,)
        )
        await self.conn.commit()

    async def count_open_tickets(self, guild_id: int, user_id: int) -> int:
        async with self.conn.execute(
            "SELECT COUNT(*) AS n FROM tickets "
            "WHERE guild_id = ? AND user_id = ? AND closed = 0",
            (guild_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
        return row["n"] if row else 0

    # Role menus

    async def add_role_option(
        self, message_id: int, guild_id: int, role_id: int, label: str
    ) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO role_menu_options "
            "(message_id, guild_id, role_id, label) VALUES (?, ?, ?, ?)",
            (message_id, guild_id, role_id, label),
        )
        await self.conn.commit()

    async def get_role_options(self, message_id: int) -> list[aiosqlite.Row]:
        async with self.conn.execute(
            "SELECT * FROM role_menu_options WHERE message_id = ?", (message_id,)
        ) as cursor:
            return list(await cursor.fetchall())

    async def role_option_exists(self, guild_id: int, role_id: int) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM role_menu_options WHERE guild_id = ? AND role_id = ? LIMIT 1",
            (guild_id, role_id),
        ) as cursor:
            return await cursor.fetchone() is not None

    # Blocked words

    async def add_blocked_word(self, guild_id: int, word: str) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO blocked_words (guild_id, word) VALUES (?, ?)",
            (guild_id, word.lower()),
        )
        await self.conn.commit()

    async def remove_blocked_word(self, guild_id: int, word: str) -> int:
        cursor = await self.conn.execute(
            "DELETE FROM blocked_words WHERE guild_id = ? AND word = ?",
            (guild_id, word.lower()),
        )
        await self.conn.commit()
        return cursor.rowcount

    async def get_blocked_words(self, guild_id: int) -> list[str]:
        async with self.conn.execute(
            "SELECT word FROM blocked_words WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            return [row["word"] for row in await cursor.fetchall()]
