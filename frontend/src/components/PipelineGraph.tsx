import { useEffect, useRef, useState } from 'react'
import type { StepEvent } from '../types'
import { MOTION } from '../lib/motion'
import { useReducedMotion } from '../hooks/useReducedMotion'

/**
 * 幕僚编排拓扑图，一组件两形态 + 一演示档：
 * - struct 结构态：纯静态关系图，仅 CSS 过渡（选中高亮 / 邻居弱高亮 / 无关降透明）；
 * - run   执行态：SMIL 连线流动 + 数据包粒子 + 跑马边框 + 降级脉冲（prefers-reduced-motion 时全停）；
 * - demo  （仅配 struct 用）落地页自动演示：phase 时钟推演 待命→运行→办结 循环，SMIL 同执行态。
 */

type NodeStatus = 'pending' | 'active' | 'done' | 'degraded' | 'failed'

const STATUS_TEXT: Record<NodeStatus, string> = {
  pending: '待命', active: '办案中', done: '已办结', degraded: '降级办结', failed: '中断',
}

// 静态颜色映射表（字面量，禁止运行时拼接）
const RING: Record<NodeStatus, string> = {
  pending: 'rgb(var(--surface-4))',
  active: 'rgb(var(--accent-cyan))',
  done: 'rgb(var(--accent-green))',
  degraded: 'rgb(var(--accent-amber))',
  failed: 'rgb(var(--accent-red))',
}
const FILL: Record<NodeStatus, string> = {
  pending: 'rgb(var(--surface-2) / 0.16)',
  active: 'rgb(var(--accent-cyan) / 0.16)',
  done: 'rgb(var(--accent-green) / 0.16)',
  degraded: 'rgb(var(--accent-amber) / 0.16)',
  failed: 'rgb(var(--accent-red) / 0.16)',
}

// 布局：三泳道四节点（拆解 → 猎手∥法官会审 → 顾问收尾）
const NODES = [
  { key: 'clause_extraction', name: '条款拆解官', x: 20, y: 82 },
  { key: 'risk_identification', name: '风险猎手', x: 244, y: 30 },
  { key: 'compliance_check', name: '合规法官', x: 244, y: 134 },
  { key: 'suggestion', name: '修订顾问', x: 468, y: 82 },
] as const
type NodeKey = (typeof NODES)[number]['key']
export type { NodeKey }
const NW = 152
const NH = 64
const LANES = [
  { label: '拆解', x: 6, w: 190 },
  { label: '会审', x: 224, w: 190 },
  { label: '收尾', x: 448, w: 190 },
]
const EDGES = [
  { id: 'e0', from: 'clause_extraction', to: 'risk_identification', d: 'M172 114 C 208 114 208 62 244 62' },
  { id: 'e1', from: 'clause_extraction', to: 'compliance_check', d: 'M172 114 C 208 114 208 166 244 166' },
  { id: 'e2', from: 'risk_identification', to: 'suggestion', d: 'M396 62 C 432 62 432 114 468 114' },
  { id: 'e3', from: 'compliance_check', to: 'suggestion', d: 'M396 166 C 432 166 432 114 468 114' },
] as const

// SMIL 流动参数：dashoffset 位移必须是 dasharray 周期的整数倍，防跳帧
// 待命 2 6（周期 8，-48=8×6，4.6s）；激活 5 7（周期 12，-120=12×10，2.6s）
const FLOW_IDLE = { dash: '2 6', to: -48, dur: '4.6s' }
const FLOW_ACTIVE = { dash: '5 7', to: -120, dur: '2.6s' }

// ── demo（落地页自动演示）：phase 时钟推演，不依赖 stepLog ──
// phase 0 拆解运行 / 1 猎手∥法官会审 / 2 顾问收尾 / 3 全办结停顿帧，循环
const DEMO_STEPS: NodeKey[] = ['clause_extraction', 'risk_identification', 'compliance_check', 'suggestion']
const DEMO_EDGE_PHASE: Record<string, number> = { e0: 1, e1: 1, e2: 2, e3: 2 }
// 演示假耗时：done 后展示，纯叙事
const DEMO_MS: Record<NodeKey, number> = { clause_extraction: 412, risk_identification: 688, compliance_check: 540, suggestion: 320 }
const DEMO_STATUS_TEXT: Record<NodeStatus, string> = {
  pending: '待命', active: '运行中…', done: '已完成', degraded: '已完成', failed: '已完成',
}

