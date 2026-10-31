import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { RefreshCw, Trash2, Eye, FileText, FileX } from 'lucide-react'
import { api } from '../api/client'
import { isAuthed } from '../hooks/useAuth'
import { requireLogin } from '../lib/loginGate'
import LoadingSpinner from '../components/LoadingSpinner'
import StatusBadge from '../components/StatusBadge'
import { MOTION } from '../lib/motion'
import type { ReviewHistoryItem } from '../types'

const RISK_MAP: Record<string, { label: string; variant: 'error' | 'warning' | 'info' | 'success' }> = {
  high: { label: '高风险', variant: 'error' },
  medium: { label: '中风险', variant: 'warning' },
  low: { label: '低风险', variant: 'info' },
  none: { label: '无风险', variant: 'success' },
}
const COMPLIANCE_MAP: Record<string, { label: string; variant: 'error' | 'warning' | 'success' }> = {
  compliant: { label: '合规', variant: 'success' },
  non_compliant: { label: '不合规', variant: 'error' },
  needs_review: { label: '待审查', variant: 'warning' },
}
const STATUS_MAP: Record<string, { label: string; variant: 'success' | 'warning' | 'error' | 'info' }> = {
  pending: { label: '排队中', variant: 'info' },
  in_progress: { label: '审查中', variant: 'warning' },
  awaiting_human: { label: '待审核', variant: 'warning' },
  approved: { label: '已批准', variant: 'success' },
  rejected: { label: '已驳回', variant: 'error' },
  completed: { label: '已完成', variant: 'success' },
  failed: { label: '失败', variant: 'error' },
}

const PAGE_SIZE = 10

function formatTime(iso: string): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    const pad = (n: number) => n.toString().padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch {
    return iso
  }
}

