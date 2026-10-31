import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { DiagnosticReport } from '../types';
import { BadCaseBadge } from '../components/BadCaseBadge';

export const BadCaseDetail: React.FC = () => {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const [report, setReport] = useState<DiagnosticReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [committing, setCommitting] = useState(false);

  useEffect(() => {
    if (!caseId) return;
    load();
  }, [caseId]);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.diagnoseBadCase(caseId!);
      setReport(r);
    } finally {
      setLoading(false);
    }
  };

  const handleResolve = async () => {
    const commit = prompt('修复 commit hash:');
    const notes = prompt('修复说明:');
    if (!commit || !notes) return;
    setCommitting(true);
    try {
      await api.resolveBadCase(caseId!, commit, notes);
      await load();
    } finally {
      setCommitting(false);
    }
  };

  if (loading) return <div className="p-6">加载中...</div>;
  if (!report) return <div className="p-6 text-accent-red">报告不存在</div>;

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <button
        onClick={() => navigate('/bad-cases')}
        className="text-sm text-muted hover:text-accent-cyan mb-4"
      >
        ← 返回列表
      </button>

      <h1 className="text-2xl font-bold mb-4">
        诊断报告: <span className="font-mono text-lg">{report.review_id}</span>
      </h1>

      <section className="bg-surface-1 border border-surface-3 rounded-xl p-4 mb-4">
        <h2 className="font-semibold mb-2">🔍 假设</h2>
        <p className="text-sm leading-relaxed">{report.hypothesis || '无'}</p>
      </section>

      {report.recommended_actions && report.recommended_actions.length > 0 && (
        <section className="bg-accent-cyan/10 border border-accent-cyan/20 rounded-xl p-4 mb-4">
          <h2 className="font-semibold mb-2">💡 推荐操作</h2>
          <ol className="list-decimal pl-5 space-y-1">
            {report.recommended_actions.map((action, i) => (
              <li key={i} className="text-sm">{action}</li>
            ))}
          </ol>
          <button
            onClick={handleResolve}
            disabled={committing}
            className="mt-3 px-4 py-2 bg-accent-green text-white rounded text-sm disabled:opacity-50"
          >
            {committing ? '处理中...' : '✓ 标记已解决'}
          </button>
        </section>
      )}

      {report.rules_result && (
        <section className="bg-surface-1 border border-surface-3 rounded-xl p-4 mb-4">
          <h2 className="font-semibold mb-2">📋 规则引擎结果(确定性)</h2>
          <pre className="text-xs bg-surface-2 p-2 rounded overflow-x-auto">
            {JSON.stringify(report.rules_result, null, 2)}
          </pre>
        </section>
      )}

      {report.similar_feedback && report.similar_feedback.length > 0 && (
        <section className="bg-surface-1 border border-surface-3 rounded-xl p-4 mb-4">
          <h2 className="font-semibold mb-2">💭 相似历史反馈({report.similar_feedback.length})</h2>
          <div className="space-y-2">
            {report.similar_feedback.map((fb: any, i) => (
              <div key={i} className="text-sm bg-surface-2 p-2 rounded">
                <span className="font-mono text-xs">{fb.review_id}</span>
                {' · '}
                <span className="font-medium">{fb.decision}</span>
                {fb.comments && <p className="text-muted mt-1 text-xs">{fb.comments}</p>}
              </div>
            ))}
          </div>
        </section>
      )}

      {report.deep_analyses && report.deep_analyses.length > 0 && (
        <section className="bg-surface-1 border border-surface-3 rounded-xl p-4 mb-4">
          <h2 className="font-semibold mb-2">🔬 Loop 节点深度分析(v2, {report.deep_analyses.length})</h2>
          <div className="space-y-2">
            {report.deep_analyses.map((a: any, i) => (
              <div key={i} className="text-sm bg-surface-2 p-3 rounded">
                <div className="flex gap-2 mb-1">
                  <span className="text-xs">匹配度: {a.similarity_score}</span>
                  <span className="text-xs">模式: {a.pattern_match}</span>
                </div>
                <p className="text-xs text-muted mb-1">风险: {a.specific_risk}</p>
                {a.actionable_advice && a.actionable_advice.length > 0 && (
                  <ul className="list-disc pl-4 text-xs">
                    {a.actionable_advice.map((adv: string, j: number) => (
                      <li key={j}>{adv}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {(report.state_warnings.length > 0 || report.state_degraded_steps.length > 0) && (
        <section className="bg-yellow-500/10 border border-yellow-500/20 rounded-xl p-4 mb-4">
          <h2 className="font-semibold mb-2">⚠️ 上下文</h2>
          {report.state_warnings.length > 0 && (
            <div className="mb-2">
              <p className="text-xs font-medium">Warnings:</p>
              <ul className="list-disc pl-5 text-sm">
                {report.state_warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          )}
          {report.state_degraded_steps.length > 0 && (
            <div>
              <p className="text-xs font-medium">Degraded steps:</p>
              <p className="text-sm font-mono">{report.state_degraded_steps.join(', ')}</p>
            </div>
          )}
        </section>
      )}
    </div>
  );
};

export default BadCaseDetail;
