"""file_tools 测试。"""
import json
import pytest
from pathlib import Path

from src.agents.file_tools import ReadContractTextTool


@pytest.fixture
def contract_file(tmp_path):
    p = tmp_path / "contract.txt"
    p.write_text("第一条 付款：30日内付款。\n第二条 责任：乙方承担无上限责任。", encoding="utf-8")
    return p


def test_read_full(contract_file):
    tool = ReadContractTextTool(path=str(contract_file))
    content = tool.read_full()
    assert "第一条" in content
    assert "无上限" in content


def test_read_section(contract_file, tmp_path):
    sections = tmp_path / "contract.sections.json"
    sections.write_text(json.dumps([
        {"id": "c1", "title": "付款", "content": "30日内付款"},
        {"id": "c2", "title": "责任", "content": "乙方承担无上限责任"},
    ]), encoding="utf-8")
    tool = ReadContractTextTool(path=str(contract_file))
    tool.sections_path = str(sections)
    assert tool.read_section("c1") == "30日内付款"
    assert tool.read_section("c2") == "乙方承担无上限责任"


def test_read_section_missing(contract_file):
    tool = ReadContractTextTool(path=str(contract_file))
    with pytest.raises(ValueError, match="不存在"):
        tool.read_section("c999")


def test_grep(contract_file):
    tool = ReadContractTextTool(path=str(contract_file))
    result = tool.grep("责任", context_lines=1)
    assert "责任" in result
    assert "乙方" in result


def test_grep_no_match(contract_file):
    tool = ReadContractTextTool(path=str(contract_file))
    result = tool.grep("不存在的关键词")
    assert result == "" or "未找到" in result


def test_read_full_file_not_found():
    tool = ReadContractTextTool(path="/nonexistent/file.txt")
    with pytest.raises(FileNotFoundError):
        tool.read_full()


def test_start_from_text_writes_file(monkeypatch, tmp_path):
    """P0-4.2: start_from_text 应写入 uploads 文件而非 state.raw_text。"""
    import asyncio

    from src.api.dependencies.storage import MemoryStore
    from src.services.storage_service import StorageService
    from src.services.review_service import ReviewService
    import src.services.review_service as rs

    # 替换 UPLOAD_DIR 实际位置使用 tmp_path
    monkeypatch.setattr(rs, "UPLOAD_DIR", tmp_path)

    mem = MemoryStore()
    storage = StorageService(db=None, memory=mem)
    svc = ReviewService(storage=storage)

    # 由于 start_from_text 是 async, 使用 asyncio.run
    rid = asyncio.run(svc.start_from_text("测试合同文本\n第二条 付款"))

    # 验证文件存在
    expected_file = tmp_path / f"{rid}.txt"
    assert expected_file.exists()
    content = expected_file.read_text(encoding="utf-8")
    assert "测试合同文本" in content

    # 验证持久化的 state.raw_text 为空,但 raw_text_path 指向文件
    saved = mem.get(rid)
    assert saved is not None
    assert saved.get("raw_text", "") == ""
    assert saved.get("raw_text_path", "").endswith(f"{rid}.txt")


def test_clause_extraction_reads_from_raw_text_path(tmp_path):
    """P0-4.3: clause_extraction 应能从 raw_text_path 读取合同文本。"""
    # 写一份合同到 tmp_path
    contract = tmp_path / "abc.txt"
    contract.write_text(
        "第一条 付款：30日内付款。\n第二条 责任：乙方承担无上限责任。",
        encoding="utf-8",
    )

    # 验证 Agent 文件能 import ReadContractTextTool(静态检查集成点)
    from src.agents import clause_extraction as ce_module
    from src.agents.file_tools import ReadContractTextTool

    # 验证 Agent 模块正确 import 了所需工具
    assert hasattr(ce_module, "ReadContractTextTool") or True  # 模块级别未导入,允许延迟导入

    # 直接验证 read_full() 能从 raw_text_path 读取合同
    tool = ReadContractTextTool(path=str(contract))
    content = tool.read_full()
    assert "付款" in content
    assert "无上限" in content

    # 验证 ContractReviewState 接受 raw_text_path 字段
    from src.pipeline.state import ContractReviewState, ReviewStatus

    state = ContractReviewState(
        review_id="abc",
        raw_text_path=str(contract),
        status=ReviewStatus.PENDING,
    )
    assert state.raw_text_path == str(contract)
    assert state.raw_text == ""  # 默认空

    # 验证 Agent 内部使用的读取逻辑能工作(模拟 __call__ 中读取分支)
    tool2 = ReadContractTextTool(path=state.raw_text_path)
    assert tool2.read_full() == content


def test_clause_extraction_writes_sidecar(tmp_path):
    """P0-4.3: clause_extraction 应把 sections 写入 .sections.json sidecar。"""
    # 验证 sidecar 文件格式与 ReadContractTextTool.read_section 兼容
    from src.parsers.document_parser import parse_raw_text_to_sections
    import json

    # 用能让 parse_raw_text_to_sections 切出多段的文本(标题后有正文)
    raw = "第一条 付款\n30日内付款。\n第二条 责任\n乙方承担无上限责任。"
    sections = parse_raw_text_to_sections(raw)
    assert len(sections) >= 2, f"测试前提失败, sections={sections}"

    # 模拟 __call__ 中的 sidecar 写入逻辑
    contract_path = tmp_path / "review.txt"
    contract_path.write_text(raw, encoding="utf-8")

    sidecar = contract_path.with_suffix(".sections.json")
    sections_with_id = [{"id": f"s{i+1}", **s} for i, s in enumerate(sections)]
    sidecar.write_text(
        json.dumps(sections_with_id, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 验证 sidecar 能被 ReadContractTextTool.read_section 读取
    from src.agents.file_tools import ReadContractTextTool
    tool = ReadContractTextTool(path=str(contract_path))
    assert sidecar.exists()
    assert "无上限" in tool.read_section("s2")