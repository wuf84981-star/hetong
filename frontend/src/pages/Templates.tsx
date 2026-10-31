import { useState } from 'react'
import { FileText } from 'lucide-react'
import { api } from '../api/client'
import { useApi } from '../hooks/useApi'
import { useAuth } from '../hooks/useAuth'
import { requireLogin } from '../lib/loginGate'
import { MOTION } from '../lib/motion'
import LoadingSpinner from '../components/LoadingSpinner'
import Card from '../components/Card'

const CATEGORY_MAP: Record<string, string> = {
  purchase: '采购合同',
  labor: '劳动合同',
  service: '服务合同',
  other: '其他',
}

export default function Templates() {
  const { isAuthenticated, role } = useAuth()
  // 模板接口限 admin/reviewer：客户端预判，登录态变化后 canView 翻转自动重拉
  const canView = isAuthenticated && (role === 'admin' || role === 'reviewer')
  const { data, loading, refetch, error } = useApi(() => (canView ? api.listTemplates() : Promise.resolve(null)), [canView])
  const [showCreate, setShowCreate] = useState(false)
  const [newTpl, setNewTpl] = useState({ name: '', category: 'other', required_clauses: '' })
  const [checkResult, setCheckResult] = useState<any>(null)
  const [checkInput, setCheckInput] = useState({ template_id: 'tpl-purchase', clause_texts: '' })

  const handleCreate = async () => {
    try {
      await api.createTemplate({
        name: newTpl.name,
        category: newTpl.category,
        required_clauses: newTpl.required_clauses.split('\n').filter(Boolean),
      })
      setShowCreate(false)
      setNewTpl({ name: '', category: 'other', required_clauses: '' })
      refetch()
    } catch (err: any) { alert(err.message) }
  }

  const handleDelete = async (id: string) => {
    if (!confirm(`确定删除模板 ${id}？`)) return
    await api.deleteTemplate(id)
    refetch()
  }

  const handleCheck = async () => {
    try {
      const result = await api.checkTemplate(checkInput.template_id, checkInput.clause_texts.split('\n').filter(Boolean))
      setCheckResult(result)
    } catch (err: any) { alert(err.message) }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-text">模板管理</h2>
          <p className="text-sm text-muted mt-1">管理合同模板，支持条款比对</p>
        </div>
        {canView && (
          <button onClick={() => setShowCreate(true)}
            className="px-4 py-1.5 bg-accent-cyan text-white rounded-lg text-sm hover:opacity-90 transition-[color,background-color,opacity] duration-300">新建模板</button>
        )}
      </div>

      {!isAuthenticated ? (
        /* 访客：页内引导卡，不弹层 */
        <div className={`bg-surface-2 border border-accent-cyan/45 rounded-xl p-12 text-center ${MOTION.develop}`}>
          <FileText className="w-10 h-10 text-accent-cyan/70 mx-auto mb-3" />
          <p className="font-display text-xl font-semibold text-text">模板库需署名调阅</p>
          <p className="text-sm text-muted font-kai mt-2">合同必要条款模板由管理员与审查员维护；登录后可在此建模板、做条款比对。</p>
          <button
            onClick={() => requireLogin()}
            className="mt-4 px-5 py-2 bg-accent-cyan text-white rounded-lg text-sm font-medium hover:opacity-90 transition-[color,background-color,opacity] duration-300"
          >
            登录调库
          </button>
        </div>
      ) : !canView ? (
        <div className="bg-surface-2 border border-accent-amber/50 rounded-xl p-12 text-center">
          <p className="font-display text-xl font-semibold text-text">当前角色为查看者</p>
          <p className="text-sm text-muted font-kai mt-2">模板库仅向管理员与审查员开放，如需调阅维护权限，请联系管理员调整角色。</p>
        </div>
      ) : (
        <>
      {error && !loading && (
        <div className="bg-accent-red/16 border border-accent-red/50 rounded-xl p-4 text-accent-red text-sm">{error}</div>
      )}
      {/* Template check */}
      <Card>
        <h3 className="font-semibold text-text mb-3">条款比对</h3>
        <div className="grid grid-cols-3 gap-4">
          <select value={checkInput.template_id} onChange={e => setCheckInput({ ...checkInput, template_id: e.target.value })}
            className="px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-sm text-text">
            {data?.templates?.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <textarea placeholder="输入条款文本（每行一条）" value={checkInput.clause_texts}
            onChange={e => setCheckInput({ ...checkInput, clause_texts: e.target.value })}
            className="px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-sm text-text placeholder:text-muted h-20" />
          <div className="flex flex-col gap-2">
            <button onClick={handleCheck} className="px-4 py-2 bg-accent-cyan text-white rounded-lg text-sm hover:opacity-90 transition">比对</button>
            {checkResult && (
              <div className="text-sm">
                <span className="font-medium text-text">匹配度：{(checkResult.score * 100).toFixed(0)}%</span>
                {checkResult.missing.length > 0 && (
                  <p className="text-accent-red text-xs mt-1">缺失：{checkResult.missing.join('、')}</p>
                )}
              </div>
            )}
          </div>
        </div>
      </Card>

      {showCreate && (
        <Card>
          <h3 className="font-semibold text-text mb-4">新建模板</h3>
          <div className="grid grid-cols-2 gap-4">
            <input placeholder="模板名称" value={newTpl.name} onChange={e => setNewTpl({ ...newTpl, name: e.target.value })}
              className="px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-sm text-text placeholder:text-muted" />
            <select value={newTpl.category} onChange={e => setNewTpl({ ...newTpl, category: e.target.value })}
              className="px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-sm text-text">
              <option value="purchase">采购合同</option><option value="labor">劳动合同</option>
              <option value="service">服务合同</option><option value="other">其他</option>
            </select>
            <textarea placeholder="必要条款（每行一条）" value={newTpl.required_clauses}
              onChange={e => setNewTpl({ ...newTpl, required_clauses: e.target.value })}
              className="px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-sm text-text placeholder:text-muted h-24 col-span-2" />
          </div>
          <div className="mt-4 flex gap-2">
            <button onClick={handleCreate} className="px-4 py-2 bg-accent-cyan text-white rounded-lg text-sm hover:opacity-90 transition">创建</button>
            <button onClick={() => setShowCreate(false)} className="px-4 py-2 bg-surface-3 text-muted rounded-lg text-sm hover:text-text transition">取消</button>
          </div>
        </Card>
      )}

      {loading ? <LoadingSpinner /> : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {data?.templates?.map(t => (
            <Card key={t.id}>
              <div className="flex justify-between items-start">
                <div>
                  <h3 className="font-semibold text-text">{t.name}</h3>
                  <p className="text-sm text-muted mt-1">{t.description || CATEGORY_MAP[t.category] || t.category}</p>
                </div>
                <button onClick={() => handleDelete(t.id)} className="text-accent-red hover:opacity-80 text-sm">删除</button>
              </div>
              <div className="mt-3">
                <p className="text-xs text-muted mb-1">必要条款 ({t.required_clauses?.length || 0})：</p>
                <div className="flex flex-wrap gap-1">
                  {t.required_clauses?.map((c: string, i: number) => (
                    <span key={i} className="text-xs bg-surface-3 text-muted px-2 py-0.5 rounded">{c}</span>
                  ))}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
        </>
      )}
    </div>
  )
}
