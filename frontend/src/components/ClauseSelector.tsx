import React from 'react';

interface ClauseOption {
  id: string;
  title: string;
  content?: string;
}

interface ClauseSelectorProps {
  clauses: ClauseOption[];
  selected: string[];
  onChange: (selected: string[]) => void;
  label?: string;
  maxHeight?: string;
}

export const ClauseSelector: React.FC<ClauseSelectorProps> = ({
  clauses, selected, onChange, label = '选择条款', maxHeight = 'max-h-40',
}) => {
  const toggle = (id: string) => {
    onChange(selected.includes(id)
      ? selected.filter(x => x !== id)
      : [...selected, id]);
  };

  return (
    <div>
      <label className="block text-sm text-muted mb-2">{label}</label>
      <div className={`overflow-y-auto border border-surface-3 rounded p-2 ${maxHeight}`}>
        {clauses.length === 0 && (
          <p className="text-xs text-muted p-2">无条款可选择</p>
        )}
        {clauses.map((c, i) => (
          <label key={c.id} className="flex items-start gap-2 py-1 hover:bg-surface-2 px-2 rounded cursor-pointer">
            <input
              type="checkbox"
              checked={selected.includes(c.id)}
              onChange={() => toggle(c.id)}
              className="mt-1"
            />
            <div className="flex-1">
              {/* 对用户露条款序号与名称即可，内部 ID 收进悬停提示 */}
              <span className="text-sm font-medium" title={c.id}>第{i + 1}条 {c.title}</span>
              {c.content && (
                <p className="text-xs text-muted line-clamp-2 mt-1">{c.content}</p>
              )}
            </div>
          </label>
        ))}
      </div>
      {selected.length > 0 && (
        <p className="text-xs text-muted mt-1">已选择 {selected.length} 条</p>
      )}
    </div>
  );
};

export default ClauseSelector;