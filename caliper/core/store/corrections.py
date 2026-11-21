"""校正与人工确认持久化：备注、重大判定原则确认。"""

from __future__ import annotations

import json
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
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS record_overrides (
                    level INTEGER NOT NULL,
                    item_id TEXT NOT NULL,
                    asset_key TEXT NOT NULL,
                    result_text TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    note TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (level, item_id, asset_key)
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS record_override_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level INTEGER NOT NULL,
                    item_id TEXT NOT NULL,
                    asset_key TEXT NOT NULL,
                    changes TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS record_reviews (
                    level INTEGER NOT NULL,
                    item_id TEXT NOT NULL,
                    asset_key TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (level, item_id, asset_key)
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

    def record_overrides(self, level: int, asset_key: str) -> dict[str, dict[str, str]]:
        rows = self._connection.execute(
            """
            SELECT item_id, result_text, verdict, note, reason
            FROM record_overrides WHERE level=? AND asset_key=?
            """,
            (level, asset_key),
        ).fetchall()
        return {
            str(item_id): {
                "result_text": str(result_text),
                "verdict": str(verdict),
                "note": str(note),
                "reason": str(reason),
            }
            for item_id, result_text, verdict, note, reason in rows
        }

    def reviewed_records(self, level: int, asset_key: str) -> dict[str, str]:
        rows = self._connection.execute(
            """
            SELECT item_id, updated_at FROM record_reviews
            WHERE level=? AND asset_key=?
            """,
            (level, asset_key),
        ).fetchall()
        return {str(item_id): str(updated_at) for item_id, updated_at in rows}

    def confirm_record(self, level: int, item_id: str, asset_key: str) -> str:
        now = datetime.now().isoformat(timespec="seconds")
        self._connection.execute(
            """
            INSERT INTO record_reviews (level, item_id, asset_key, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(level, item_id, asset_key)
            DO UPDATE SET updated_at=excluded.updated_at
            """,
            (level, item_id, asset_key, now),
        )
        self._connection.commit()
        return now

    def save_record_override(
        self,
        level: int,
        item_id: str,
        asset_key: str,
        result_text: str,
        verdict: str,
        note: str,
        reason: str,
        asset_type: str = "",
    ) -> str:
        """Save editable record fields and append a small, local change history."""
        reason = reason.strip()
        if len(reason) > MAX_REASON:
            raise CorrectionError(f"修改理由不能超过 {MAX_REASON} 字")
        current_row = self._connection.execute(
            """
            SELECT result_text, verdict, note FROM record_overrides
            WHERE level=? AND item_id=? AND asset_key=?
            """,
            (level, item_id, asset_key),
        ).fetchone()
        current = None
        if current_row:
            current = {
                "result_text": str(current_row[0]),
                "verdict": str(current_row[1]),
                "note": str(current_row[2]),
            }
        updated = {
            "result_text": result_text,
            "verdict": verdict,
            "note": note,
        }
        if current != updated and not reason:
            raise CorrectionError("请填写修改理由，便于后续复核")
        if current == updated:
            return self.confirm_record(level, item_id, asset_key)

        now = datetime.now().isoformat(timespec="seconds")
        self._connection.execute(
            """
            INSERT INTO record_overrides
                (level, item_id, asset_key, result_text, verdict, note, reason, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(level, item_id, asset_key) DO UPDATE SET
                result_text=excluded.result_text,
                verdict=excluded.verdict,
                note=excluded.note,
                reason=excluded.reason,
                updated_at=excluded.updated_at
            """,
            (level, item_id, asset_key, result_text, verdict, note, reason, now),
        )
        self._connection.execute(
            """
            INSERT INTO record_reviews (level, item_id, asset_key, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(level, item_id, asset_key)
            DO UPDATE SET updated_at=excluded.updated_at
            """,
            (level, item_id, asset_key, now),
        )
        self._connection.execute(
            """
            INSERT INTO record_override_history
                (level, item_id, asset_key, changes, reason, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                level,
                item_id,
                asset_key,
                json.dumps({"before": current, "after": updated}, ensure_ascii=False),
                reason,
                now,
            ),
        )
        if asset_type:
            # Any changed source record invalidates a previous major-risk decision.
            self._connection.execute(
                "DELETE FROM corrections WHERE level=? AND item_id=? AND asset_type=? AND field='major'",
                (level, item_id, asset_type),
            )
        self._connection.commit()
        return now

    def clear_record_override(
        self, level: int, item_id: str, asset_key: str, asset_type: str = ""
    ) -> None:
        row = self._connection.execute(
            """
            SELECT result_text, verdict, note FROM record_overrides
            WHERE level=? AND item_id=? AND asset_key=?
            """,
            (level, item_id, asset_key),
        ).fetchone()
        if not row:
            return
        now = datetime.now().isoformat(timespec="seconds")
        self._connection.execute(
            """
            INSERT INTO record_override_history
                (level, item_id, asset_key, changes, reason, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                level,
                item_id,
                asset_key,
                json.dumps(
                    {
                        "before": {
                            "result_text": row[0],
                            "verdict": row[1],
                            "note": row[2],
                        },
                        "after": None,
                    },
                    ensure_ascii=False,
                ),
                "恢复规则建议",
                now,
            ),
        )
        self._connection.execute(
            "DELETE FROM record_overrides WHERE level=? AND item_id=? AND asset_key=?",
            (level, item_id, asset_key),
        )
        self._connection.execute(
            "DELETE FROM record_reviews WHERE level=? AND item_id=? AND asset_key=?",
            (level, item_id, asset_key),
        )
        if asset_type:
            self._connection.execute(
                "DELETE FROM corrections WHERE level=? AND item_id=? AND asset_type=? AND field='major'",
                (level, item_id, asset_type),
            )
        self._connection.commit()


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


def apply_record_overrides(run_result: RunResult, store: CorrectionStore, level: int) -> None:
    for run in run_result.asset_runs:
        overrides = store.record_overrides(level, run.asset.device_name)
        reviews = store.reviewed_records(level, run.asset.device_name)
        for result in run.items:
            result.auto_verdict = result.verdict
            result.auto_result_text = result.result_text
            result.auto_note = result.note
            if result.item_id in reviews:
                result.reviewed = True
                result.reviewed_at = reviews[result.item_id]
            override = overrides.get(result.item_id)
            if not override:
                continue
            from core.contracts.verdict import Verdict

            result.result_text = override["result_text"]
            result.verdict = Verdict(override["verdict"])
            result.note = override["note"]
            result.manual_override = True
            result.override_reason = override["reason"]
            result.reviewed = True
