import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Activity, ArrowRight, Archive, BookOpen, Brain, Crosshair, FileCheck, FileUp,
  GitCompare, Hourglass, MessageSquare, Moon, PenLine, Scale, ScanText, ScrollText,
  Sun, ThumbsUp, UserCheck,
} from 'lucide-react'
import { usePolling } from '../hooks/useApi'
import { useTheme } from '../hooks/useTheme'
import { useAuth } from '../hooks/useAuth'
import { api } from '../api/client'
import PipelineGraph from '../components/PipelineGraph'
import type { NodeKey } from '../components/PipelineGraph'
import { MOTION } from '../lib/motion'

/**
 * 产品落地页：/ 全屏顶层路由（Layout 外），免登录可逛。
 * 承担"初次进来就知道系统怎么运作、每个界面干什么"的导览职能；
 * 只请求公开接口（metrics），一切需署名的入口交给页内引导卡承接——本页禁用 requireLogin。
 */

const NAV = [
  { href: '#pipeline', label: '幕僚编排' },
  { href: '#officers', label: '四位幕僚' },
  { href: '#engines', label: '双引擎对照' },
  { href: '#human', label: '人工把关' },
  { href: '#usage', label: '四步上手' },
  { href: '#archive', label: '存档流转' },
]

const OFFICERS: { key: NodeKey; num: string; icon: typeof ScanText; name: string; en: string; duty: string; depend: string }[] = [
  {
    key: 'clause_extraction', num: '01', icon: ScanText, name: '条款拆解官', en: 'CLAUSE SEGMENTER',
    duty: '把非结构化的合同正文切成带类型标签的条款单元，保留原文字符偏移，后续所有结论都能回溯定位到原句。',
    depend: '串行前置 · 后面三位都等它的结果',
  },
  {
    key: 'risk_identification', num: '02', icon: Crosshair, name: '风险猎手', en: 'RISK IDENTIFIER',
    duty: '对每条条款并行执行规则引擎关键词命中与大模型语义判定，产出带严重度的风险候选集。',
    depend: '与合规法官并行 · 互不阻塞',
  },
  {
    key: 'compliance_check', num: '03', icon: Scale, name: '合规法官', en: 'COMPLIANCE CHECKER',
    duty: '以「缺失即风险」的视角通查全文，覆盖争议解决、保密、数据处理、劳动用工等强制性与完备性要求。',
    depend: '与风险猎手并行 · 各自独立取证',
  },
  {
    key: 'suggestion', num: '04', icon: PenLine, name: '修订顾问', en: 'REDRAFT ADVISOR',
    duty: '汇聚两路结论，做一致性归因与就严原则采信；为每条风险生成「原文 → 建议替换」的可执行修订。',
    depend: '汇聚归因 · 两路结论在此合流',
  },
]

const ENGINES = [
  {
    icon: Crosshair, name: '规则引擎命中', cls: 'text-accent-cyan', edge: 'border-l-accent-cyan',
    desc: '静态规则有据可查：每条报警都带规则编号与命中原文，零延迟、可复核。',
    sample: 'R003 · 「违约金为合同总价三倍」→ 高风险',
  },
  {
    icon: Brain, name: '大模型推理', cls: 'text-accent-purple', edge: 'border-l-accent-purple',
    desc: '读上下文找暗坑：权责失衡、条款缺失这类隐性陷阱由语义判定兜住。',
    sample: '「乙方承担全部损失」义务单向倾斜 → 建议设上限',
  },
  {
    icon: Scale, name: '双引擎分歧', cls: 'text-accent-amber', edge: 'border-l-accent-amber',
    desc: '两路结论不一致时不取平均：按就严原则采信，写明理由，升级人工裁断。',
    sample: '规则判严重 · 大模型判中等 → 就严采信，待您裁断',
  },
]

const HUMAN = [
  {
    icon: ThumbsUp, title: '逐条认同 / 存疑',
    desc: '每条批注右下角有点赞与存疑钮——不整体否决，精准表达到哪一条您不同意。',
  },
  {
    icon: UserCheck, title: '三态定夺',
    desc: '同意结论、驳回、部分同意（需修改）——定夺权是人类独有的，系统只建议，绝不擅自放行。',
  },
  {
    icon: Archive, title: '反馈回流',
    desc: '存疑与错判反馈记入 lessons，幕僚按您认可过的口径学习，越用越合您的尺度。',
  },
]

