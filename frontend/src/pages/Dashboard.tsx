import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, PenLine, Scale, ScanText, Settings, Crosshair, Upload, BookOpen, GitCompare } from 'lucide-react'
import { useApi, usePolling } from '../hooks/useApi'
import { useAuth, isAuthed } from '../hooks/useAuth'
import { api } from '../api/client'
import { MOTION } from '../lib/motion'

const RISK_DOT: Record<string, string> = {
  high: 'bg-accent-red',
  medium: 'bg-accent-amber',
  low: 'bg-accent-green',
  none: 'bg-accent-green',
}

const STATUS_TEXT: Record<string, string> = {
  pending: '排队中',
  processing: '核阅中',
  awaiting_human: '待把关',
  completed: '已核阅',
  approved: '已放行',
  rejected: '已驳回',
  failed: '中断',
}

const STAFF = [
  { icon: ScanText, name: '条款拆解官', duty: '逐条拆解合同条款' },
  { icon: Crosshair, name: '风险猎手', duty: '规则引擎与大模型双轨排查' },
  { icon: Scale, name: '合规法官', duty: '对照现行法规条文' },
  { icon: PenLine, name: '修订顾问', duty: '起草修改意见' },
]

const SLIP_NUMERALS = ['壹', '贰', '叁', '肆']