interface Props {
  mode: 'struct' | 'run'
  stepLog: StepEvent[]
  /** run：当前进行中环节；struct：可不传，按 stepLog 静态着色 */
  currentStep?: string
  /** run：0~1 进度 */
  progress?: number
  error?: string
  /** struct：受控选中节点 */
  selected?: NodeKey | null
  onSelect?: (key: NodeKey) => void
  /** struct：外层已有标题时关掉内置标题 */
  bare?: boolean
  /** 仅配 struct 用：落地页自动演示环（phase 时钟 + SMIL 流动）；注意 #pg-glow 滤镜 id 全局唯一，勿同屏双 demo */
  demo?: boolean
}

function fmtClock(iso: string): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleTimeString('zh-CN', { hour12: false })
  } catch {
    return ''
  }
}

function fmtDuration(startIso: string, endIso: string | null): string {
  if (!startIso || !endIso) return ''
  const ms = new Date(endIso).getTime() - new Date(startIso).getTime()
  if (!Number.isFinite(ms) || ms < 0) return ''
  return `${(ms / 1000).toFixed(1)}s`
}

export default function PipelineGraph({ mode, stepLog, currentStep = '', progress = 0, error, selected = null, onSelect, bare = false, demo = false }: Props) {
  const reduced = useReducedMotion()
  const logRef = useRef<HTMLDivElement>(null)
  const [innerSelected, setInnerSelected] = useState<NodeKey | null>(null)
  // demo 相位时钟：reduced 或非 demo 不起表（demo+reduced 冻结为全办结终稿）
  const [phase, setPhase] = useState(0)
  useEffect(() => {
    if (!demo || reduced) return
    const id = window.setInterval(() => setPhase(p => (p + 1) % 4), 2600)
    return () => window.clearInterval(id)
  }, [demo, reduced])
  useEffect(() => {
    if (mode !== 'run') return
    const el = logRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [stepLog.length, mode])

  // 每个节点取最后一次事件
  const lastEvent = new Map<string, StepEvent>()
  for (const e of stepLog) lastEvent.set(e.step, e)

  const statusOf = (key: string): NodeStatus => {
    const ev = lastEvent.get(key)
    if (ev?.status === 'error') return 'failed'
    if (ev?.message?.includes('降级')) return 'degraded'
    if (ev?.status === 'done') return 'done'
    if (currentStep === key || ev?.status === 'running') return 'active'
    return 'pending'
  }

  // demo 相位→节点态（phase3 时所有 index<phase 恒真 → 全 done 停顿帧）
  const demoStatus = (key: NodeKey): NodeStatus => {
    if (reduced) return 'done'
    const i = DEMO_STEPS.indexOf(key)
    return i < phase ? 'done' : i === phase ? 'active' : 'pending'
  }
  const viewStatus = (key: NodeKey): NodeStatus => (demo ? demoStatus(key) : statusOf(key))

  // struct 模式的选中关系：受控优先，其次内部状态
  const sel = mode === 'struct' ? (selected ?? innerSelected) : null
  const neighborOf = (a: NodeKey, b: NodeKey) =>
    EDGES.some(e => (e.from === a && e.to === b) || (e.from === b && e.to === a))
  const relation = (key: NodeKey): 'self' | 'near' | 'none' =>
    sel == null ? 'none' : sel === key ? 'self' : neighborOf(sel, key) ? 'near' : 'none'

  const pct = Math.round(Math.max(0, Math.min(1, progress)) * 100)

  const topo = (
    <svg viewBox="0 0 644 220" className="w-full h-auto select-none" role="img" aria-label="幕僚编排拓扑图">
      {(mode === 'run' || demo) && !reduced && (
        <defs>
          {/* 外发光：模糊副本垫在原图之下 */}
          <filter id="pg-glow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
      )}

      {/* 泳道：虚线框，纯静态无动画 */}
      {LANES.map(l => (
        <g key={l.label}>
          <rect x={l.x} y={10} width={l.w} height={200} rx={12} fill="none"
            stroke="rgb(var(--surface-3))" strokeDasharray="3 5" />
          <text x={l.x + 12} y={28} fontSize={10} letterSpacing="0.3em"
            style={{ fill: 'rgb(var(--muted))' }}>{l.label}</text>
        </g>
      ))}

      {/* 连线：激活优先级 悬停选中 > demo 相位 > run 进度 */}
      {EDGES.map(e => {
        const active = mode === 'run'
          ? ['done', 'degraded'].includes(statusOf(e.from))
          : sel != null
            ? (e.from === sel || e.to === sel)
            : demo && DEMO_EDGE_PHASE[e.id] === phase
        const flow = mode === 'run' ? (active ? FLOW_ACTIVE : FLOW_IDLE) : demo && active ? FLOW_ACTIVE : null
        return (
          <g key={e.id} className="transition-[opacity] duration-300" style={{ opacity: sel != null && !active ? 0.4 : active ? 1 : 0.4 }}>
            <path
              d={e.d}
              fill="none"
              strokeWidth={active ? 2 : 1.4}
              stroke={active ? RING.active : mode === 'run' ? RING.pending : 'rgb(var(--surface-4))'}
              strokeDasharray={flow?.dash}
              className="transition-[stroke] duration-300"
            >
              {/* key 绑定 lit 态：SMIL 属性变更不生效，靠重建元素切换流动参数 */}
              {flow && !reduced && (
                <animate
                  key={active ? 'lit' : 'idle'}
                  attributeName="stroke-dashoffset"
                  from="0"
                  to={flow.to}
                  dur={flow.dur}
                  repeatCount="indefinite"
                />
              )}
            </path>
            {/* 数据包粒子：仅激活连线挂载，卸载即停 */}
            {(mode === 'run' || demo) && active && !reduced && (
              <circle r={3.6} fill={RING.active} filter="url(#pg-glow)">
                <animateMotion dur="2.2s" repeatCount="indefinite" path={e.d} />
              </circle>
            )}
          </g>
        )
      })}

      {/* 节点 */}
      {NODES.map(n => {
        const st = viewStatus(n.key)
        const rel = relation(n.key)
        const ev = lastEvent.get(n.key)
        const dur = demo
          ? (st === 'done' ? `${DEMO_MS[n.key]} ms` : '')
          : (st === 'done' || st === 'degraded' ? fmtDuration(ev?.started_at || '', ev?.finished_at || null) : '')
        const ring = rel === 'self' ? RING.active : rel === 'near' ? 'rgb(var(--accent-cyan) / 0.45)' : RING[st]
        const strokeWidth = rel === 'self' ? 2 : 1.5
        return (
          <g
            key={n.key}
            onClick={mode === 'struct' ? () => { setInnerSelected(k => (k === n.key ? null : n.key)); onSelect?.(n.key) } : undefined}
            className={mode === 'struct' ? 'cursor-pointer' : undefined}
            style={{ opacity: sel != null && rel === 'none' ? 0.5 : 1, transition: 'opacity 300ms' }}
          >
            <rect
              x={n.x} y={n.y} width={NW} height={NH} rx={12}
              fill={FILL[st]} stroke={ring} strokeWidth={strokeWidth}
              className="transition-[stroke,fill] duration-500"
            />
            {/* 跑马边框：执行态/演示态的激活节点 */}
            {(mode === 'run' || demo) && st === 'active' && !reduced && (
              <rect
                x={n.x + 4} y={n.y + 4} width={NW - 8} height={NH - 8} rx={9}
                fill="none" stroke={RING.active} strokeOpacity={0.6} strokeDasharray="6 4"
              >
                {/* -140 = (6+4)×14，周期整数倍防跳帧 */}
                <animate attributeName="stroke-dashoffset" from="0" to="-140" dur="2s" repeatCount="indefinite" />
              </rect>
            )}
            <circle cx={n.x + 18} cy={n.y + 22} r={4} fill={RING[st]} className="transition-[fill] duration-500" />
            {/* 降级脉冲：挂载即播一次，r 4→9→4、透明度 1→0.3→1 */}
            {st === 'degraded' && mode === 'run' && !reduced && (
              <g>
                <circle cx={n.x + 18} cy={n.y + 22} r={4} fill={RING.degraded}>
                  <animate attributeName="r" values="4;9;4" dur="1.1s" fill="freeze" />
                  <animate attributeName="opacity" values="1;0.3;1" dur="1.1s" fill="freeze" />
                </circle>
              </g>
            )}
            <text x={n.x + 30} y={n.y + 27} fontSize={13}
              style={{ fill: 'rgb(var(--text))', fontFamily: '"KaiTi","STKaiti",serif', fontWeight: 600 }}>
              {n.name}
            </text>
            <text x={n.x + 18} y={n.y + 48} fontSize={10}
              style={{ fill: st === 'pending' ? 'rgb(var(--muted))' : RING[st] }}>
              {demo ? DEMO_STATUS_TEXT[st] : STATUS_TEXT[st]}{dur ? ` · ${dur}` : ''}
            </text>
          </g>
        )
      })}
    </svg>
  )

  // ── 结构态：只交拓扑图本身，标题与交互留给调用方 ──
  if (mode === 'struct') {
    return bare ? topo : (
      <div className="bg-surface-2 border border-surface-3 rounded-xl p-5">
        <h3 className="font-display text-base font-semibold text-text mb-1">幕僚编排拓扑</h3>
        <p className="text-xs text-muted font-kai mb-3">点任一幕僚，看它在编排中的上下游</p>
        {topo}
      </div>
    )
  }

  // ── 执行态：接力画面（标题、进度、拓扑、工作日志、错误） ──
  return (
    <div className="max-w-3xl mx-auto">
      <div className="bg-surface-2 border border-surface-3 rounded-xl p-6">
        <div className="flex items-baseline justify-between mb-1">
          <h3 className="font-display text-xl font-semibold text-text">四位幕僚正在核阅</h3>
          <span className="text-sm font-mono text-accent-cyan">{pct}%</span>
        </div>
        <p className="text-xs text-muted font-kai mb-4">条款拆解官先行，风险猎手与合规法官并行会审，修订顾问收尾</p>
        <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden mb-4">
          <div className="h-full bg-accent-cyan transition-all duration-500 ease-out" style={{ width: `${pct}%` }} />
        </div>

        {topo}

        {/* 幕僚工作日志：step_log 逐条滚动，进行行尾光标闪烁 */}
        <div ref={logRef} className="mt-5 rounded-lg bg-surface-1 border border-surface-3 p-3 max-h-40 overflow-y-auto">
          <p className="text-[10px] tracking-[0.3em] text-muted mb-2">幕僚工作日志</p>
          {stepLog.length === 0 && <p className="text-xs text-muted font-kai">等待第一条回报…</p>}
          {stepLog.map((e, i) => {
            const officer = NODES.find(o => o.key === e.step)
            return (
              <p key={i} className={`text-xs leading-6 ${MOTION.rise}`}>
                <span className="font-mono text-muted">{fmtClock(e.started_at)}</span>
                {' '}
                <span className={`font-kai ${e.status === 'error' ? 'text-accent-red' : 'text-text'}`}>
                  {officer?.name || e.step}
                </span>
                {' '}
                <span className={e.status === 'error' ? 'text-accent-red' : 'text-muted'}>{e.message}</span>
                {e.status === 'running' && (
                  <span className={`inline-block w-1.5 h-3 bg-accent-cyan ml-1 align-middle ${MOTION.caret}`} aria-hidden="true" />
                )}
              </p>
            )
          })}
        </div>

        {error && (
          <div className="mt-5 p-3 bg-accent-red/16 border border-accent-red/50 rounded-lg">
            <p className="text-sm text-accent-red">核阅中断：{error}</p>
          </div>
        )}
      </div>
    </div>
  )
}
