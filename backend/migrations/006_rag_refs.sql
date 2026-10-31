-- 006: 三张发现/建议子表加 rag_refs JSON 列（RAG 检索引用透出）
-- 老数据默认 '[]'，读侧对空数组渲染"无检索参考"，行为与迁移前一致；新审查由 Agent 写入命中的知识库条文引用。
ALTER TABLE risk_findings       ADD COLUMN IF NOT EXISTS rag_refs JSON DEFAULT '[]';
ALTER TABLE compliance_findings ADD COLUMN IF NOT EXISTS rag_refs JSON DEFAULT '[]';
ALTER TABLE suggestions         ADD COLUMN IF NOT EXISTS rag_refs JSON DEFAULT '[]';
