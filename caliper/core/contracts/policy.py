"""六种 judge_policy 与合成规则。未声明 policy 一律报错，不许兜底。"""

from __future__ import annotations

from enum import Enum

from core.contracts.verdict import Verdict


class Policy(str, Enum):
    ALL_POSITIVE = "all_positive"
    ANY_POSITIVE = "any_positive"
    MIXED_PARTIAL = "mixed_partial"
    BINARY = "binary"
    NA = "na"
    MANUAL = "manual"


VERDICT_MAP: dict[Policy, dict[str, Verdict]] = {
    Policy.ALL_POSITIVE: {"all_true": Verdict.COMPLIANT, "not_all_true": Verdict.NON_COMPLIANT},
    Policy.ANY_POSITIVE: {"any_true": Verdict.COMPLIANT, "none_true": Verdict.NON_COMPLIANT},
    Policy.MIXED_PARTIAL: {
        "all_true": Verdict.COMPLIANT,
        "all_false": Verdict.NON_COMPLIANT,
        "mixed": Verdict.PARTIAL,
    },
    Policy.BINARY: {"all_true": Verdict.COMPLIANT, "any_false": Verdict.NON_COMPLIANT},
    Policy.NA: {"always": Verdict.NOT_APPLICABLE},
    Policy.MANUAL: {"always": Verdict.UNCOLLECTED},
}


def require_declared(policy_text: str) -> Policy:
    try:
        return Policy(policy_text)
    except ValueError as exc:
        raise ValueError(f"policy 未声明或非法：{policy_text!r}") from exc
