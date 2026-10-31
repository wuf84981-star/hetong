-- 004: risk_findings.source 字段（标注发现来源：rule / llm / conflict）
-- 老数据默认 'llm'，与迁移前行为一致；新审查由风险识别 Agent 写入真实来源。
ALTER TABLE risk_findings ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'llm';
