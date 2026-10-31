import { useState, useEffect, useCallback, useRef } from 'react'
import type { ReactNode } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Calendar, Check, ChevronDown, Clock, Copy, Crosshair, Download,
  FileText, MessageSquare, PenLine, RefreshCw, Scale, ScanText,
  ThumbsDown, ThumbsUp, Trash2, User,
} from 'lucide-react'
import { api } from '../api/client'
import { requireLogin } from '../lib/loginGate'
import LoadingSpinner from '../components/LoadingSpinner'
import PipelineGraph from '../components/PipelineGraph'
import { FeedbackModal } from '../components/FeedbackModal'
import { useBadCase } from '../hooks/useBadCase'
import { useAuth, isAuthed } from '../hooks/useAuth'
import { MOTION } from '../lib/motion'
import type {
  Clause, ComplianceFinding, DetailedReview, RagRef, RiskFinding, StepEvent, Suggestion,
} from '../types'

const TERMINAL_STATUSES = new Set(['completed', 'approved', 'rejected', 'awaiting_human'])

const RISK_LABEL: Record<string, string> = { high: '高风险', medium: '中风险', low: '低风险', none: '无风险' }
const COMPLIANCE_LABEL: Record<string, string> = {
  compliant: '合规', non_compliant: '不合规', needs_review: '待复核',
}
const DECISION_LABEL: Record<string, { label: string; cls: string }> = {
  approve: { label: '批准通过', cls: 'text-accent-green border-accent-green/40' },
  reject: { label: '驳回', cls: 'text-accent-red border-accent-red/40' },
  modify: { label: '修改后复审', cls: 'text-accent-amber border-accent-amber/40' },
}
const STATUS_LABEL: Record<string, string> = {
  pending: '排队中', processing: '核阅中', awaiting_human: '待把关',
  completed: '已核阅', approved: '已放行', rejected: '已驳回', failed: '中断',
}
// 降级步骤的节点名 → 幕僚名，不再对用户露出英文键
const STEP_OFFICER: Record<string, string> = {
  clause_extraction: '条款拆解官', risk_identification: '风险猎手',
  compliance_check: '合规法官', suggestion: '修订顾问',
}

type Tone = 'red' | 'amber' | 'cyan' | 'green'

const TONE_BAR: Record<Tone, string> = {
  red: 'border-accent-red', amber: 'border-accent-amber',
  cyan: 'border-accent-cyan', green: 'border-accent-green',
}
const TONE_TEXT: Record<Tone, string> = {
  red: 'text-accent-red', amber: 'text-accent-amber',
  cyan: 'text-accent-cyan', green: 'text-accent-green',
}
const TONE_DOT: Record<Tone, string> = {
  red: 'bg-accent-red', amber: 'bg-accent-amber',
  cyan: 'bg-accent-cyan', green: 'bg-accent-green',
}

/** 判断风险发现的出处：source 字段（004 迁移后）与 rationale 措辞（老数据）双兜底 */
function riskSource(r: RiskFinding): 'rule' | 'llm' | 'conflict' {
  const ra = r.rationale || ''
  if (r.source === 'conflict' || ra.includes('双引擎分歧')) return 'conflict'
  if (r.source === 'rule' || ra.includes('规则引擎检测')) return 'rule'
  return 'llm'
}
const SOURCE_META: Record<'rule' | 'llm' | 'conflict', { label: string; cls: string }> = {
  rule: { label: '规则引擎命中', cls: 'text-accent-cyan border-accent-cyan/30' },
  llm: { label: '大模型推理', cls: 'text-accent-purple border-accent-purple/30' },
  conflict: { label: '双引擎分歧 · 待您裁断', cls: 'text-accent-amber border-accent-amber/40' },
}

// 审查立场：卷首徽章与我方利害排序共用
const POSITION_META: Record<string, { label: string; cls: string }> = {
  buyer: { label: '立场 · 买方（甲方）', cls: 'text-accent-cyan border-accent-cyan/40' },
  seller: { label: '立场 · 卖方（乙方）', cls: 'text-accent-cyan border-accent-cyan/40' },
  neutral: { label: '立场 · 中立', cls: 'text-muted border-surface-3' },
}

function fmtTime(iso: string): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    const pad = (n: number) => n.toString().padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch {
    return iso
  }
}

/** 把幕僚建议改动的原文在条款正文上圈朱，理由挂进悬停提示 */
function renderClauseText(content: string, suggs: Suggestion[]): ReactNode[] {
  type Range = { start: number; end: number; reason: string }
  const ranges: Range[] = []
  for (const s of suggs) {
    const needle = (s.original_text || '').trim()
    if (!needle) continue
    const idx = content.indexOf(needle)
    if (idx >= 0 && !ranges.some(r => idx < r.end && idx + needle.length > r.start)) {
      ranges.push({ start: idx, end: idx + needle.length, reason: s.reason })
    }
  }
  ranges.sort((a, b) => a.start - b.start)
  const out: ReactNode[] = []
  let pos = 0
  ranges.forEach((r, i) => {
    if (r.start > pos) out.push(content.slice(pos, r.start))
    out.push(
      <mark key={i} className={`anno-mark rounded ${MOTION.flash}`} title={r.reason || '修订顾问建议改动'}>
        {content.slice(r.start, r.end)}
      </mark>,
    )
    pos = r.end
  })
  out.push(content.slice(pos))
  return out
}

