import React from 'react';

const SEVERITY_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  critical: { bg: 'bg-accent-red/20', text: 'text-accent-red', label: '严重' },
  high: { bg: 'bg-accent-amber/20', text: 'text-accent-amber', label: '高' },
  medium: { bg: 'bg-yellow-500/20', text: 'text-yellow-500', label: '中' },
  low: { bg: 'bg-surface-2', text: 'text-muted', label: '低' },
};

const SIGNAL_LABELS: Record<string, string> = {
  low_judge_score: '评分低',
  human_reject: '人工驳回',
  human_modify: '人工修改',
  schema_failure: 'Schema失败',
  multiple_degraded: '多步降级',
  high_risk_keyword_missed: '漏检高风险',
  user_reported: '用户上报',
  rule_mismatch: '规则不一致',
};

export const BadCaseBadge: React.FC<{
  severity: string;
  signalType: string;
}> = ({ severity, signalType }) => {
  const style = SEVERITY_STYLES[severity] || SEVERITY_STYLES.low;
  const signalLabel = SIGNAL_LABELS[signalType] || signalType;

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs ${style.bg} ${style.text}`}
          title={`信号: ${signalLabel}`}>
      <span className="font-semibold">{style.label}</span>
      <span>·</span>
      <span>{signalLabel}</span>
    </span>
  );
};

export default BadCaseBadge;