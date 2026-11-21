"""校正与人工确认持久化：备注、重大判定原则确认。"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from core.model.entities import RunResult

MAX_REASON = 500


class CorrectionError(Exception):
    """校正记录不可读写。"""


class CorrectionStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._connection = sqlite3.connect(self.path)
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS corrections (
                    level INTEGER NOT NULL,
                    item_id TEXT NOT NULL,
                    asset_type TEXT NOT NULL,
                    field TEXT NOT NULL,
                    value TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (level, item_id, asset_type, field)
                )
                """
            )
            self._connection.commit()
        except sqlite3.Error as exc:
            raise CorrectionError(f"校正库不可用：{exc}") from exc

    def close(self) -> None:
        self._connection.close()

    def get(self, level: int, item_id: str, asset_type: str, field: str) -> str:
        row = self._connection.execute(
            "SELECT value FROM corrections WHERE level=? AND item_id=? AND asset_type=? AND field=?",
            (level, item_id, asset_type, field),
        ).fetchone()
        return str(row[0]) if row else ""

    def set(
        self,
        level: int,
        item_id: str,
        asset_type: str,
        field: str,
        value: str,
        reason: str = "",
    ) -> None:
        if len(reason) > MAX_REASON:
            raise CorrectionError(f"校正原因不能超过 {MAX_REASON} 字")
        if not value.strip():
            self._connection.execute(
                "DELETE FROM corrections WHERE level=? AND item_id=? AND asset_type=? AND field=?",
                (level, item_id, asset_type, field),
            )
        else:
            self._connection.execute(
                """
                INSERT INTO corrections (level, item_id, asset_type, field, value, reason, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(level, item_id, asset_type, field)
                DO UPDATE SET value=excluded.value, reason=excluded.reason,
                              updated_at=excluded.updated_at
                """,
                (
                    level,
                    item_id,
                    asset_type,
                    field,
                    value.strip(),
                    reason.strip(),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
        self._connection.commit()

    def notes(self, level: int) -> dict[tuple[str, str], str]:
        rows = self._connection.execute(
            "SELECT item_id, asset_type, value FROM corrections WHERE level=? AND field='note'",
            (level,),
        ).fetchall()
        return {(str(item), str(asset)): str(value) for item, asset, value in rows}

    def major_confirmed(self, level: int) -> set[tuple[str, str]]:
        rows = self._connection.execute(
            "SELECT item_id, asset_type FROM corrections WHERE level=? AND field='major' AND value='1'",
            (level,),
        ).fetchall()
        return {(str(item), str(asset)) for item, asset in rows}


def apply_notes(run_result: RunResult, store: CorrectionStore, level: int) -> None:
    notes = store.notes(level)
    if not notes:
        return
    for run in run_result.asset_runs:
        asset_type = run.asset.asset_type.value
        for result in run.items:
            note = notes.get((result.item_id, asset_type))
            if note:
                result.note = note
