"""金标准用例发现与逐格比对。"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from core.golden import GoldenCase, compare_workbooks, discover_cases


def _make_book(path: Path, values: list[list[object]]) -> Path:
    book = Workbook()
    sheet = book.active
    sheet.title = "结果"
    for row in values:
        sheet.append(row)
    book.save(path)
    return path


def test_discover_cases(tmp_path: Path) -> None:
    case_dir = tmp_path / "case-l3"
    case_dir.mkdir()
    (case_dir / "project.yaml").write_text("level: 3\n", encoding="utf-8")
    (tmp_path / "not-a-case").mkdir()
    cases = discover_cases(tmp_path)
    assert [case.name for case in cases] == ["case-l3"]
    assert cases[0].assets is None
    assert discover_cases(tmp_path / "missing") == []


def test_compare_workbooks_identical(tmp_path: Path) -> None:
    values = [["序号", "控制点"], [1, "身份鉴别"]]
    actual = _make_book(tmp_path / "a.xlsx", values)
    expected = _make_book(tmp_path / "e.xlsx", values)
    assert compare_workbooks(actual, expected) == []


def test_compare_workbooks_reports_cell(tmp_path: Path) -> None:
    actual = _make_book(tmp_path / "a.xlsx", [["序号", "控制点"], [1, "身份鉴别"]])
    expected = _make_book(tmp_path / "e.xlsx", [["序号", "控制点"], [1, "访问控制"]])
    diffs = compare_workbooks(actual, expected)
    assert len(diffs) == 1
    assert "结果!B2" in diffs[0]
    assert "访问控制" in diffs[0] and "身份鉴别" in diffs[0]


def test_compare_workbooks_reports_size(tmp_path: Path) -> None:
    actual = _make_book(tmp_path / "a.xlsx", [["序号"], [1]])
    expected = _make_book(tmp_path / "e.xlsx", [["序号"], [1], [2]])
    diffs = compare_workbooks(actual, expected)
    assert any("尺寸" in diff for diff in diffs)
    assert any("结果!A3" in diff for diff in diffs)


def test_case_requires_project(tmp_path: Path) -> None:
    case = GoldenCase(
        name="case",
        project=tmp_path / "project.yaml",
        assets=None,
        expected_dir=tmp_path / "expected",
    )
    assert not case.project.exists()
