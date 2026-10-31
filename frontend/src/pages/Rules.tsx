import { useState } from 'react'
import { Scale } from 'lucide-react'
import { api } from '../api/client'
import { useApi } from '../hooks/useApi'
import { useAuth } from '../hooks/useAuth'
import { requireLogin } from '../lib/loginGate'
import LoadingSpinner from '../components/LoadingSpinner'
import StatusBadge from '../components/StatusBadge'
import { MOTION } from '../lib/motion'

const SEVERITY_MAP: Record<string, string> = {
  critical: '严重',
  warning: '警告',
  info: '提示',
}

const CATEGORY_MAP: Record<string, string> = {
  liability: '责任',
  termination: '终止',
  penalty: '违约金',
  validity: '有效性',
  ip: '知识产权',
  confidentiality: '保密',
  renewal: '续约',
  clarity: '清晰度',
  jurisdiction: '管辖权',
  general: '通用',
  other: '其他',
}

export default function Rules() {
  const { isAuthenticated, role } = useAuth()
  // 规则接口限 admin/reviewer：客户端预判角色，访客/查看者不发注定 401/403 的请求；登录态变化经 useAuth 事件同步后自动重拉
  const canView = isAuthenticated && (role === 'admin' || role === 'reviewer')
  const { data, loading, refetch, error } = useApi(() => (canView ? api.listRules() : Promise.resolve(null)), [canView])
  const { data: stats } = useApi(() => (canView ? api.getRuleStats() : Promise.resolve(null)), [canView])
  const [showCreate, setShowCreate] = useState(false)
  const [newRule, setNewRule] = useState({ id: '', name: '', severity: 'info', category: '', condition: { operator: 'or', conditions: [{ field: 'content', operator: 'contains', value: '' }] } })

  const handleCreate = async () => {
    try {
      await api.createRule(newRule)
      setShowCreate(false)
      setNewRule({ id: '', name: '', severity: 'info', category: '', condition: { operator: 'or', conditions: [{ field: 'content', operator: 'contains', value: '' }] } })
      refetch()
    } catch (err: any) { alert(err.message) }
  }

  const handleToggle = async (id: string, enabled: boolean) => {
    await api.toggleRule(id, enabled)
    refetch()
  }

  const handleDelete = async (id: string) => {
    if (!confirm(`确定删除规则 ${id}？`)) return
    await api.deleteRule(id)
    refetch()
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-text">规则管理</h2>
          <p className="text-sm text-muted mt-1">管理合同审查规则，支持 YAML 热加载</p>
        </div>
        {canView && (
          <div className="flex gap-2">
            <button onClick={() => requireLogin(() => { void api.reloadRules().then(() => refetch()) })}
              className="px-3 py-1.5 bg-surface-2 border border-surface-3 text-muted rounded-lg text-sm hover:text-text transition-[color,background-color,border-color] duration-300">刷新规则</button>
            <button onClick={() => setShowCreate(true)}
              className="px-4 py-1.5 bg-accent-cyan text-white rounded-lg text-sm hover:opacity-90 transition-[color,background-color,opacity] duration-300">新建规则</button>
          </div>
        )}
      </div>

      {!isAuthenticated ? (
        /* 访客：页内引导卡，不弹层 */
        <div className={`bg-surface-2 border border-accent-cyan/45 rounded-xl p-12 text-center ${MOTION.develop}`}>
          <Scale className="w-10 h-10 text-accent-cyan/70 mx-auto mb-3" />
          <p className="font-display text-xl font-semibold text-text">规则库需署名调阅</p>
          <p className="text-sm text-muted font-kai mt-2">风险规则由管理员与审查员维护；登录成功后即可在此启停规则、热加载规则库。</p>
          <button
            onClick={() => requireLogin()}
            className="mt-4 px-5 py-2 bg-accent-cyan text-white rounded-lg text-sm font-medium hover:opacity-90 transition-[color,background-color,opacity] duration-300"
          >
            登录调库
          </button>
        </div>
      ) : !canView ? (
        /* 已登录但角色是查看者：403 区分文案，不弹层 */
        <div className="bg-surface-2 border border-accent-amber/50 rounded-xl p-12 text-center">
          <p className="font-display text-xl font-semibold text-text">当前角色为查看者</p>
          <p className="text-sm text-muted font-kai mt-2">规则库仅向管理员与审查员开放，如需调阅维护权限，请联系管理员调整角色。</p>
        </div>
      ) : (
        <>
      {error && !loading && (
        <div className="bg-accent-red/16 border border-accent-red/50 rounded-xl p-4 text-accent-red text-sm">{error}</div>
      )}
      {stats && (
        <div className="grid grid-cols-4 gap-4">
          {[
            { value: stats.total, label: '总规则数', color: 'text-text' },
            { value: stats.enabled, label: '已启用', color: 'text-accent-green' },
            { value: stats.disabled, label: '已禁用', color: 'text-muted' },
            { value: stats.by_severity?.critical || 0, label: '严重级别', color: 'text-accent-red' },
          ].map(({ value, label, color }) => (
            <div key={label} className={`bg-surface-2 border border-surface-3 rounded-xl p-4 text-center hover:border-accent-cyan/50 ${MOTION.lift}`}>
              <div className={`text-2xl font-bold ${color}`}>{value}</div>
              <div className="text-xs text-muted mt-1">{label}</div>
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <div className="bg-surface-2 border border-surface-3 rounded-xl p-6">
          <h3 className="font-semibold text-text mb-4">新建规则</h3>
          <div className="grid grid-cols-2 gap-4">
            <input placeholder="规则ID (如 R009)" value={newRule.id} onChange={e => setNewRule({ ...newRule, id: e.target.value })}
              className="px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-sm text-text placeholder:text-muted" />
            <input placeholder="规则名称" value={newRule.name} onChange={e => setNewRule({ ...newRule, name: e.target.value })}
              className="px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-sm text-text placeholder:text-muted" />
            <select value={newRule.severity} onChange={e => setNewRule({ ...newRule, severity: e.target.value })}
              className="px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-sm text-text">
              <option value="info">提示</option><option value="warning">警告</option><option value="critical">严重</option>
            </select>
            <select value={newRule.category} onChange={e => setNewRule({ ...newRule, category: e.target.value })}
              className="px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-sm text-text">
              <option value="">请选择分类</option>
              {Object.entries(CATEGORY_MAP).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <input placeholder="匹配关键词" value={newRule.condition.conditions[0].value as string}
              onChange={e => setNewRule({ ...newRule, condition: { ...newRule.condition, conditions: [{ ...newRule.condition.conditions[0], value: e.target.value }] } })}
              className="px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-sm text-text placeholder:text-muted col-span-2" />
          </div>
          <div className="mt-4 flex gap-2">
            <button onClick={handleCreate} className="px-4 py-2 bg-accent-cyan text-white rounded-lg text-sm hover:opacity-90 transition-[color,background-color,opacity] duration-300">创建</button>
            <button onClick={() => setShowCreate(false)} className="px-4 py-2 bg-surface-3 text-muted rounded-lg text-sm hover:text-text transition-colors duration-300">取消</button>
          </div>
        </div>
      )}

      {loading ? <LoadingSpinner /> : (
        <div className="bg-surface-2 border border-surface-3 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-surface-1 border-b border-surface-3">
              <tr>
                <th className="px-4 py-3 text-left text-muted">ID</th>
                <th className="px-4 py-3 text-left text-muted">名称</th>
                <th className="px-4 py-3 text-left text-muted">严重程度</th>
                <th className="px-4 py-3 text-left text-muted">分类</th>
                <th className="px-4 py-3 text-center text-muted">状态</th>
                <th className="px-4 py-3 text-right text-muted">操作</th>
              </tr>
            </thead>
            <tbody>
              {data?.rules?.map(r => (
                <tr key={r.id} className={`sweep-band border-b border-surface-3 hover:bg-surface-1 transition-colors duration-300 ${MOTION.sweep}`}>
                  <td className="px-4 py-3 font-mono text-xs text-text">{r.id}</td>
                  <td className="px-4 py-3 text-text">{r.name}</td>
                  <td className="px-4 py-3">
                    <StatusBadge label={SEVERITY_MAP[r.severity] || r.severity} variant={r.severity === 'critical' ? 'error' : r.severity === 'warning' ? 'warning' : 'info'} />
                  </td>
                  <td className="px-4 py-3 text-muted">{CATEGORY_MAP[r.category] || r.category}</td>
                  <td className="px-4 py-3 text-center">
                    <button onClick={() => handleToggle(r.id, !r.enabled)}
                      className={`w-10 h-5 rounded-full transition-colors duration-300 ${r.enabled ? 'bg-accent-green' : 'bg-surface-4'}`}>
                      <div className={`w-4 h-4 bg-white rounded-full shadow transition-transform ${r.enabled ? 'translate-x-5' : 'translate-x-0.5'}`} />
                    </button>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => handleDelete(r.id)} className="text-accent-red hover:opacity-80 text-xs">删除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
        </>
      )}
    </div>
  )
}
