"""
SQLite-backed FSM storage for aiogram 3.x.

Replaces ``MemoryStorage`` so that FSM state (including the ``last_urls``
key written by the rescan feature) survives bot restarts.

Usage in bot_aiogram.py::

    from fsm_storage import SQLiteStorage
    dp = Dispatcher(storage=SQLiteStorage())
"""

import json
from typing import Any, Dict, Optional

import aiosqlite
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey

from logger import setup_logger

logger = setup_logger()

# Re-use the same database file as the rest of the project.
_DB_FILE = "gateway_checker.db"


class SQLiteStorage(BaseStorage):
    """
    Persistent FSM storage backed by the ``fsm_state`` SQLite table.

    The table is created by ``database.py``'s ``Database.initialize()`` so it
    will always exist by the time the bot starts polling.  We open a fresh
    connection per operation (no long-lived connection) to stay compatible with
    how the rest of the project uses aiosqlite.
    """

    def __init__(self, db_path: str = _DB_FILE) -> None:
        self._db_path = db_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_table(self, db: aiosqlite.Connection) -> None:
        """Create the table if it does not exist yet (defensive fallback)."""
        await db.execute("""
            CREATE TABLE IF NOT EXISTS fsm_state (
                chat_id   INTEGER NOT NULL,
                user_id   INTEGER NOT NULL,
                state     TEXT,
                data      TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (chat_id, user_id)
            )
        """)
        await db.commit()

    # ------------------------------------------------------------------
    # BaseStorage interface
    # ------------------------------------------------------------------

    async def set_state(
        self,
        key: StorageKey,
        state: Optional[State] = None,
    ) -> None:
        """Persist the FSM state for *key*."""
        state_name: Optional[str] = state.state if state is not None else None
        chat_id = key.chat_id
        user_id = key.user_id

        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_table(db)

            # Read existing data so we don't clobber it.
            cursor = await db.execute(
                "SELECT data FROM fsm_state WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            )
            row = await cursor.fetchone()
            existing_data = row[0] if row else "{}"

            from datetime import datetime

            await db.execute("""
                INSERT INTO fsm_state (chat_id, user_id, state, data, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    state = excluded.state,
                    updated_at = excluded.updated_at
            """, (chat_id, user_id, state_name, existing_data, datetime.now().isoformat()))

            await db.commit()

        logger.debug(f"FSM set_state: ({chat_id}, {user_id}) → {state_name!r}")

    async def get_state(self, key: StorageKey) -> Optional[str]:
        """Return the stored state name for *key*, or ``None``."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT state FROM fsm_state WHERE chat_id = ? AND user_id = ?",
                (key.chat_id, key.user_id),
            )
            row = await cursor.fetchone()
            return row[0] if row else None

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        """Persist the FSM data dict for *key*."""
        chat_id = key.chat_id
        user_id = key.user_id
        serialised = json.dumps(data, ensure_ascii=False)

        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_table(db)

            # Read current state so we don't clobber it.
            cursor = await db.execute(
                "SELECT state FROM fsm_state WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            )
            row = await cursor.fetchone()
            current_state = row[0] if row else None

            from datetime import datetime

            await db.execute("""
                INSERT INTO fsm_state (chat_id, user_id, state, data, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    data = excluded.data,
                    updated_at = excluded.updated_at
            """, (chat_id, user_id, current_state, serialised, datetime.now().isoformat()))

            await db.commit()

        logger.debug(f"FSM set_data: ({chat_id}, {user_id}) keys={list(data.keys())}")

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        """Return the stored data dict for *key* (empty dict if absent)."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT data FROM fsm_state WHERE chat_id = ? AND user_id = ?",
                (key.chat_id, key.user_id),
            )
            row = await cursor.fetchone()

        if not row or not row[0]:
            return {}

        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            logger.warning(
                f"FSM get_data: corrupt JSON for ({key.chat_id}, {key.user_id}), resetting"
            )
            return {}

    async def close(self) -> None:
        """No persistent connection to close."""
        pass