export default function Dashboard() {
  const navigate = useNavigate()
  const fileRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const { isAuthenticated } = useAuth()

  // 访客不发鉴权请求：数据接口一律静默空转，页面走引导态
  const { data: history } = usePolling(() => (isAuthed() ? api.listReviews(1, 20) : Promise.resolve(null)), 15000)
  const { data: metrics } = usePolling(() => (isAuthed() ? api.getMetrics() : Promise.resolve(null)), 30000)
  const { data: health } = usePolling(() => api.health(), 15000)
  const { data: ruleStats } = useApi(() => (isAuthed() ? api.getRuleStats() : Promise.resolve(null)))

  const items = history?.items ?? []
  const pending = items.filter(
    i => i.status === 'awaiting_human' || (i.needs_human_review && !['approved', 'rejected'].includes(i.status))
  )
  const running = items.filter(i => ['pending', 'processing'].includes(i.status))
  const highTotal = metrics?.risk_distribution?.high ?? items.filter(i => i.overall_risk_level === 'high').length
  // 数据飞轮：您押印/驳回的每一卷，都会回流为幕僚的学习样本
  const sealed = items.filter(i => ['approved', 'rejected'].includes(i.status)).length

  const today = new Date()
  const dateLabel = `${today.getFullYear()}年${today.getMonth() + 1}月${today.getDate()}日 · ${today.toLocaleDateString('zh-CN', { weekday: 'long' })}`

  const openFile = (f: File | undefined | null) => {
    if (f) navigate('/review', { state: { file: f } })
  }

  const slips = [
    { value: pending.length, label: '待您把关', hint: '幕僚拿不准的卷宗', onClick: () => navigate('/history') },
    { value: running.length, label: '正在核阅', hint: '幕僚办案中，须臾即复', onClick: () => navigate('/history') },
    { value: highTotal, label: '累计高风险', hint: '全部审查的风险定级', onClick: () => navigate('/history') },
    { value: ruleStats?.enabled ?? '—', label: '在库规则', hint: '规则引擎枕戈待旦', onClick: () => navigate('/rules') },
  ]

  return (
    <div className="space-y-6">
      {/* 案头题签 */}
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <p className="text-xs font-mono text-muted tracking-[0.2em]">{dateLabel}</p>
          <h2 className="font-display text-3xl font-semibold text-text mt-1">案头</h2>
          <p className="font-kai text-sm text-muted mt-1.5">合同铺开在案，四位 AI 法务幕僚代为核阅，供您押印定夺。</p>
        </div>
        <button
          onClick={() => navigate('/review')}
          className="px-4 py-2 rounded-lg border border-accent-cyan/50 text-accent-cyan text-sm font-medium hover:bg-accent-cyan/16 transition-[color,background-color,border-color] duration-300"
        >
          粘贴文本审查
        </button>
      </div>

      {/* 账册条；访客换成登录引导纸单 */}
      {isAuthenticated ? (
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          {slips.map((s, i) => (
            <button
              key={s.label}
              onClick={s.onClick}
              style={{ animationDelay: `${i * 80}ms` }}
              className={`text-left bg-surface-2 border border-surface-3 rounded-xl p-4 hover:border-accent-cyan/50 ${MOTION.lift} ${MOTION.develop}`}
            >
              <p className="font-display text-xs text-muted">{SLIP_NUMERALS[i]}</p>
              <p className="mt-1 text-2xl font-mono font-semibold text-text">{s.value}</p>
              <p className="text-sm text-text mt-0.5">{s.label}</p>
              <p className="text-xs text-muted mt-0.5">{s.hint}</p>
            </button>
          ))}
        </div>
      ) : (
        <div className={`bg-surface-2 border border-accent-cyan/45 rounded-xl p-8 text-center ${MOTION.develop}`}>
          <p className="font-display text-2xl font-semibold text-text">案上暂无卷宗</p>
          <p className="text-sm text-muted font-kai mt-2">登录后即可铺纸立卷、逐条把关；不登录也能拖卷开审前先一观。</p>
          <button
            onClick={() => navigate('/login?from=%2Fdashboard')}
            className="mt-4 px-5 py-2 rounded-lg bg-accent-cyan text-white text-sm font-medium hover:opacity-90 transition-[color,background-color,opacity] duration-300"
          >
            登录立卷
          </button>
        </div>
      )}

      <div className="grid xl:grid-cols-[minmax(0,1fr)_340px] gap-6 items-start">
        <div className="space-y-6">
          {/* 铺纸：拖拽或点选上传 */}
          <div
            onDragOver={e => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={e => {
              e.preventDefault()
              setDragOver(false)
              openFile(e.dataTransfer.files?.[0])
            }}
            className={`paper-card rounded-xl p-6 transition-shadow ${dragOver ? 'ring-2 ring-accent-cyan' : ''}`}
          >
            <div
              role="button"
              tabIndex={0}
              aria-label="选择合同文件上传"
              onClick={() => fileRef.current?.click()}
              onKeyDown={e => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  fileRef.current?.click()
                }
              }}
              className={`border-2 border-dashed rounded-lg py-10 px-4 flex flex-col items-center gap-2.5 text-center cursor-pointer transition-colors ${
                dragOver ? 'border-accent-cyan bg-accent-cyan/16' : 'border-paper-ink/25 hover:border-paper-ink/45'
              }`}
            >
              <Upload className="w-8 h-8 text-paper-ink/50" />
              <p className="font-display text-lg font-semibold text-paper-ink">合同拖到案上，即刻铺纸开审</p>
              <p className="font-kai text-sm text-paper-ink/60">支持 PDF · DOCX · DOC · TXT；多份请到「合同审查」批量上传</p>
              <span className="mt-2 px-5 py-2 rounded-lg bg-accent-cyan text-white text-sm font-medium hover:opacity-90 transition">
                选择文件
              </span>
            </div>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.docx,.doc,.txt"
              className="hidden"
              onChange={e => { openFile(e.target.files?.[0]); if (fileRef.current) fileRef.current.value = '' }}
            />
          </div>

          {/* 幕僚就位：让用户在开审前就知道谁在场 */}
          <div className="bg-surface-2 border border-surface-3 rounded-xl p-5">
            <p className="text-[10px] tracking-[0.3em] text-muted mb-4">幕僚就位</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {STAFF.map(({ icon: Icon, name, duty }) => (
                <div key={name} className={`flex items-start gap-2.5 bg-surface-1 border border-surface-3 rounded-lg p-3 hover:border-accent-cyan/50 ${MOTION.lift}`}>
                  <Icon className="w-5 h-5 flex-shrink-0 mt-0.5 text-accent-cyan" />
                  <div className="min-w-0">
                    <p className="font-kai text-sm font-semibold text-text">{name}</p>
                    <p className="text-xs text-muted leading-snug mt-0.5">{duty}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 右侧文书匣；访客换成免登录可逛入口 */}
        <div className="space-y-6">
          {isAuthenticated ? (
            <>
              <div className="bg-surface-2 border border-surface-3 rounded-xl overflow-hidden">
                <p className="px-4 pt-4 pb-2 text-[10px] tracking-[0.3em] text-muted">待您把关</p>
                {pending.length === 0 ? (
                  <p className="px-4 pb-4 text-xs text-muted font-kai">案头无积压，卷卷已办结。</p>
                ) : (
                  <ul className="divide-y divide-surface-3">
                    {pending.slice(0, 5).map(i => (
                      <li key={i.review_id}>
                        <button
                          onClick={() => navigate(`/review/${i.review_id}`)}
                          className={`sweep-band w-full text-left px-4 py-3 hover:bg-surface-3/50 transition-colors duration-300 flex items-center gap-2.5 ${MOTION.sweep}`}
                        >
                          <span className={`w-2 h-2 rounded-full bg-accent-amber ${MOTION.alert} flex-shrink-0`} />
                          <div className="min-w-0 flex-1">
                            <p className="text-sm text-text truncate">{i.filename || '(文本审查)'}</p>
                            <p className="text-xs text-muted truncate">{i.risk_summary || '幕僚已呈报，请您定夺'}</p>
                          </div>
                          <ArrowRight className="w-3.5 h-3.5 text-muted flex-shrink-0" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="bg-surface-2 border border-surface-3 rounded-xl overflow-hidden">
                <p className="px-4 pt-4 pb-2 text-[10px] tracking-[0.3em] text-muted">最近核阅</p>
                {items.length === 0 ? (
                  <p className="px-4 pb-4 text-xs text-muted font-kai">尚无卷宗 —— 铺一份合同，开始第一次审查。</p>
                ) : (
                  <ul className="divide-y divide-surface-3">
                    {items.slice(0, 6).map(i => (
                      <li key={i.review_id}>
                        <button
                          onClick={() => navigate(`/review/${i.review_id}`)}
                          className={`sweep-band w-full text-left px-4 py-3 hover:bg-surface-3/50 transition-colors duration-300 flex items-center gap-2.5 ${MOTION.sweep}`}
                        >
                          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${RISK_DOT[i.overall_risk_level] || 'bg-muted'}`} />
                          <div className="min-w-0 flex-1">
                            <p className="text-sm text-text truncate">{i.filename || i.contract_type || '(文本审查)'}</p>
                            <p className="text-xs text-muted font-mono">{i.created_at?.slice(5, 10)}</p>
                          </div>
                          <span className="text-xs text-muted flex-shrink-0">{STATUS_TEXT[i.status] || i.status}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="px-4 py-3 border-t border-surface-3/60 text-[11px] text-muted font-kai">
                  {sealed > 0
                    ? `近期卷宗中您已把关 ${sealed} 卷 —— 您的每次定夺，幕僚都记进 lessons`
                    : '您的首次把关定夺，将成为幕僚学习的起点'}
                </p>
              </div>
            </>
          ) : (
            <div className={`bg-surface-2 border border-accent-cyan/45 rounded-xl p-5 ${MOTION.develop}`}>
              <p className="text-[10px] tracking-[0.3em] text-muted mb-3">免登录可逛</p>
              <div className="space-y-2">
                <Link
                  to="/regulations"
                  className={`flex items-center gap-2.5 bg-surface-1 border border-surface-3 rounded-lg px-3 py-2.5 text-sm text-text hover:border-accent-cyan/50 ${MOTION.lift}`}
                >
                  <BookOpen className="w-4 h-4 flex-shrink-0 text-accent-cyan" />
                  <span className="flex-1">法规引用</span>
                  <span className="text-xs text-muted">现行条文可查</span>
                </Link>
                <Link
                  to="/diff"
                  className={`flex items-center gap-2.5 bg-surface-1 border border-surface-3 rounded-lg px-3 py-2.5 text-sm text-text hover:border-accent-cyan/50 ${MOTION.lift}`}
                >
                  <GitCompare className="w-4 h-4 flex-shrink-0 text-accent-cyan" />
                  <span className="flex-1">版本对比</span>
                  <span className="text-xs text-muted">两稿逐行比对</span>
                </Link>
              </div>
              <p className="mt-3 text-[11px] text-muted font-kai">递交卷宗、把关定夺需登录署名后进行。</p>
            </div>
          )}

          {/* 运维状态收进一行小字，不打扰业务用户 */}
          <div className="flex items-center justify-between text-xs text-muted px-1">
            <span className="flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${health?.status === 'healthy' ? 'bg-accent-green' : 'bg-accent-amber'}`} />
              服务{health?.status === 'healthy' ? '正常' : '降级'} · 数据库{health?.database === 'connected' ? '已连接' : '未连接'}
            </span>
            <button onClick={() => navigate('/settings')} className="flex items-center gap-1 hover:text-text transition" aria-label="前往系统设置">
              <Settings className="w-3.5 h-3.5" />
              系统设置
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