const USAGE = [
  {
    num: '01', icon: FileUp, title: '递卷',
    desc: '粘贴合同文本或上传 PDF / Word（≤20MB），选好立场——买方、卖方或中立；需要人类定夺就保留「人工把关」开关。递交那一刻才要署名。',
    to: '/review', entry: '去递交合同',
  },
  {
    num: '02', icon: Hourglass, title: '会审',
    desc: '四位幕僚沿执行图依次就位：拆解 → 风险 ∥ 合规 → 修订。案头实时显示进度与每步日志，快则十几秒，视合同长度而定。',
    to: '/dashboard', entry: '看看案头',
  },
  {
    num: '03', icon: ScrollText, title: '阅卷',
    desc: '批注本逐条摆出结论与依据——规则编号、大模型推理，乃至命中的法条「检索参考」；用每条下方的认同 / 存疑精确定位分歧，再做三态定夺。',
    to: '/history', entry: '打开一卷',
  },
  {
    num: '04', icon: FileCheck, title: '用印流转',
    desc: '导出 PDF 报告或 Word 红线稿（删句呈朱、增句着青）直接发对方磋商；两版稿件先过版本对比；您的存疑会回流，教幕僚按您的尺度判。',
    to: '/diff', entry: '试试版本对比',
  },
]

const ARCHIVE_SHELVES = [
  { to: '/regulations', icon: BookOpen, name: '法规引用', desc: '内置三部现行法规的关键条文，贴一段条款即匹配相关法条原文', badge: '免登录', gate: false },
  { to: '/diff', icon: GitCompare, name: '版本对比', desc: '前后两稿逐行对照：删句呈朱、增句呈青，一眼看清对方改了什么', badge: '免登录', gate: false },
  { to: '/negotiation', icon: MessageSquare, name: '协商追踪', desc: '修订拉锯多轮留痕，从初稿到定案全程可回放', badge: '免登录', gate: false },
  { to: '/history', icon: Archive, name: '审查归档', desc: '您经办的卷宗与定夺记录，按账号租户隔离', badge: '需署名', gate: true },
]

function SectionHead({ num, en, title, sub }: { num: string; en: string; title: string; sub: string }) {
  return (
    <div>
      <p className="font-mono text-xs tracking-[0.3em] text-accent-cyan">{num} / {en}</p>
      <h2 className="font-display text-3xl font-semibold text-text mt-2 text-balance">{title}</h2>
      <p className="font-kai text-sm text-muted mt-2 max-w-2xl leading-relaxed">{sub}</p>
    </div>
  )
}

