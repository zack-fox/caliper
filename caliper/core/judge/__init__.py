"""判定合成与跑批。"""

from core.judge.runner import RunError, run_project
from core.judge.synth import build_result_text, judge_item

__all__ = ["RunError", "build_result_text", "judge_item", "run_project"]
