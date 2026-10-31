"""RAGRetriever 单元测试 — 结构化检索、软删除过滤与上下文格式化。"""

from unittest.mock import MagicMock

import pytest

from src.vector.rag import RAGRetriever


@pytest.fixture
def mock_store():
    """创建 mock MilvusStore。"""
    store = MagicMock()
    store.search.return_value = [
        {
            "text": "甲方应在收到发票后30日内支付货款",
            "metadata": {"doc_id": "d1", "doc_title": "民法典·合同编", "title": "付款条款", "category": "civil", "deleted": False},
            "score": 0.92,
        },
        {
            "text": "逾期付款的，应按日万分之五支付违约金",
            "metadata": {"doc_id": "d1", "doc_title": "民法典·合同编", "title": "违约金条款", "category": "civil", "deleted": False},
            "score": 0.85,
        },
    ]
    return store


@pytest.fixture
def retriever(mock_store):
    return RAGRetriever(store=mock_store)


class TestRAGRetriever:
    def test_retrieve_for_risk(self, retriever, mock_store):
        result = retriever.retrieve_for_risk("甲方承担无限责任")
        assert "参考条文" in result
        # 过采：top_k=3 × oversample=3 = 9
        mock_store.search.assert_called_once_with("甲方承担无限责任", top_k=9)

    def test_retrieve_for_compliance(self, retriever, mock_store):
        result = retriever.retrieve_for_compliance("试用期为8个月")
        assert "参考条文" in result
        mock_store.search.assert_called_once_with("试用期为8个月", top_k=9)

    def test_retrieve_for_suggestion(self, retriever, mock_store):
        result = retriever.retrieve_for_suggestion("违约金为合同总额的50%")
        assert "参考条文" in result
        mock_store.search.assert_called_once_with("违约金为合同总额的50%", top_k=9)

    def test_empty_results(self, retriever, mock_store):
        mock_store.search.return_value = []
        result = retriever.retrieve_for_risk("任何条款")
        assert result == ""

    def test_retrieve_structured_filters_deleted(self, retriever, mock_store):
        """软删除块退出检索：deleted=True 的命中被过滤后从过采池补足。"""
        mock_store.search.return_value = [
            {"text": "已删条文", "metadata": {"title": "已删", "deleted": True}, "score": 0.99},
            {"text": "有效条文", "metadata": {"title": "有效", "deleted": False}, "score": 0.80},
        ]
        hits = retriever.retrieve_structured("任何条款", top_k=3)
        assert [h["metadata"]["title"] for h in hits] == ["有效"]

    def test_retrieve_structured_truncates_to_top_k(self, retriever, mock_store):
        mock_store.search.return_value = [
            {"text": f"条文{i}", "metadata": {"title": f"T{i}"}, "score": 0.9 - i * 0.1}
            for i in range(9)
        ]
        hits = retriever.retrieve_structured("条款", top_k=3)
        assert len(hits) == 3

    def test_retrieve_structured_legacy_metadata_passes(self, retriever, mock_store):
        """旧样例索引数据无 deleted 键：视为活跃，正常返回。"""
        mock_store.search.return_value = [
            {"text": "旧数据", "metadata": {"title": "旧条文"}, "score": 0.7},
        ]
        hits = retriever.retrieve_structured("条款")
        assert len(hits) == 1

    def test_format_context_structure(self, retriever):
        results = [
            {
                "text": "条款内容",
                "metadata": {"doc_title": "民法典", "title": "标题", "category": "civil"},
                "score": 0.9,
            },
        ]
        formatted = retriever.format_context(results)
        assert "标题" in formatted
        assert "条款内容" in formatted
        assert "0.90" in formatted
        assert "出处：民法典" in formatted

    def test_format_context_doc_title_falls_back_to_source(self, retriever):
        """知识库文档名缺位时退回原始文件名（旧数据兼容）。"""
        results = [
            {"text": "条款内容", "metadata": {"source": "原合同.txt", "title": "标题"}, "score": 0.9},
        ]
        assert "出处：原合同.txt" in retriever.format_context(results)

    def test_format_context_missing_metadata(self, retriever):
        results = [
            {"text": "条款内容", "metadata": {}, "score": 0.9},
        ]
        formatted = retriever.format_context(results)
        assert "未知条款" in formatted
        assert "条款内容" in formatted