export default function History() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [items, setItems] = useState<ReviewHistoryItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [deletingId, setDeletingId] = useState<string | null>(null)
  // 动效判卷：freshIds=本次刷新新进场的卷（push）；recededIds=已被重跑顶替的旧卷（recede）
  const seenIdsRef = useRef<Set<string>>(new Set())
  const firstLoadRef = useRef(true)
  const [freshIds, setFreshIds] = useState<Set<string>>(new Set())
  const [recededIds] = useState<Set<string>>(() => {
    try {
      return new Set<string>(JSON.parse(localStorage.getItem('receded_ids') || '[]'))
    } catch {
      return new Set<string>()
    }
  })

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    // 访客不查台账：静默空转，页面走引导态
    if (!isAuthed()) {
      setItems([])
      setTotal(0)
      setLoading(false)
      return
    }
    try {
      const res = await api.listReviews(page, PAGE_SIZE)
      setItems(res.items)
      setTotal(res.total)
      const ids = new Set(res.items.map(i => i.review_id))
      if (firstLoadRef.current) {
        // 首屏全部卷宗不推挤——进场安静，之后新增的才演 push
        firstLoadRef.current = false
      } else {
        setFreshIds(new Set(Array.from(ids).filter(id => !seenIdsRef.current.has(id))))
      }
      seenIdsRef.current = ids
    } catch (err: any) {
      setError(err.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => {
    load()
  }, [load])

  // 登录/登出后立即重扫卷宗；登录后首批不演推挤动画，安静落位
  useEffect(() => {
    const onAuth = () => {
      firstLoadRef.current = true
      load()
    }
    window.addEventListener('auth-changed', onAuth)
    return () => window.removeEventListener('auth-changed', onAuth)
  }, [load])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const handleDelete = async (id: string) => {
    if (!window.confirm('确定要删除此审查记录？该操作不可恢复。')) return
    setDeletingId(id)
    try {
      await api.deleteReview(id)
      // 如果当前页删完了且不是第一页，回退一页
      if (items.length === 1 && page > 1) {
        setPage(page - 1)
      } else {
        load()
      }
    } catch (err: any) {
      alert(err.message)
    } finally {
      setDeletingId(null)
    }
  }

  const displayName = (item: ReviewHistoryItem) => {
    if (item.filename) return item.filename
    const typeName = item.contract_type || '文本审查'
    return `(文本审查) ${typeName}`
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <FileText className="w-6 h-6 text-accent-cyan" />
          <h2 className="text-2xl font-bold text-text">审查历史</h2>
          <span className="text-sm text-muted">共 {total} 条</span>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-surface-2 hover:bg-surface-3 text-text text-sm transition-[background-color,color] duration-300"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? MOTION.spin : ''}`} />
          刷新
        </button>
      </div>

      {loading && <LoadingSpinner text="加载历史记录..." />}

      {error && !loading && (
        <div className="bg-accent-red/16 border border-accent-red/50 rounded-xl p-4 text-accent-red text-sm">
          {error}
        </div>
      )}

      {!loading && !error && (
        <>
          {!isAuthed() ? (
            <div className={`bg-surface-2 border border-accent-cyan/45 rounded-xl p-16 text-center ${MOTION.develop}`}>
              <FileX className="w-12 h-12 text-accent-cyan/70 mx-auto mb-3" />
              <p className="font-display text-xl font-semibold text-text">卷宗需署名调阅</p>
              <p className="text-sm text-muted font-kai mt-2">登录之后，您经办过的卷宗会在这里逐条排开。</p>
              <button
                onClick={() => requireLogin()}
                className="inline-block mt-4 px-5 py-2 bg-accent-cyan text-white rounded-lg text-sm font-medium hover:opacity-90 transition-[color,background-color,opacity] duration-300"
              >
                登录调卷
              </button>
            </div>
          ) : items.length === 0 ? (
            <div className="bg-surface-2 border border-surface-3 rounded-xl p-16 text-center">
              <FileX className="w-12 h-12 text-muted mx-auto mb-3" />
              <p className="text-muted">暂无审查记录</p>
              <Link to="/review" className="inline-block mt-4 px-4 py-2 bg-accent-cyan text-white rounded-lg text-sm hover:opacity-90 transition-[color,background-color,opacity] duration-300">
                发起新审查
              </Link>
            </div>
          ) : (
            <div className="bg-surface-2 border border-surface-3 rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-surface-3 text-muted text-xs uppercase tracking-wider">
                  <tr>
                    <th className="text-left px-4 py-3 font-medium">文件名</th>
                    <th className="text-left px-4 py-3 font-medium">合同类型</th>
                    <th className="text-left px-4 py-3 font-medium">状态</th>
                    <th className="text-left px-4 py-3 font-medium">风险</th>
                    <th className="text-left px-4 py-3 font-medium">合规</th>
                    <th className="text-left px-4 py-3 font-medium">创建时间</th>
                    <th className="text-right px-4 py-3 font-medium">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-3">
                  {items.map(item => {
                    const status = STATUS_MAP[item.status] || STATUS_MAP.completed
                    const risk = RISK_MAP[item.overall_risk_level] || RISK_MAP.none
                    const compliance = COMPLIANCE_MAP[item.overall_compliance] || COMPLIANCE_MAP.needs_review
                    // 三态行语义：新卷挤入 > 驳回下沉 > 被重跑顶替的旧卷退后
                    const rowMotion = freshIds.has(item.review_id)
                      ? MOTION.push
                      : item.status === 'rejected'
                        ? MOTION.fall
                        : recededIds.has(item.review_id)
                          ? MOTION.recede
                          : ''
                    return (
                      <tr
                        key={item.review_id}
                        className={`sweep-band hover:bg-surface-1 transition-colors duration-300 ${MOTION.sweep} ${rowMotion}`}
                      >
                        <td className="px-4 py-3">
                          <button
                            onClick={() => navigate(`/review/${item.review_id}`)}
                            className="text-left text-text hover:text-accent-cyan font-medium max-w-xs truncate"
                            title={displayName(item)}
                          >
                            {displayName(item)}
                          </button>
                        </td>
                        <td className="px-4 py-3 text-muted">{item.contract_type || '-'}</td>
                        <td className="px-4 py-3"><StatusBadge label={status.label} variant={status.variant} /></td>
                        <td className="px-4 py-3"><StatusBadge label={risk.label} variant={risk.variant} /></td>
                        <td className="px-4 py-3"><StatusBadge label={compliance.label} variant={compliance.variant} /></td>
                        <td className="px-4 py-3 text-muted whitespace-nowrap">{formatTime(item.created_at)}</td>
                        <td className="px-4 py-3">
                          <div className="flex items-center justify-end gap-1">
                            <button
                              onClick={() => navigate(`/review/${item.review_id}`)}
                              title="查看详情"
                              className="p-2 rounded-lg hover:bg-surface-3 text-muted hover:text-accent-cyan transition"
                            >
                              <Eye className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => handleDelete(item.review_id)}
                              disabled={deletingId === item.review_id}
                              title="删除"
                              className="p-2 rounded-lg hover:bg-accent-red/10 text-muted hover:text-accent-red transition disabled:opacity-50"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          {total > 0 && (
            <div className="flex items-center justify-between text-sm text-muted">
              <div>
                第 {page} / {totalPages} 页
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="px-3 py-1.5 rounded-lg bg-surface-2 hover:bg-surface-3 text-text disabled:opacity-40 disabled:cursor-not-allowed transition"
                >
                  上一页
                </button>
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="px-3 py-1.5 rounded-lg bg-surface-2 hover:bg-surface-3 text-text disabled:opacity-40 disabled:cursor-not-allowed transition"
                >
                  下一页
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
