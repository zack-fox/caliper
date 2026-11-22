"""记录表模型与构建：公司 9 列口径，判定结果只读。"""

from core.records.model import (
    COLUMNS,
    RecordHeader,
    RecordRow,
    RecordSheet,
    build_sheet,
)
from core.records.profile import (
    ALLOWED_COMPLIANCE_TEXT,
    RecordError,
    RecordProfile,
    load_profile,
)
from core.records.writer import write_record_book

__all__ = [
    "ALLOWED_COMPLIANCE_TEXT",
    "COLUMNS",
    "RecordError",
    "RecordHeader",
    "RecordProfile",
    "RecordRow",
    "RecordSheet",
    "build_sheet",
    "load_profile",
    "write_record_book",
]
