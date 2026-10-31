"""验证 bad case 修复后是否回归通过。"""
import asyncio
import sys
from pathlib import Path

# 让脚本可以直接从仓库任意目录执行
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


async def verify():
    """跑 rules 模式 + 检查未解决的 bad case 数量。"""
    from eval.run_eval import load_dataset, detect_rules
    from eval.metrics import prf_from_sets

    data = load_dataset()
    cases = data["cases"]
    gold = [set(c["gold_risk_types"]) for c in cases]
    preds = [detect_rules(c["text"]) for c in cases]
    prf = prf_from_sets(preds, gold)

    print(f"=== Rules 模式评测 ===")
    print(f"Precision: {prf.precision:.4f}")
    print(f"Recall:    {prf.recall:.4f}")
    print(f"F1:        {prf.f1:.4f}")
    print(f"TP={prf.tp} FP={prf.fp} FN={prf.fn}")

    from src.services.bad_case_repo import BadCaseRepository
    repo = BadCaseRepository(storage_path=str(_ROOT / "data" / "bad_cases"))
    unresolved = await repo.list_unresolved(min_severity="high")

    print(f"\n=== 未解决 high+critical bad cases: {len(unresolved)} ===")
    for bc in unresolved[:5]:
        print(f"- {bc.case_id} [{bc.severity}] {bc.signal_type} - {bc.review_id}")

    if prf.f1 < 0.95:
        print(f"\n❌ F1 降至 {prf.f1:.4f},需要回滚修复")
        return 1

    print(f"\n✅ F1 稳定在 {prf.f1:.4f},bad cases 趋势 OK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(verify()))