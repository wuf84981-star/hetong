"""Good Case 签名服务 — Tier 2 存储,分层抽样,不含 PII。v2 加 industry 维度。"""
from __future__ import annotations
import json
import random
from pathlib import Path
from datetime import datetime

from ..pipeline.state import ContractReviewState


class ReviewSignature:
    """结构化签名(不含原始合同文本)。"""

    def __init__(self, **kwargs):
        self.timestamp = kwargs.get("timestamp", datetime.now().isoformat())
        self.tenant_id = kwargs.get("tenant_id", "")
        self.review_id = kwargs.get("review_id", "")
        self.contract_type = kwargs.get("contract_type", "")
        self.industry = kwargs.get("industry", "")
        self.clauses_count = kwargs.get("clauses_count", 0)
        self.risk_findings_count = kwargs.get("risk_findings_count", 0)
        self.risk_types = sorted(kwargs.get("risk_types", []))
        self.compliance_status = kwargs.get("compliance_status", "")
        self.overall_risk_level = kwargs.get("overall_risk_level", "")
        self.schema_failures_count = kwargs.get("schema_failures_count", 0)
        self.warnings_count = kwargs.get("warnings_count", 0)
        self.degraded_steps_count = kwargs.get("degraded_steps_count", 0)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class SignatureService:
    """分层抽样的 Good Case 签名服务。v2 增加 industry 维度。"""

    _CONTRACT_TYPE_WEIGHTS = {
        "重大并购": 0.50,
        "涉外合同": 0.20,
        "知识产权": 0.05,
        "劳动合同": 0.03,
        "服务合同": 0.005,
        "买卖合同": 0.005,
    }

    _INDUSTRY_WEIGHTS = {
        "金融": 0.10,
        "医疗": 0.10,
        "互联网": 0.005,
        "制造": 0.005,
    }

    _DEFAULT_WEIGHT = 0.005

    def __init__(self, storage_path: str = "data/signatures"):
        self.path = Path(storage_path) / "signatures.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def should_sample(self, state: ContractReviewState) -> tuple[bool, str]:
        if state.overall_risk_level.value == "high":
            return True, "high_risk"
        if len(state.degraded_steps) > 0:
            return True, "degraded_steps"
        if len(state.warnings) > 0:
            return True, "has_warnings"
        if len(state.schema_failures) > 0:
            return True, "schema_failures"

        contract_weight = self._CONTRACT_TYPE_WEIGHTS.get(
            state.contract_type or "", self._DEFAULT_WEIGHT
        )
        industry_weight = self._INDUSTRY_WEIGHTS.get(
            getattr(state, "industry", "") or "", self._DEFAULT_WEIGHT
        )
        weight = max(contract_weight, industry_weight)

        if random.random() < weight:
            reason_dim = (
                state.contract_type if contract_weight > industry_weight
                else f"industry:{getattr(state, 'industry', '')}"
            )
            return True, f"strata:{reason_dim}"

        if len(state.clauses) > 50:
            if random.random() < 0.05:
                return True, "long_contract"

        return False, ""

    def maybe_record(self, state: ContractReviewState, force: bool = False) -> bool:
        if not force:
            should, reason = self.should_sample(state)
            if not should:
                return False

        sig = self._extract(state)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(sig.to_dict(), ensure_ascii=False) + "\n")
        return True

    def _extract(self, state: ContractReviewState) -> ReviewSignature:
        return ReviewSignature(
            tenant_id=getattr(state, "tenant_id", ""),
            review_id=state.review_id,
            contract_type=state.contract_type,
            industry=getattr(state, "industry", ""),
            clauses_count=len(state.clauses),
            risk_findings_count=len(state.risk_findings),
            risk_types=list({f.risk_type for f in state.risk_findings}),
            compliance_status=state.overall_compliance.value if state.overall_compliance else "",
            overall_risk_level=state.overall_risk_level.value,
            schema_failures_count=len(state.schema_failures),
            warnings_count=len(state.warnings),
            degraded_steps_count=len(state.degraded_steps),
        )


__all__ = ["SignatureService", "ReviewSignature"]