/** 批注卡：朱笔=风险、石青=合规、青绿=建议，条状骑缝排在条款尾部 */
/** RAG 知识库检索命中引用：让批注「判断依据」可审计；旧卷宗无此字段则不渲染 */
function RagRefsBlock({ refs }: { refs?: RagRef[] }) {
  if (!refs?.length) return null
  return (
    <details className="mt-1">
      <summary className="text-xs text-muted cursor-pointer hover:text-text select-none w-fit">检索参考 · {refs.length} 条</summary>
      <ul className="mt-1 space-y-2">
        {refs.map((ref, i) => (
          <li key={i} className="text-xs border-l-2 border-accent-cyan/30 pl-2">
            <p className="font-kai">
              <span className="text-accent-cyan">{ref.clause_title || '条文'}</span>
              {ref.doc_title && <span className="text-muted">（{ref.doc_title}）</span>}
              <span className="text-muted"> · 相似度 {ref.score.toFixed(2)}</span>
            </p>
            <p className="text-muted/80 leading-relaxed line-clamp-2 mt-0.5">{ref.snippet}</p>
          </li>
        ))}
      </ul>
    </details>
  )
}

function AnnoCard({ tone, badge, icon: Icon, right, children, footer }: {
  tone: Tone; badge: string; icon: typeof Crosshair; right?: ReactNode; children: ReactNode; footer?: ReactNode
}) {
  return (
    <div className={`rounded-r-lg border-l-[3px] ${TONE_BAR[tone]} bg-surface-2 px-4 py-3 ${MOTION.develop}`}>
      <div className="flex items-center justify-between gap-2">
        <span className={`flex items-center gap-1.5 font-kai text-xs font-semibold ${TONE_TEXT[tone]}`}>
          <Icon className="w-3.5 h-3.5 flex-shrink-0" />
          {badge}
        </span>
        {right}
      </div>
      <div className="mt-1.5 space-y-1">{children}</div>
      {footer && <div className="mt-2 pt-2 border-t border-surface-3/60 flex justify-end gap-1.5">{footer}</div>}
    </div>
  )
}

function VerdictSeal({ label, tone }: { label: string; tone: Tone }) {
  return (
    <div
      role="img"
      aria-label={`审查定论：${label}`}
      className={`select-none shrink-0 rounded-lg border-[3px] ${TONE_BAR[tone]} ${TONE_TEXT[tone]} px-4 py-3 flex flex-col items-center gap-1 opacity-90 ${MOTION.stamp}`}
    >
      <span className="font-display text-lg font-bold tracking-[0.35em] pl-[0.35em] whitespace-nowrap">{label}</span>
      <span className="font-display text-[9px] tracking-[0.5em] pl-[0.5em] opacity-70">定论</span>
    </div>
  )
}

