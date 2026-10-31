import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { BadCaseItem } from '../types';
import { BadCaseBadge } from '../components/BadCaseBadge';
import { useNavigate } from 'react-router-dom';

const SEVERITY_OPTIONS = [
  { value: 'low', label: '低' },
  { value: 'medium', label: '中' },
  { value: 'high', label: '高' },
  { value: 'critical', label: '严重' },
];

export const BadCaseList: React.FC = () => {
  const [items, setItems] = useState<BadCaseItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [severity, setSeverity] = useState('medium');
  const navigate = useNavigate();

  useEffect(() => { load(); }, [severity]);

  const load = async () => {
    setLoading(true);
    try {
      const resp = await api.listBadCases(severity, 50);
      setItems(resp.items);
      setTotal(resp.total);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Bad Case 管理</h1>
        <div className="flex gap-2">
          {SEVERITY_OPTIONS.map(opt => (
            <button
              key={opt.value}
              onClick={() => setSeverity(opt.value)}
              className={`px-3 py-1 rounded text-sm ${
                severity === opt.value ? 'bg-accent-cyan text-white' : 'bg-surface-2 text-muted'
              }`}
            >
              {opt.label} ({opt.value})
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <p className="text-muted">加载中...</p>
      ) : items.length === 0 ? (
        <p className="text-muted">没有符合该严重度的 Bad Case 🎉</p>
      ) : (
        <div className="space-y-3">
          {items.map(item => (
            <div
              key={item.case_id}
              className="bg-surface-1 border border-surface-3 rounded-xl p-4 hover:border-accent-cyan cursor-pointer transition"
              onClick={() => navigate(`/bad-cases/${item.case_id}`)}
            >
              <div className="flex justify-between items-start mb-2">
                <div className="flex gap-2">
                  <BadCaseBadge severity={item.severity} signalType={item.signal_type} />
                  {item.judge_score !== null && item.judge_score !== undefined && (
                    <span className="text-xs text-muted">
                      judge: {item.judge_score.toFixed(1)}
                    </span>
                  )}
                </div>
                <span className="text-xs text-muted">{item.timestamp}</span>
              </div>
              <p className="text-sm font-medium mb-1">review: {item.review_id}</p>
              {item.judge_rationale && (
                <p className="text-sm text-muted line-clamp-2">{item.judge_rationale}</p>
              )}
              {item.state_warnings.length > 0 && (
                <p className="text-xs text-yellow-500 mt-2">⚠️ {item.state_warnings.length} warnings</p>
              )}
            </div>
          ))}
        </div>
      )}
      <p className="text-xs text-muted mt-4">共 {total} 条</p>
    </div>
  );
};

export default BadCaseList;