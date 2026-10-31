"""Bad case 双轨存储 — v2 升级: 摘要 + 全文分别存。"""
from __future__ import annotations
import asyncio
import json
from pathlib import Path
from typing import Union

from ..models.bad_case import BadCase
from ..models.structured_bad_case import StructuredBadCase


class BadCaseRepository:
    """Bad case JSONL 仓库,带双轨存储和解决追踪。"""

    def __init__(self, storage_path: str = "data/bad_cases",
                 max_input_length: int = 500):
        self.summary_path = Path(storage_path) / "summaries.jsonl"
        self.full_path = Path(storage_path) / "full.jsonl"
        for p in [self.summary_path, self.full_path]:
            p.parent.mkdir(parents=True, exist_ok=True)
        self.max_input_length = max_input_length
        self._lock = asyncio.Lock()

    async def save(self, bad_case: Union[BadCase, StructuredBadCase]) -> None:
        """存储: 完整 + 摘要两份文件。"""
        if len(bad_case.input_summary) > self.max_input_length:
            bad_case.input_summary = bad_case.input_summary[:self.max_input_length]

        data = bad_case.to_dict()

        async with self._lock:
            with self.summary_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")

            if isinstance(bad_case, StructuredBadCase):
                with self.full_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(data, ensure_ascii=False) + "\n")

    async def list_all(self, limit: int = 100) -> list[BadCase]:
        if not self.summary_path.exists():
            return []
        out = []
        for line in self.summary_path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                out.append(BadCase.from_dict(json.loads(line)))
            except Exception:
                continue
        return out

    async def load_full(self, case_id: str) -> dict | None:
        if not self.full_path.exists():
            return None
        for line in self.full_path.read_text(encoding="utf-8").splitlines():
            try:
                data = json.loads(line)
                if data.get("case_id") == case_id:
                    return data
            except Exception:
                continue
        return None

    async def list_unresolved(self, min_severity: str = "medium") -> list[BadCase]:
        severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        threshold = severity_order.get(min_severity, 2)
        all_cases = await self.list_all(limit=1000)
        return [
            bc for bc in all_cases
            if not bc.resolved and severity_order.get(bc.severity, 1) >= threshold
        ]

    async def mark_resolved(self, case_id: str, commit: str, notes: str) -> None:
        cases = await self.list_all(limit=10000)
        for bc in cases:
            if bc.case_id == case_id:
                bc.resolved = True
                bc.resolution = notes
                bc.resolution_commit = commit
        async with self._lock:
            with self.summary_path.open("w", encoding="utf-8") as f:
                for bc in cases:
                    f.write(json.dumps(bc.to_dict(), ensure_ascii=False) + "\n")


__all__ = ["BadCaseRepository"]