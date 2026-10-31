"""把 BadCase 转换为 eval/dataset.json 回归测试。"""
import asyncio
import json
import sys
from pathlib import Path

# 让脚本可以直接从仓库任意目录执行(参照 eval/run_eval.py 的做法)
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.services.bad_case_repo import BadCaseRepository


async def convert(case_id: str | None = None, output: str | None = None):
    """把 bad case 转成 eval 格式并追加到 dataset.json。"""
    if output is None:
        output = str(_ROOT / "eval" / "dataset.json")
    # 使用绝对路径,避免 cwd 切换时找不到 data 目录
    repo = BadCaseRepository(storage_path=str(_ROOT / "data" / "bad_cases"))
    all_cases = await repo.list_all(limit=1000)
    cases = all_cases if not case_id else [c for c in all_cases if c.case_id == case_id]
    cases = [c for c in cases if c is not None]

    output_path = Path(output)
    dataset = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else {"cases": []}

    for bc in cases:
        predicted = bc.predicted_output or {}
        risk_types = list({f.get("risk_type", "") for f in predicted.get("risk_findings", [])})

        new_case = {
            "id": f"badcase-{bc.case_id[:8]}",
            "text": bc.input_summary,
            "gold_risk_types": risk_types,
            "metadata": {
                "origin": "production_badcase",
                "severity": bc.severity,
                "judge_score": bc.judge_score,
                "original_case_id": bc.case_id,
            },
        }
        dataset["cases"].append(new_case)

    output_path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 添加 {len(cases)} 个 bad case 到 {output}")


if __name__ == "__main__":
    asyncio.run(convert(sys.argv[1] if len(sys.argv) > 1 else None))