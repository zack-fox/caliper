"""规则、测评实施点与标准单元的引用关系。"""

from pathlib import Path

from core.items.loader import load_pack
from core.traceability import standard_references


def test_linux_rules_have_stable_unique_references() -> None:
    pack = load_pack(Path("packs/linux_os"))
    references = [rule.rule_id for rule in pack.rules.rules]
    assert all(references)
    assert len(references) == len(set(references))
    assert all(reference.startswith("L") for reference in references)


def test_computing_environment_item_has_standard_references() -> None:
    pack = load_pack(Path("packs/linux_os"))
    item = pack.items_for_level(3)[0]
    assert item.item_id == "L3-CES1-01"
    assert standard_references(item) == [
        "GB/T 22239—2019 §8.1.4.1 a)",
        "GB/T 28448—2019 L3-CES1-01 c)测评实施 / d)单元判定",
    ]