export default function ReviewDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { username, isAuthenticated } = useAuth()
  const [data, setData] = useState<DetailedReview | null>(null)
  const [loading, setLoading] = useState(true)
  const [rerunning, setRerunning] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [negotiating, setNegotiating] = useState(false)
  const [trackingId, setTrackingId] = useState<string | null>(null)
  const [stepLog, setStepLog] = useState<StepEvent[]>([])
  const [currentStep, setCurrentStep] = useState('')
  const [trackProgress, setTrackProgress] = useState(0)
  const [trackError, setTrackError] = useState('')
  const pollTimer = useRef<number | null>(null)
  const [showFeedbackModal, setShowFeedbackModal] = useState(false)
  const [copiedKey, setCopiedKey] = useState<string | null>(null)
  const [flashIdx, setFlashIdx] = useState<number | null>(null)
  const flashTimer = useRef<number | null>(null)
  const [upVoted, setUpVoted] = useState<Record<string, boolean>>({})
  const [badClauses, setBadClauses] = useState<string[]>([])
  const [selfCheckOpen, setSelfCheckOpen] = useState(false)
  const [judgeScore, setJudgeScore] = useState<number | null>(null)
  const { submitFeedback } = useBadCase()

  // 判分官抽检结论：未抽中的卷宗返回 404，静默留白；访客不发请求，署名后自动补拉
  useEffect(() => {
    if (!id || !isAuthed()) return
    setJudgeScore(null)
    api.getReviewDiagnostics(id).then(r => setJudgeScore(r.judge_score)).catch(() => {})
  }, [id, isAuthenticated])

  const stopPolling = useCallback(() => {
    if (pollTimer.current !== null) {
      window.clearTimeout(pollTimer.current)
      pollTimer.current = null
    }
  }, [])

  useEffect(() => () => {
    stopPolling()
    if (flashTimer.current !== null) window.clearTimeout(flashTimer.current)
  }, [stopPolling])

  const load = useCallback(() => {
    // 访客不发鉴权请求：页面走署名引导态，避免误导性「不存在」
    if (!id || !isAuthed()) {
      setLoading(false)
      return Promise.resolve()
    }
    setLoading(true)
    return api.getReview(id)
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [id])

  useEffect(() => { load() }, [load])

  // 署名/退出后立即重查本卷，不必刷新页面
  useEffect(() => {
    const on = () => { void load() }
    window.addEventListener('auth-changed', on)
    return () => window.removeEventListener('auth-changed', on)
  }, [load])

  const startPolling = useCallback((rid: string) => {
    setTrackingId(rid)
    setStepLog([])
    setCurrentStep('')
    setTrackProgress(0)
    setTrackError('')
    const tick = async () => {
      try {
        const d: DetailedReview = await api.getReview(rid)
        setStepLog(d.step_log || [])
        setCurrentStep(d.current_step || '')
        setTrackProgress(d.progress || 0)
        if (TERMINAL_STATUSES.has(d.status)) {
          stopPolling()
          if (rid === id) {
            setData(d)
            setTrackingId(null)
          } else {
            navigate(`/review/${rid}`)
          }
          return
        }
        if (d.errors?.length && !d.current_step) {
          const lastErr = d.step_log?.slice().reverse().find(e => e.status === 'error')
          if (lastErr) {
            setTrackError(lastErr.message || d.errors[0])
            stopPolling()
            return
          }
        }
      } catch (err: any) {
        setTrackError(err.message || '轮询失败')
        stopPolling()
        return
      }
      pollTimer.current = window.setTimeout(tick, 1000)
    }
    tick()
  }, [id, navigate, stopPolling])

  const handleFeedbackSubmit = async (feedback: any) => {
    const ok = await submitFeedback(id!, feedback)
    if (ok) {
      setShowFeedbackModal(false)
      await load()
    }
  }

  // 下载门：访客先弹登录，登录成功后自动续下（blob 带鉴权头）
  const downloadWith = (fn: (rid: string) => Promise<unknown>) => () => {
    if (!id) return
    const rid = id
    requireLogin(() => {
      void fn(rid).catch((err: any) => alert(err?.message || '下载失败'))
    })
  }

  const handleRerun = async () => {
    if (!id) return
    if (!window.confirm('将基于原始文本/文件重新执行审查，会生成一条新的审查记录。是否继续？')) return
    setRerunning(true)
    try {
      const res = await api.rerunReview(id)
      setRerunning(false)
      // 记下被顶替的旧卷：回看历史时它以「退后」淡化示人
      try {
        const rec = new Set<string>(JSON.parse(localStorage.getItem('receded_ids') || '[]'))
        rec.add(id)
        localStorage.setItem('receded_ids', JSON.stringify(Array.from(rec)))
      } catch { /* 存储不可用则不标记 */ }
      startPolling(res.review_id)
    } catch (err: any) {
      alert(err.message)
      setRerunning(false)
    }
  }

  const handleDelete = async () => {
    if (!id) return
    if (!window.confirm('确定要删除此审查记录？该操作不可恢复。')) return
    setDeleting(true)
    try {
      await api.deleteReview(id)
      navigate('/history')
    } catch (err: any) {
      alert(err.message)
    } finally {
      setDeleting(false)
    }
  }

  // 复用或新开一个协商会话，然后带去协商追踪页
  const handleNegotiate = async () => {
    if (!id) return
    setNegotiating(true)
    try {
      const list = await api.listNegotiations()
      const active = list.sessions.find(s => s.review_id === id && s.status === 'active')
      if (!active) await api.startNegotiation(id)
      navigate('/negotiation')
    } catch (err: any) {
      alert(err.message)
      setNegotiating(false)
    }
  }

  const copySuggestion = async (key: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedKey(key)
      window.setTimeout(() => setCopiedKey(null), 1500)
    } catch { /* 剪贴板不可用时静默 */ }
  }

  const toggleUp = (key: string) => setUpVoted(v => ({ ...v, [key]: !v[key] }))
  const toggleBad = (cid?: string) => {
    if (!cid) return
    setBadClauses(b => (b.includes(cid) ? b.filter(x => x !== cid) : [...b, cid]))
  }

  const goToClause = (i: number) => {
    document.getElementById(`clause-${i}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    setFlashIdx(i)
    if (flashTimer.current !== null) window.clearTimeout(flashTimer.current)
    flashTimer.current = window.setTimeout(() => setFlashIdx(null), 1800)
  }

  // 访客早返回（置于全部 hooks 之后）：页内引导，不弹层
  if (!isAuthenticated) {
    return (
      <div className={`bg-surface-2 border border-accent-cyan/45 rounded-xl p-12 text-center max-w-lg mx-auto mt-16 ${MOTION.develop}`}>
        <FileText className="w-10 h-10 text-accent-cyan/70 mx-auto mb-3" />
        <p className="font-display text-xl font-semibold text-text">本卷需署名调阅</p>
        <p className="text-sm text-muted font-kai mt-2">卷宗按账号租户隔离；登录署名后即可查看批注、行使定夺。</p>
        <button
          onClick={() => requireLogin()}
          className="mt-4 px-5 py-2 bg-accent-cyan text-white rounded-lg text-sm font-medium hover:opacity-90 transition-[color,background-color,opacity] duration-300"
        >
          登录调卷
        </button>
        <p className="mt-4">
          <Link to="/" className="text-xs text-muted hover:text-accent-cyan transition-colors duration-300">
            回产品首页，先看看系统是怎么运作的
          </Link>
        </p>
      </div>
    )
  }

  if (loading) return <LoadingSpinner text="加载审查详情..." />
  if (!data) return <div className="text-center py-20 text-muted">审查记录不存在</div>

  if (trackingId) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Link to="/history" className="text-muted hover:text-text transition-colors duration-300 flex items-center gap-1.5">
            <ArrowLeft className="w-4 h-4" /> 返回列表
          </Link>
          <h2 className="font-display text-2xl font-semibold text-text">幕僚复核中</h2>
        </div>
        <PipelineGraph mode="run" stepLog={stepLog} currentStep={currentStep} progress={trackProgress} error={trackError} />
        {trackError && (
          <div className="text-center">
            <button
              onClick={() => { setTrackingId(null); setRerunning(false) }}
              className="px-4 py-2 bg-surface-2 hover:bg-surface-3 text-text rounded-lg text-sm transition-colors duration-300"
            >
              返回详情
            </button>
          </div>
        )}
      </div>
    )
  }

  // ── 按条款归位：每条结论都钉在它的原文旁边 ──
  const clauses = data.clauses || []
  const clauseIds = new Set(clauses.map(c => c.id))
  const clauseBy = new Map(clauses.map(c => [c.id, c]))
  const risksBy = new Map<string, RiskFinding[]>()
  const compsBy = new Map<string, ComplianceFinding[]>()
  const suggsBy = new Map<string, Suggestion[]>()
  const orphanRisks = (data.risk_findings || []).filter(r => !r.clause_id || !clauseIds.has(r.clause_id))
  const orphanComps = (data.compliance_findings || []).filter(f => !f.clause_id || !clauseIds.has(f.clause_id))
  const orphanSuggs = (data.suggestions || []).filter(s => !s.clause_id || !clauseIds.has(s.clause_id))
  for (const r of data.risk_findings || []) {
    if (r.clause_id && clauseIds.has(r.clause_id)) {
      risksBy.set(r.clause_id, [...(risksBy.get(r.clause_id) || []), r])
    }
  }
  for (const f of data.compliance_findings || []) {
    if (f.clause_id && clauseIds.has(f.clause_id)) {
      compsBy.set(f.clause_id, [...(compsBy.get(f.clause_id) || []), f])
    }
  }
  for (const s of data.suggestions || []) {
    if (s.clause_id && clauseIds.has(s.clause_id)) {
      suggsBy.set(s.clause_id, [...(suggsBy.get(s.clause_id) || []), s])
    }
  }
  const clauseSeverity = (c: Clause): Tone => {
    const risks = risksBy.get(c.id) || []
    const comps = compsBy.get(c.id) || []
    if (risks.some(r => r.risk_level === 'high') || comps.some(f => f.status === 'non_compliant')) return 'red'
    if (risks.some(r => r.risk_level === 'medium') || comps.some(f => f.status === 'needs_review')) return 'amber'
    if (risks.length || comps.length) return 'cyan'
    return 'green'
  }
  const clauseLabel = (cid?: string): string => {
    if (!cid) return ''
    const c = clauseBy.get(cid)
    if (!c) return cid
    const no = c.section_number || clauses.indexOf(c) + 1
    return `第${no}条　${c.title}`
  }

  const sealTone: Tone =
    data.overall_risk_level === 'high' ? 'red'
    : data.overall_risk_level === 'medium' ? 'amber'
    : 'green'
  const sealLabel = RISK_LABEL[data.overall_risk_level] || RISK_LABEL.none
  const score = Math.max(0, Math.min(100, (data as any).risk_score ?? data.risk_score ?? 0))
  const missing = data.missing_clauses || []
  const regulations = Array.from(
    new Map(
      (data.compliance_findings || []).map(f => [f.regulation, { name: f.regulation, count: 0 }]),
    ).values(),
  ).map(r => ({
    ...r,
    count: (data.compliance_findings || []).filter(f => f.regulation === r.name).length,
  }))
  const fbDecision = data.human_feedback ? DECISION_LABEL[data.human_feedback.decision] : null
  const showAskHuman = data.needs_human_review && !data.human_feedback
  // 谈判弹药：高中风险 + 对手方影响 + 我方诉求（取同条款顾问草稿）
  const ammo = (data.risk_findings || [])
    .filter(r => ['high', 'medium'].includes(r.risk_level) && (r.buyer_impact || r.seller_impact))
    .slice(0, 4)
    .map(r => ({
      r,
      ask: (suggsBy.get(r.clause_id) || [])[0]?.suggested_text || '',
    }))
  const upCount = Object.values(upVoted).filter(Boolean).length

  // 审查立场：我方一侧（buyer/seller），中立为 null
  const ourSide = data.position === 'buyer' || data.position === 'seller' ? data.position : null
  const impactFor = (r: RiskFinding) =>
    ourSide === 'buyer' ? (r.buyer_impact || r.seller_impact)
    : ourSide === 'seller' ? (r.seller_impact || r.buyer_impact)
    : (r.seller_impact || r.buyer_impact)
  const impactRows = (r: RiskFinding) => {
    const rows: { side: 'buyer' | 'seller'; text: string }[] = []
    if (r.buyer_impact) rows.push({ side: 'buyer', text: r.buyer_impact })
    if (r.seller_impact) rows.push({ side: 'seller', text: r.seller_impact })
    if (ourSide) rows.sort((a, b) => Number(b.side === ourSide) - Number(a.side === ourSide))
    return rows
  }

  // 幕僚自检：用本卷已有数据做的确定性核销，不依赖判分官抽检
  const selfChecks: { level: 'ok' | 'warn'; text: string }[] = (() => {
    const items: { level: 'ok' | 'warn'; text: string }[] = []
    const degraded = data.degraded_steps || []
    const warns = data.warnings || []
    if (degraded.length) {
      items.push({ level: 'warn', text: `${degraded.map(k => STEP_OFFICER[k] || k).join('、')}环节降级，仅部分完成` })
    } else if (warns.length) {
      items.push({ level: 'warn', text: `质量提示 ${warns.length} 条，请复核批注` })
    } else {
      items.push({ level: 'ok', text: '四位幕僚环节全部完成，无降级' })
    }
    const conflictCount = (data.risk_findings || []).filter(r => riskSource(r) === 'conflict').length
    items.push(
      conflictCount
        ? { level: 'warn', text: `规则与大模型意见分歧 ${conflictCount} 处，待您裁断` }
        : { level: 'ok', text: '规则与大模型两处判定一致' },
    )
    const covered = new Set((data.suggestions || []).map(s => s.clause_id))
    const uncovered = new Set(
      (data.risk_findings || [])
        .filter(r => r.risk_level === 'high' && !covered.has(r.clause_id))
        .map(r => r.clause_id),
    ).size
    items.push(
      uncovered
        ? { level: 'warn', text: `${uncovered} 条高风险条款暂无对应改稿` }
        : { level: 'ok', text: '每条高风险均有配套改稿' },
    )
    const missingN = (data.missing_clauses || []).length
    items.push(
      missingN
        ? { level: 'warn', text: `缺少必要条款 ${missingN} 项，建议补订` }
        : { level: 'ok', text: '必要条款完备' },
    )
    if (judgeScore !== null) {
      items.push({
        level: judgeScore >= 7 ? 'ok' : 'warn',
        text: `判分官抽检评分 ${judgeScore}/10${judgeScore < 7 ? '——本卷得分偏低，请细阅' : ''}`,
      })
    }
    return items
  })()
  const selfCheckWarns = selfChecks.filter(c => c.level === 'warn').length

  // 每条批注右下角的赞踩操作
  const voteFooter = (key: string, cid?: string) => (
    <>
      <button
        onClick={() => toggleUp(key)}
        aria-label="认同这条批注"
        className={`flex items-center gap-1 px-2 py-1 rounded border text-xs transition-[color,background-color,border-color] duration-300 ${
          upVoted[key]
            ? `border-accent-green/50 text-accent-green bg-accent-green/16 ${MOTION.flip}`
            : 'border-surface-3 text-muted hover:text-text'
        }`}
      >
        <ThumbsUp className="w-3 h-3" /> 认同
      </button>
      <button
        onClick={() => toggleBad(cid)}
        aria-label="这条批注有问题，纳入反馈"
        className={`flex items-center gap-1 px-2 py-1 rounded border text-xs transition-[color,background-color,border-color] duration-300 ${
          cid && badClauses.includes(cid)
            ? `border-accent-red/50 text-accent-red bg-accent-red/16 ${MOTION.flip}`
            : 'border-surface-3 text-muted hover:text-text'
        }`}
      >
        <ThumbsDown className="w-3 h-3" /> 存疑
      </button>
    </>
  )

  const renderRiskAnno = (r: RiskFinding, key: string) => {
    const src = riskSource(r)
    const tone: Tone = r.risk_level === 'high' ? 'red' : r.risk_level === 'medium' ? 'amber' : 'cyan'
    return (
      <AnnoCard
        key={key}
        tone={tone}
        badge="风险猎手"
        icon={Crosshair}
        footer={voteFooter(key, r.clause_id)}
        right={
          <span className="flex items-center gap-1.5 flex-wrap justify-end">
            <span className={`text-[10px] font-kai border rounded-full px-2 py-0.5 ${SOURCE_META[src].cls}`}>
              {SOURCE_META[src].label}
            </span>
            <span className={`text-xs font-kai ${TONE_TEXT[tone]}`}>{RISK_LABEL[r.risk_level] || r.risk_level}</span>
          </span>
        }
      >
        <p className="text-sm text-text">{r.risk_type}</p>
        <p className="text-xs text-muted leading-relaxed">{r.description}</p>
        {impactRows(r).map(row => (
          <p key={row.side} className="text-xs text-muted">
            <span className={row.side === ourSide ? 'text-accent-cyan' : 'text-text/80'}>
              {row.side === 'buyer' ? '对买方' : '对卖方'}{row.side === ourSide ? '（我方）' : ''}：
            </span>
            {row.text}
          </p>
        ))}
        {(r.rationale || r.rag_refs?.length) && (
          <details className="mt-1">
            <summary className="text-xs text-muted cursor-pointer hover:text-text select-none w-fit">判断依据</summary>
            {r.rationale && <p className="text-xs text-muted font-kai mt-1 leading-relaxed">{r.rationale}</p>}
            <RagRefsBlock refs={r.rag_refs} />
          </details>
        )}
      </AnnoCard>
    )
  }

  const renderComplianceAnno = (f: ComplianceFinding, key: string) => (
    <AnnoCard
      key={key}
      tone={f.status === 'non_compliant' ? 'red' : f.status === 'needs_review' ? 'amber' : 'cyan'}
      badge="合规法官"
      icon={Scale}
      right={<span className="text-xs font-kai text-muted">{COMPLIANCE_LABEL[f.status] || f.status}</span>}
      footer={voteFooter(key, f.clause_id)}
    >
      <p className="text-sm text-text">{f.issue}</p>
      {f.regulation && <p className="text-xs font-display text-accent-cyan">{f.regulation}</p>}
      {f.recommendation && <p className="text-xs text-muted leading-relaxed">{f.recommendation}</p>}
      <RagRefsBlock refs={f.rag_refs} />
    </AnnoCard>
  )

  const renderSuggestionAnno = (s: Suggestion, key: string) => (
    <AnnoCard
      key={key}
      tone="green"
      badge="修订顾问"
      icon={PenLine}
      right={<span className="text-xs font-kai text-muted">{s.priority === 'high' ? '宜先办' : s.priority === 'medium' ? '随后办' : '可从长计议'}</span>}
      footer={voteFooter(key, s.clause_id)}
    >
      {/* 改前 vs 改后 并排对照 */}
      <div className="grid md:grid-cols-2 gap-2">
        <div className="rounded-lg bg-accent-red/5 border border-accent-red/20 p-2.5">
          <p className="text-[10px] tracking-[0.25em] text-accent-red/80 mb-1">改 前</p>
          <p className="text-sm leading-relaxed text-muted">{s.original_text || '（此条为增补，无对应原文）'}</p>
        </div>
        <div className="rounded-lg bg-accent-green/5 border border-accent-green/20 p-2.5">
          <p className="flex items-center justify-between text-[10px] tracking-[0.25em] text-accent-green/90 mb-1">
            改 后 · 顾问草稿
            <button
              onClick={() => copySuggestion(key, s.suggested_text)}
              className="flex items-center gap-1 normal-case tracking-normal border border-accent-green/30 rounded px-1.5 py-0.5 text-[11px] text-accent-green hover:bg-accent-green/10 transition-[color,background-color,border-color] duration-300"
              aria-label="复制修订后的条款"
            >
              {copiedKey === key ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
              {copiedKey === key ? '已复制' : '复制'}
            </button>
          </p>
          <p className="text-sm leading-relaxed text-text">{s.suggested_text}</p>
        </div>
      </div>
      {s.reason && <p className="text-xs text-muted">改动因由：{s.reason}</p>}
      <RagRefsBlock refs={s.rag_refs} />
    </AnnoCard>
  )

  return (
    <div className="space-y-6">
      {/* 卷首 */}
      <div className="flex items-center gap-4 flex-wrap">
        <Link to="/history" className="text-muted hover:text-text transition-colors duration-300 flex items-center gap-1.5">
          <ArrowLeft className="w-4 h-4" /> 返回案头
        </Link>
        <h2 className="font-display text-2xl font-semibold text-text">{data.filename || '文本审查卷'}</h2>
        <span className="text-xs font-kai text-muted border border-surface-3 rounded-full px-2.5 py-0.5">
          {data.contract_type || '合同'}
        </span>
        <span className="text-xs font-kai text-muted border border-surface-3 rounded-full px-2.5 py-0.5">
          {STATUS_LABEL[data.status] || data.status}
        </span>
        <span className="text-xs font-kai border rounded-full px-2.5 py-0.5 border-surface-3 text-muted">
          合规：{COMPLIANCE_LABEL[data.overall_compliance] || data.overall_compliance || '待复核'}
        </span>
        <span className={`text-xs font-kai border rounded-full px-2.5 py-0.5 ${(POSITION_META[data.position || 'neutral'] || POSITION_META.neutral).cls}`}>
          {(POSITION_META[data.position || 'neutral'] || POSITION_META.neutral).label}
        </span>
      </div>

      {/* 定论纸单：押印 + 风险分 + 幕僚意见 */}
      <div className="paper-card rounded-xl p-6 flex flex-col lg:flex-row lg:items-center gap-6">
        <VerdictSeal label={sealLabel} tone={sealTone} />
        <div className="flex-1 min-w-0">
          <div className="flex items-end gap-2">
            <span className="font-mono text-4xl font-bold text-paper-ink">{score}</span>
            <span className="font-mono text-xs text-paper-ink/60 mb-1.5">/100 风险评分</span>
          </div>
          <div
            className={`relative h-2 rounded-full mt-2 overflow-visible ${MOTION.settle}`}
            style={{ background: 'linear-gradient(90deg, rgb(var(--accent-green)) 0%, rgb(var(--accent-amber)) 55%, rgb(var(--accent-red)) 100%)' }}
          >
            <div
              className="absolute -top-1 h-4 w-0.5 rounded bg-paper-ink"
              style={{ left: `calc(${score}% - 1px)` }}
              aria-hidden="true"
            />
          </div>
          <p className="mt-3 text-xs font-mono text-paper-ink/70">
            条款 {clauses.length} · 风险 {(data.risk_findings || []).length} · 合规 {(data.compliance_findings || []).length} · 建议 {(data.suggestions || []).length} · 缺失 {missing.length}
          </p>
        </div>
        {data.risk_summary && (
          <div className="lg:max-w-xs border-l-2 border-accent-red/60 pl-4">
            <p className="font-kai text-sm text-paper-ink leading-6">{data.risk_summary}</p>
            <p className="text-[10px] tracking-[0.3em] text-paper-ink/50 mt-2">批注 · 幕僚意见</p>
          </div>
        )}
      </div>

      {/* AI 请求把关：人机协同的中断时刻 */}
      {showAskHuman && (
        <div className="bg-accent-amber/16 border border-accent-amber/50 rounded-xl px-5 py-4 flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="flex-1 min-w-0">
            <h3 className="font-kai text-base font-semibold text-accent-amber">幕僚已核毕，数处不敢自专 —— 请您定夺</h3>
            <p className="text-sm text-muted mt-1">检测到高风险条款，AI 已给出判断但请求人工复核，批注见下。</p>
          </div>
          <button
            onClick={() => setShowFeedbackModal(true)}
            className="shrink-0 px-5 py-2.5 bg-accent-amber text-surface-1 rounded-lg text-sm font-medium hover:opacity-90 transition-[color,background-color,opacity] duration-300"
          >
            入卷把关
          </button>
        </div>
      )}
      {TERMINAL_STATUSES.has(data.status) && !showAskHuman && !data.human_feedback && (
        <button
          onClick={() => setShowFeedbackModal(true)}
          className="px-4 py-2 rounded-lg border border-accent-cyan/50 text-accent-cyan text-sm hover:bg-accent-cyan/16 transition-[color,background-color,border-color] duration-300"
        >
          反馈本次审查结果
        </button>
      )}
      {data.human_feedback && fbDecision && (
        <div className="bg-surface-2 border border-surface-3 rounded-xl px-4 py-3 flex items-center gap-3 flex-wrap">
          <User className="w-4 h-4 text-muted" />
          <span className={`text-xs font-kai border rounded-full px-2.5 py-0.5 ${fbDecision.cls}`}>{fbDecision.label}</span>
          <span className="text-sm text-text">{data.human_feedback.reviewer}</span>
          {data.human_feedback.comments && <span className="text-sm text-muted">「{data.human_feedback.comments}」</span>}
          {data.human_feedback.timestamp && <span className="text-xs font-mono text-muted ml-auto">{fmtTime(data.human_feedback.timestamp)}</span>}
        </div>
      )}
      {data.warnings && data.warnings.length > 0 && (
        <div className="bg-accent-amber/16 border border-accent-amber/50 rounded-xl px-4 py-3">
          <h3 className="font-kai text-sm font-semibold text-accent-amber">质量提示</h3>
          <ul className="text-sm mt-1.5 list-disc pl-5 text-muted space-y-0.5">
            {data.warnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
          {data.degraded_steps && data.degraded_steps.length > 0 && (
            <p className="text-xs mt-1.5 text-muted">
              以下环节仅部分完成：{data.degraded_steps.map(k => STEP_OFFICER[k] || k).join('、')}
            </p>
          )}
        </div>
      )}

      {/* 幕僚自检：交卷前的确定性核销清单 */}
      <div className="bg-surface-2 border border-surface-3 rounded-xl overflow-hidden">
        <button
          onClick={() => setSelfCheckOpen(o => !o)}
          aria-expanded={selfCheckOpen}
          className="w-full flex items-center gap-3 px-4 py-3 hover:bg-surface-3/40 transition-colors duration-300"
        >
          <ScanText className="w-4 h-4 text-muted shrink-0" />
          <span className="text-[10px] tracking-[0.3em] text-muted">幕僚自检</span>
          <span className={`text-xs font-kai border rounded-full px-2 py-0.5 ${
            selfCheckWarns ? 'text-accent-amber border-accent-amber/40' : 'text-accent-green border-accent-green/40'
          }`}>
            {selfCheckWarns ? `${selfCheckWarns} 项需留意` : '全部通过'}
          </span>
          <ChevronDown className={`w-4 h-4 text-muted ml-auto transition-transform ${selfCheckOpen ? 'rotate-180' : ''}`} />
        </button>
        {selfCheckOpen && (
          <ul className="px-4 pb-3 space-y-1.5">
            {selfChecks.map((c, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <span className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${c.level === 'ok' ? 'bg-accent-green' : `bg-accent-amber ${MOTION.alert}`}`} />
                <span className={c.level === 'ok' ? 'text-muted' : 'text-text'}>{c.text}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* 幕僚编排拓扑（结构态）：点任一幕僚看其上下游 */}
      <details className="bg-surface-2 border border-surface-3 rounded-xl overflow-hidden">
        <summary className="px-4 py-3 cursor-pointer select-none text-[10px] tracking-[0.3em] text-muted hover:bg-surface-3/40 transition-colors duration-300">
          幕僚编排拓扑
        </summary>
        <div className="px-5 pb-5">
          <PipelineGraph mode="struct" bare stepLog={data.step_log || []} />
        </div>
      </details>

      {/* 正文：左为批注本，右为目录与卷宗 */}
      <div className="grid xl:grid-cols-[minmax(0,1fr)_320px] gap-6 items-start">
        <div>
          <div className="flex items-baseline justify-between mb-3 px-1">
            <h3 className="font-display text-lg font-semibold text-text">批注本</h3>
            <p className="text-xs text-muted font-kai">朱圈为顾问建议改动的原文，批注骑缝附于各条之后</p>
          </div>
          <div className="paper-card rounded-xl p-6 space-y-8 max-h-[72vh] overflow-y-auto">
            {clauses.length === 0 && (
              <p className="font-kai text-sm text-paper-ink/60 text-center py-8">幕僚尚未拆出条款，可稍后刷新或重新审查。</p>
            )}
            {clauses.map((c, i) => {
              const risks = risksBy.get(c.id) || []
              const comps = compsBy.get(c.id) || []
              const suggs = suggsBy.get(c.id) || []
              return (
                <section key={c.id || i} id={`clause-${i}`} className={flashIdx === i ? `rounded-lg ${MOTION.scan}` : ''}>
                  <div>
                    <div className="flex items-baseline justify-between gap-3">
                      <h4 className="font-display text-base font-semibold text-paper-ink">
                        第{c.section_number || i + 1}条　{c.title}
                      </h4>
                      <span className="shrink-0 text-[11px] font-kai text-paper-ink/55 border border-paper-ink/25 rounded-full px-2 py-0.5">
                        {c.category || '条款'}
                      </span>
                    </div>
                    <p className="font-display text-[15px] text-paper-ink mt-1.5 paper-lines">
                      {renderClauseText(c.content || '', suggs)}
                    </p>
                    {c.entities && c.entities.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {c.entities.slice(0, 6).map((e, j) => (
                          <span key={j} className="text-[11px] font-mono text-paper-ink/65 border border-paper-ink/20 rounded px-1.5 py-0.5">
                            {e.entity_type}·{e.value}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  {(risks.length > 0 || comps.length > 0 || suggs.length > 0) && (
                    <div className="mt-3 md:ml-6 space-y-2">
                      {risks.map((r, j) => renderRiskAnno(r, `r-${c.id}-${j}`))}
                      {comps.map((f, j) => renderComplianceAnno(f, `c-${c.id}-${j}`))}
                      {suggs.map((s, j) => renderSuggestionAnno(s, `s-${c.id}-${j}`))}
                    </div>
                  )}
                </section>
              )
            })}
            {missing.length > 0 && (
              <section className="rounded-r-lg border-l-[3px] border-accent-red/80 bg-accent-red/5 px-4 py-3">
                <p className="font-kai text-sm font-semibold text-accent-red">缺失条款 · 合规法官提请留意</p>
                <ul className="text-sm mt-1.5 list-disc pl-5 text-paper-ink/80 space-y-0.5">
                  {missing.map((m, j) => <li key={j}>{m}</li>)}
                </ul>
              </section>
            )}
          </div>

          {/* 逐条赞踩的汇总：意见成型，一键入反馈 */}
          {(upCount > 0 || badClauses.length > 0) && (
            <div className="mt-3 flex items-center gap-3 flex-wrap px-1 text-sm">
              <span className="text-muted">已认同 <span className="text-accent-green font-mono">{upCount}</span> 条 · 存疑卷宗 <span className="text-accent-red font-mono">{badClauses.length}</span> 条</span>
              {badClauses.length > 0 && (
                <button
                  onClick={() => setShowFeedbackModal(true)}
                  className="px-3.5 py-1.5 rounded-lg bg-accent-cyan text-white text-xs font-medium hover:opacity-90 transition-[color,background-color,opacity] duration-300"
                >
                  将存疑条款提交反馈
                </button>
              )}
            </div>
          )}

          {/* 游离于条款之外的批注，如实陈列 */}
          {(orphanRisks.length > 0 || orphanComps.length > 0 || orphanSuggs.length > 0) && (
            <div className="mt-6">
              <h3 className="font-display text-base font-semibold text-text mb-2 px-1">散页批注（未能归位到条款）</h3>
              <div className="space-y-2">
                {orphanRisks.map((r, j) => renderRiskAnno(r, `or-${j}`))}
                {orphanComps.map((f, j) => renderComplianceAnno(f, `oc-${j}`))}
                {orphanSuggs.map((s, j) => renderSuggestionAnno(s, `os-${j}`))}
              </div>
            </div>
          )}
        </div>

        {/* 右栏：目录、法规、谈判、卷宗 */}
        <div className="space-y-5">
          <div className={`bg-surface-2 border border-surface-3 rounded-xl overflow-hidden hover:border-accent-cyan/50 ${MOTION.lift}`}>
            <p className="px-4 pt-4 pb-2 text-[10px] tracking-[0.3em] text-muted">目录 · 点击定位</p>
            {clauses.length === 0 ? (
              <p className="px-4 pb-4 text-xs text-muted font-kai">暂无条款。</p>
            ) : (
              <ul className="max-h-72 overflow-y-auto divide-y divide-surface-3/60">
                {clauses.map((c, i) => (
                  <li key={c.id || i}>
                    <button
                      onClick={() => goToClause(i)}
                      className={`sweep-band w-full text-left px-4 py-2.5 flex items-center gap-2.5 hover:bg-surface-3/50 transition-colors duration-300 ${MOTION.sweep}`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${TONE_DOT[clauseSeverity(c)]}`} />
                      <span className="min-w-0 flex-1">
                        <span className="font-display text-sm text-text">第{c.section_number || i + 1}条</span>
                        <span className="text-sm text-muted ml-2 truncate">{c.title}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className={`bg-surface-2 border border-surface-3 rounded-xl overflow-hidden hover:border-accent-cyan/50 ${MOTION.lift}`}>
            <p className="px-4 pt-4 pb-2 text-[10px] tracking-[0.3em] text-muted">援引法规</p>
            {regulations.length === 0 ? (
              <p className="px-4 pb-4 text-xs text-muted font-kai">本卷未援引法规条文。</p>
            ) : (
              <ul className="divide-y divide-surface-3/60">
                {regulations.map(r => (
                  <li key={r.name} className="px-4 py-2.5 flex items-center justify-between gap-3">
                    <span className="font-display text-sm text-text truncate">{r.name}</span>
                    <span className="text-xs font-mono text-accent-cyan shrink-0">{r.count} 处</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* 谈判要点：把风险与诉求整理成上桌可用的弹药 */}
          {ammo.length > 0 && (
            <div className={`bg-surface-2 border border-surface-3 rounded-xl overflow-hidden hover:border-accent-cyan/50 ${MOTION.lift}`}>
              <p className="px-4 pt-4 pb-2 text-[10px] tracking-[0.3em] text-muted">谈判要点 · 自批注提炼</p>
              <ul className="divide-y divide-surface-3/60">
                {ammo.map(({ r, ask }, j) => (
                  <li key={j} className="px-4 py-3">
                    <p className="text-sm text-text">
                      <span className="font-display">{clauseLabel(r.clause_id)}</span>
                      <span className="text-muted"> · {r.risk_type}</span>
                    </p>
                    <p className="text-xs text-muted mt-1 leading-relaxed">
                      利害{ourSide ? '（我方）' : ''}：{impactFor(r)}
                    </p>
                    {ask && <p className="text-xs text-accent-green mt-1 leading-relaxed">我方主张：{ask.length > 64 ? ask.slice(0, 64) + '…' : ask}</p>}
                  </li>
                ))}
              </ul>
              <div className="px-4 py-3 border-t border-surface-3">
                <button
                  onClick={handleNegotiate}
                  disabled={negotiating}
                  className="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg border border-accent-purple/50 text-accent-purple text-sm hover:bg-accent-purple/16 transition-[color,background-color,border-color] duration-300 disabled:opacity-50"
                >
                  <MessageSquare className="w-4 h-4" />
                  {negotiating ? '正在开席…' : '带要点入协商'}
                </button>
              </div>
            </div>
          )}

          <div className={`bg-surface-2 border border-surface-3 rounded-xl p-4 space-y-3 hover:border-accent-cyan/50 ${MOTION.lift}`}>
            <p className="text-[10px] tracking-[0.3em] text-muted">卷宗</p>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={downloadWith(api.downloadReport)}
                className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg border border-surface-3 text-text text-sm hover:border-accent-cyan/50 transition-[color,background-color,border-color] duration-300"
              >
                <Download className="w-4 h-4" /> PDF 报告
              </button>
              <button
                onClick={downloadWith(api.downloadWord)}
                className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-accent-cyan text-white text-sm font-medium hover:opacity-90 transition-[color,background-color,opacity] duration-300"
              >
                <Download className="w-4 h-4" /> Word 报告
              </button>
              <button
                onClick={downloadWith(api.downloadRedline)}
                title="删除线为建议删、下划线为建议增，可直接发给对方或贴回合同"
                className="col-span-2 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg border border-accent-green/50 text-accent-green text-sm hover:bg-accent-green/16 transition-[color,background-color,border-color] duration-300"
              >
                <Download className="w-4 h-4" /> 修订版红线（Word）
              </button>
            </div>
            <button
              onClick={handleRerun}
              disabled={rerunning}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-surface-3 hover:bg-surface-4 text-text text-sm transition-colors duration-300 disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${rerunning ? MOTION.spin : ''}`} />
              {rerunning ? '幕僚复核中…' : '重新审查'}
            </button>
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-accent-red text-sm hover:bg-accent-red/16 transition-[color,background-color] duration-300 disabled:opacity-50"
            >
              <Trash2 className="w-4 h-4" /> 删除本卷
            </button>
            <div className="pt-1 border-t border-surface-3 space-y-1.5 text-xs text-muted">
              <p className="flex items-center gap-1.5"><FileText className="w-3.5 h-3.5" /><span className="truncate">{data.filename || '(文本审查)'}</span></p>
              <p className="flex items-center gap-1.5"><Calendar className="w-3.5 h-3.5" />成卷 {fmtTime(data.created_at)}</p>
              {data.updated_at && <p className="flex items-center gap-1.5"><Clock className="w-3.5 h-3.5" />最近批注 {fmtTime(data.updated_at)}</p>}
              <p className="flex items-center gap-1.5"><ScanText className="w-3.5 h-3.5" /><span className="font-mono truncate">{data.review_id}</span></p>
            </div>
          </div>
        </div>
      </div>

      <FeedbackModal
        isOpen={showFeedbackModal}
        onClose={() => setShowFeedbackModal(false)}
        onSubmit={handleFeedbackSubmit}
        clauses={clauses.map(c => ({ id: c.id, title: c.title, content: c.content }))}
        defaultReviewer={username || ''}
        defaultBadClauses={badClauses}
        defaultDecision={badClauses.length > 0 ? 'modify' : undefined}
        title={data.needs_human_review ? '入卷把关 · 人工审核' : '反馈审查结果'}
      />
    </div>
  )
}
