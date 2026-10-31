-- 005: reviews.position 字段（审查立场：buyer / seller / neutral）
-- 老数据默认 'neutral'，与迁移前无立场的行为一致。
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS position VARCHAR(10) DEFAULT 'neutral';
