import React, { useState, useEffect } from 'react';
import { HumanFeedback, DecisionType } from '../types';
import ClauseSelector from './ClauseSelector';
import StarRating from './StarRating';

interface FeedbackModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (feedback: HumanFeedback & {
    bad_clauses?: string[];
    missed_clauses?: string[];
    overall_rating?: number;
    industry?: string;
  }) => Promise<void>;
  clauses?: { id: string; title: string; content?: string }[];
  defaultReviewer?: string;
  title?: string;
  /** 页面上逐条点了「存疑」的条款，打开弹窗时预勾选 */
  defaultBadClauses?: string[];
  /** 有存疑条款时默认落在「部分同意(需修改)」 */
  defaultDecision?: DecisionType;
}

// 选中态底色用字面量类，动态拼接 bg-accent-${x} 不会被 Tailwind JIT 生成
const DECISIONS: { value: DecisionType; label: string; activeCls: string }[] = [
  { value: 'approve', label: '同意审查结果', activeCls: 'bg-accent-green text-white' },
  { value: 'reject', label: '驳回(结果错误)', activeCls: 'bg-accent-red text-white' },
  { value: 'modify', label: '部分同意(需修改)', activeCls: 'bg-accent-amber text-white' },
];

export const FeedbackModal: React.FC<FeedbackModalProps> = ({
  isOpen, onClose, onSubmit, clauses = [], defaultReviewer = '',
  title = '提交反馈', defaultBadClauses = [], defaultDecision,
}) => {
  const [form, setForm] = useState({
    reviewer: defaultReviewer,
    decision: (defaultDecision ?? 'approve') as DecisionType,
    comments: '',
    bad_clauses: [] as string[],
    missed_clauses: [] as string[],
    overall_rating: 0,
    industry: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  // 组件常驻挂载，每次重新打开都按最新默认值重置表单
  useEffect(() => {
    if (isOpen) {
      setForm({
        reviewer: defaultReviewer,
        decision: defaultDecision ?? 'approve',
        comments: '',
        bad_clauses: [...defaultBadClauses],
        missed_clauses: [],
        overall_rating: 0,
        industry: '',
      });
      setError('');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async () => {
    if (!form.reviewer.trim()) {
      setError('请填写审核人');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      await onSubmit({
        reviewer: form.reviewer,
        decision: form.decision,
        comments: form.comments,
        timestamp: new Date().toISOString(),
        bad_clauses: form.bad_clauses,
        missed_clauses: form.missed_clauses,
        overall_rating: form.overall_rating,
        industry: form.industry,
      });
      onClose();
    } catch (err: any) {
      setError(err.message || '提交失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-surface-1 rounded-xl p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <h2 className="font-display text-xl font-semibold mb-4">{title}</h2>

        <div className="mb-3">
          <label className="block text-sm text-muted mb-1">审核人</label>
          <input
            type="text"
            value={form.reviewer}
            onChange={e => setForm({ ...form, reviewer: e.target.value })}
            className="w-full px-3 py-2 bg-surface-2 rounded border border-surface-3 text-text"
            placeholder="请输入姓名"
          />
        </div>

        <div className="mb-3">
          <label className="block text-sm text-muted mb-1">决定</label>
          <div className="flex gap-2">
            {DECISIONS.map(d => (
              <button
                key={d.value}
                onClick={() => setForm({ ...form, decision: d.value })}
                className={`px-4 py-2 rounded-lg text-sm transition ${
                  form.decision === d.value
                    ? d.activeCls
                    : 'bg-surface-2 text-muted hover:text-text'
                }`}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>

        <div className="mb-3">
          <label className="block text-sm text-muted mb-1">行业(v2,用于检索)</label>
          <select
            value={form.industry}
            onChange={e => setForm({ ...form, industry: e.target.value })}
            className="w-full px-3 py-2 bg-surface-2 rounded border border-surface-3 text-text"
          >
            <option value="">选择行业(可选)</option>
            <option value="金融">金融</option>
            <option value="医疗">医疗</option>
            <option value="互联网">互联网</option>
            <option value="制造">制造</option>
            <option value="其他">其他</option>
          </select>
        </div>

        <div className="mb-3">
          <label className="block text-sm text-muted mb-1">
            详细意见 <span className="text-muted text-xs">(供系统学习)</span>
          </label>
          <textarea
            value={form.comments}
            onChange={e => setForm({ ...form, comments: e.target.value })}
            className="w-full px-3 py-2 bg-surface-2 rounded border border-surface-3 min-h-[100px] text-text"
            placeholder="具体说明哪些部分正确/错误,建议怎么改进..."
          />
        </div>

        <div className="mb-3">
          <label className="block text-sm text-muted mb-1">总体评分</label>
          <StarRating value={form.overall_rating} onChange={v => setForm({ ...form, overall_rating: v })} />
        </div>

        <div className="mb-3">
          <ClauseSelector
            label="哪些条款识别错了?(可多选)"
            clauses={clauses}
            selected={form.bad_clauses}
            onChange={ids => setForm({ ...form, bad_clauses: ids })}
          />
          {defaultBadClauses.length > 0 && (
            <p className="text-xs text-accent-amber mt-1">已勾上您在批注上标过「存疑」的 {defaultBadClauses.length} 条</p>
          )}
        </div>
        <div className="mb-3">
          <ClauseSelector
            label="哪些条款被漏检了?(可多选)"
            clauses={clauses}
            selected={form.missed_clauses}
            onChange={ids => setForm({ ...form, missed_clauses: ids })}
          />
        </div>

        {error && (
          <div className="mb-3 p-2 bg-accent-red/10 text-accent-red rounded text-sm">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2 mt-4">
          <button
            onClick={onClose}
            disabled={submitting}
            className="px-4 py-2 bg-surface-2 rounded text-text hover:bg-surface-3 transition"
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="px-4 py-2 bg-accent-cyan text-white rounded disabled:opacity-50 transition"
          >
            {submitting ? '提交中...' : '提交反馈'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default FeedbackModal;