export default function Landing() {
  const { isAuthenticated } = useAuth()
  const { theme, toggle } = useTheme()
  // 幕僚卡 hover/聚焦 ↔ 执行图节点高亮联动（受控 selected）
  const [graphSel, setGraphSel] = useState<NodeKey | null>(null)
  // 落地页唯一取数：公开 metrics；零数据或后端未起时整行隐藏
  const { data: metrics } = usePolling(() => api.getMetrics(), 60000)
  const rd = metrics?.risk_distribution
  const rdTotal = rd ? (rd.high ?? 0) + (rd.medium ?? 0) + (rd.low ?? 0) + (rd.none ?? 0) : 0

  return (
    <div className="min-h-screen text-text">
      {/* ── 顶栏 ── */}
      <header className="sticky top-0 z-40 bg-surface-1/70 backdrop-blur border-b border-surface-3">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center gap-4">
          <Link to="/" className="flex items-center gap-2.5 flex-shrink-0">
            <div className="w-8 h-8 rounded-lg bg-accent-cyan/16 border border-accent-cyan/50 flex items-center justify-center">
              <Activity className="w-4 h-4 text-accent-cyan" />
            </div>
            <span className="font-display text-base font-semibold tracking-wide whitespace-nowrap">分寸合同</span>
            <span className="hidden xl:inline font-mono text-[10px] tracking-[0.25em] text-muted">DUAL-ENGINE CONTRACT REVIEW</span>
          </Link>
          <nav className="hidden lg:flex items-center gap-0.5 text-sm">
            {NAV.map(n => (
              <a key={n.href} href={n.href} className="px-2.5 py-1.5 rounded-lg whitespace-nowrap text-muted hover:text-text hover:bg-surface-2/70 transition-[color,background-color] duration-300">
                {n.label}
              </a>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2 flex-shrink-0">
            <button
              onClick={toggle}
              title={theme === 'dark' ? '切换亮色' : '切换暗色'}
              className="p-2 rounded-lg text-muted hover:text-text hover:bg-surface-2 transition-[color,background-color] duration-300"
            >
              {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
            {!isAuthenticated && (
              <Link to="/login?from=%2Fdashboard" className="px-3 py-1.5 text-sm whitespace-nowrap text-muted hover:text-text transition-colors duration-300">
                登录
              </Link>
            )}
            <Link
              to="/dashboard"
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-accent-cyan text-white text-sm font-medium whitespace-nowrap hover:opacity-90 transition-[color,background-color,opacity] duration-300"
            >
              进入工作台 <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>
      </header>

      {/* ── hero ── */}
      <section id="top" className="relative overflow-hidden">
        <div className="absolute inset-0 grid-bg pointer-events-none" aria-hidden="true" />
        <div className="relative max-w-6xl mx-auto px-6 pt-20 pb-12">
          <p className="font-mono text-xs tracking-[0.35em] text-muted">DUAL-ENGINE CONTRACT REVIEW · 规则引擎 × 大模型</p>
          <h1 className={`font-display text-4xl md:text-6xl font-semibold text-text mt-4 leading-tight text-balance ${MOTION.develop}`}>
            合同里的每一处风险，
            <br />
            都要说清是谁判的、凭什么判。
          </h1>
          <p className="font-kai text-muted mt-5 max-w-2xl leading-relaxed">
            条款拆解、风险识别、合规检查、修订建议——四位 AI 幕僚沿有向图串行前置、并行会审、汇聚收尾；
            规则引擎与语义引擎各判一次，结论不一致时按就严原则采信并写明理由；
            大模型超时或不可用时自动降级为仅规则判定，并在报告里如实标注。
          </p>
          <div className="mt-8 flex items-center gap-3 flex-wrap">
            <Link
              to="/review"
              className="flex items-center gap-1.5 px-5 py-2.5 rounded-lg bg-accent-cyan text-white text-sm font-medium hover:opacity-90 transition-[color,background-color,opacity] duration-300"
            >
              开始一次审查 <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              to="/diff"
              className="px-5 py-2.5 rounded-lg border border-accent-cyan/50 text-accent-cyan text-sm font-medium hover:bg-accent-cyan/16 transition-[color,background-color,border-color] duration-300"
            >
              先看双引擎怎么对照
            </Link>
            <a href="#pipeline" className="px-2 py-2 text-sm text-muted hover:text-text transition-colors duration-300">
              幕僚编排细节 ↓
            </a>
          </div>
          {metrics && metrics.review_count > 0 && rdTotal > 0 && rd && (
            <div className="mt-10 flex items-center gap-4 text-xs text-muted font-mono flex-wrap">
              <span>已核阅 {metrics.review_count} 卷</span>
              <span className="w-40 h-1.5 rounded-full bg-surface-3 overflow-hidden flex" aria-hidden="true">
                <span className="bg-accent-red" style={{ width: `${((rd.high ?? 0) / rdTotal) * 100}%` }} />
                <span className="bg-accent-amber" style={{ width: `${((rd.medium ?? 0) / rdTotal) * 100}%` }} />
                <span className="bg-accent-green" style={{ width: `${((rd.low ?? 0) / rdTotal) * 100}%` }} />
              </span>
              <span>高 {rd.high ?? 0} · 中 {rd.medium ?? 0} · 低 {rd.low ?? 0}</span>
            </div>
          )}
        </div>
      </section>

      {/* ── 执行图自动演示 ── */}
      <section id="pipeline" className="max-w-6xl mx-auto px-6 pt-6 scroll-mt-20">
        <div className={`bg-surface-2 border border-surface-3 rounded-xl p-6 ${MOTION.develop}`}>
          <div className="flex items-baseline justify-between flex-wrap gap-2">
            <p className="font-mono text-[10px] tracking-[0.3em] text-muted">EXECUTION GRAPH · 自动演示</p>
            <p className="font-kai text-xs text-muted">条款拆解 → 风险 ∥ 合规 → 修订建议</p>
          </div>
          <p className="font-kai text-xs text-muted mt-1 mb-2">编排不是口号，是一张图：下方悬停任一幕僚卡，图上立刻点亮它的上下游。</p>
          <PipelineGraph mode="struct" bare demo stepLog={[]} selected={graphSel} />
          <div className="mt-2 flex items-center gap-5 text-xs text-muted font-kai">
            <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-surface-4" />待命</span>
            <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-accent-cyan" />运行中</span>
            <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-accent-green" />已完成</span>
          </div>
        </div>
      </section>

      {/* ── 四位幕僚 ── */}
      <section id="officers" className="max-w-6xl mx-auto px-6 pt-16 scroll-mt-20">
        <SectionHead
          num="01" en="HOW IT RUNS"
          title="一条合同如何穿过四位幕僚"
          sub="条款拆解是串行前置，风险识别与合规检查并行执行，修订建议在汇聚点做一致性归因。悬停卡片可在上方执行图中定位该幕僚。"
        />
        <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-4 mt-8">
          {OFFICERS.map((o, i) => (
            <div
              key={o.key}
              tabIndex={0}
              onMouseEnter={() => setGraphSel(o.key)}
              onMouseLeave={() => setGraphSel(null)}
              onFocus={() => setGraphSel(o.key)}
              onBlur={() => setGraphSel(null)}
              style={{ animationDelay: `${i * 90}ms` }}
              className={`bg-surface-2 border border-surface-3 rounded-xl p-5 flex flex-col hover:border-accent-cyan/50 focus-visible:border-accent-cyan/50 ${MOTION.lift} ${MOTION.develop}`}
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs text-accent-cyan">{o.num}</span>
                <o.icon className="w-5 h-5 text-muted" />
              </div>
              <h3 className="font-display text-lg font-semibold text-text mt-3">{o.name}</h3>
              <p className="font-mono text-[10px] tracking-[0.2em] text-muted mt-0.5">{o.en}</p>
              <p className="text-sm text-muted leading-relaxed mt-3 flex-1">{o.duty}</p>
              <p className="text-xs font-kai text-accent-cyan/90 mt-4 pt-3 border-t border-surface-3">{o.depend}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── 双引擎对照 ── */}
      <section id="engines" className="max-w-6xl mx-auto px-6 pt-16 scroll-mt-20">
        <SectionHead
          num="02" en="DUAL ENGINE"
          title="两位判官各判一次，分歧处升级人类"
          sub="规则引擎与大模型独立出结论，每条批注都标明出处；两路不一致的地方不做和稀泥，按就严采信并交您裁断。"
        />
        <div className="grid md:grid-cols-3 gap-4 mt-8">
          {ENGINES.map((e, i) => (
            <div
              key={e.name}
              style={{ animationDelay: `${i * 90}ms` }}
              className={`bg-surface-2 border border-surface-3 rounded-xl p-5 border-l-2 ${e.edge} ${MOTION.lift} ${MOTION.develop}`}
            >
              <e.icon className={`w-5 h-5 ${e.cls}`} />
              <h3 className={`font-display text-lg font-semibold mt-3 ${e.cls}`}>{e.name}</h3>
              <p className="text-sm text-muted leading-relaxed mt-2">{e.desc}</p>
              <p className="font-mono text-[11px] text-muted mt-4 pt-3 border-t border-surface-3 leading-relaxed">{e.sample}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── 人工把关 ── */}
      <section id="human" className="max-w-6xl mx-auto px-6 pt-16 scroll-mt-20">
        <SectionHead
          num="03" en="HUMAN IN THE LOOP"
          title="最后的印章，始终由人类落下"
          sub="幕僚核毕不等于放行：待把关的卷宗会挂在页签提醒您，定夺之后反馈还会回流给系统学习。"
        />
        <div className="grid md:grid-cols-3 gap-4 mt-8">
          {HUMAN.map((h, i) => (
            <div
              key={h.title}
              style={{ animationDelay: `${i * 90}ms` }}
              className={`bg-surface-2 border border-surface-3 rounded-xl p-5 ${MOTION.lift} ${MOTION.develop}`}
            >
              <div className="w-9 h-9 rounded-lg bg-accent-cyan/16 border border-accent-cyan/45 flex items-center justify-center">
                <h.icon className="w-5 h-5 text-accent-cyan" />
              </div>
              <h3 className="font-display text-base font-semibold text-text mt-3">{h.title}</h3>
              <p className="text-sm text-muted leading-relaxed mt-2">{h.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── 四步上手 ── */}
      <section id="usage" className="max-w-6xl mx-auto px-6 pt-16 scroll-mt-20">
        <SectionHead
          num="04" en="GETTING STARTED"
          title="四步，从一份合同到可落印的批注本"
          sub="浏览全程免登录，署名只发生在递卷与定夺的瞬间。每一步都对应工作台侧栏的一个入口，下面直接跳给您看。"
        />
        <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-4 mt-8">
          {USAGE.map((u, i) => (
            <div
              key={u.num}
              style={{ animationDelay: `${i * 90}ms` }}
              className={`bg-surface-2 border border-surface-3 rounded-xl p-5 flex flex-col hover:border-accent-cyan/50 ${MOTION.lift} ${MOTION.develop}`}
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs text-accent-cyan">STEP {u.num}</span>
                <u.icon className="w-5 h-5 text-muted" />
              </div>
              <h3 className="font-display text-lg font-semibold text-text mt-3">{u.title}</h3>
              <p className="text-sm text-muted leading-relaxed mt-2 flex-1">{u.desc}</p>
              <Link
                to={u.to}
                className="mt-4 pt-3 border-t border-surface-3 flex items-center gap-1 text-xs font-kai text-accent-cyan/90 hover:text-accent-cyan transition-colors duration-300"
              >
                {u.entry} <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
          ))}
        </div>
        <p className="font-kai text-xs text-muted mt-4">
          想批注里的「检索参考」更有依据？管理员与审查员可在「知识库」页上传法规条例或粘贴条文，入库即参与后续审查的检索。
        </p>
      </section>

      {/* ── 存档流转 ── */}
      <section id="archive" className="max-w-6xl mx-auto px-6 pt-16 scroll-mt-20">
        <SectionHead
          num="05" en="KNOWLEDGE & ARCHIVE"
          title="法规、模板与卷宗，各归其架"
          sub="法规引用、版本对比、协商追踪不登录即可逛；您经办的卷宗按账号隔离，署名后可查。"
        />
        <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-4 mt-8">
          {ARCHIVE_SHELVES.map((s, i) => (
            <Link
              key={s.to}
              to={s.to}
              style={{ animationDelay: `${i * 90}ms` }}
              className={`bg-surface-2 border border-surface-3 rounded-xl p-5 hover:border-accent-cyan/50 ${MOTION.lift} ${MOTION.develop}`}
            >
              <div className="flex items-center justify-between">
                <s.icon className="w-5 h-5 text-accent-cyan" />
                <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono border ${s.gate ? 'border-accent-amber/50 text-accent-amber' : 'border-accent-green/50 text-accent-green'}`}>
                  {s.badge}
                </span>
              </div>
              <h3 className="font-display text-base font-semibold text-text mt-3">{s.name}</h3>
              <p className="text-sm text-muted leading-relaxed mt-1.5">{s.desc}</p>
            </Link>
          ))}
        </div>
      </section>

      {/* ── 底部 CTA + 页脚 ── */}
      <section className="max-w-6xl mx-auto px-6 pt-20 pb-10 text-center">
        <h2 className="font-display text-3xl md:text-4xl font-semibold text-text text-balance">
          把合同铺到案上，四位幕僚即刻就位
        </h2>
        <p className="font-kai text-muted mt-3">浏览无需登录；递交与定夺时再署名也不迟。</p>
        <div className="mt-6 flex items-center justify-center gap-3 flex-wrap">
          <Link
            to="/review"
            className="flex items-center gap-1.5 px-5 py-2.5 rounded-lg bg-accent-cyan text-white text-sm font-medium hover:opacity-90 transition-[color,background-color,opacity] duration-300"
          >
            开始一次审查 <ArrowRight className="w-4 h-4" />
          </Link>
          <Link
            to="/dashboard"
            className="px-5 py-2.5 rounded-lg border border-accent-cyan/50 text-accent-cyan text-sm font-medium hover:bg-accent-cyan/16 transition-[color,background-color,border-color] duration-300"
          >
            进入工作台
          </Link>
        </div>
        <footer className="mt-16 pt-6 border-t border-surface-3 text-xs text-muted font-kai flex justify-center gap-x-8 gap-y-1.5 flex-wrap">
          <span>自部署 · 按账号租户隔离</span>
          <span>纯规则模式下合同不出网</span>
          <span>AI 仅提出建议，不构成法律意见</span>
        </footer>
      </section>
    </div>
  )
}
