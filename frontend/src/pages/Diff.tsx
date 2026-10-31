import { useState } from 'react'
import type { ReactNode } from 'react'
import { api } from '../api/client'
import LoadingSpinner from '../components/LoadingSpinner'
import type { DiffItem, DiffResult } from '../types'

/** 把【】标记段渲染成删除线朱字（改前）或着重青绿字（改后） */
function renderMarked(text: string, side: 'old' | 'new'): ReactNode[] {
  const out: ReactNode[] = []
  const re = /【([^】]*)】/g
  let last = 0
  let m: RegExpExecArray | null
  let i = 0
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index))
    out.push(
      side === 'old' ? (
        <span key={i++} className="text-accent-red bg-accent-red/10 line-through decoration-accent-red/70">
          {m[1]}
        </span>
      ) : (
        <span key={i++} className="text-accent-green bg-accent-green/10 border-b-2 border-accent-green/70 font-semibold">
          {m[1]}
        </span>
      ),
    )
    last = m.index + m[0].length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

type Block =
  | { kind: 'calm'; text: string }
  | { kind: 'removed'; text: string }
  | { kind: 'added'; text: string }
  | { kind: 'changed'; old: string; new: string }

/** 连续的未变段合并成平静的正文，改动段各自成块突出 */
function toBlocks(items: DiffItem[]): Block[] {
  const blocks: Block[] = []
  for (const it of items) {
    if (it.type === 'unchanged') {
      const last = blocks[blocks.length - 1]
      if (last && last.kind === 'calm') last.text += it.content
      else blocks.push({ kind: 'calm', text: it.content })
    } else if (it.type === 'removed') {
      blocks.push({ kind: 'removed', text: it.old_value || it.content })
    } else if (it.type === 'added') {
      blocks.push({ kind: 'added', text: it.new_value || it.content })
    } else {
      blocks.push({ kind: 'changed', old: it.old_value || '', new: it.new_value || '' })
    }
  }
  return blocks
}

export default function Diff() {
  const [oldText, setOldText] = useState('')
  const [newText, setNewText] = useState('')
  const [result, setResult] = useState<DiffResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleCompare = async () => {
    if (!oldText.trim() || !newText.trim()) return
    setLoading(true)
    setError('')
    try {
      setResult(await api.compareDiff(oldText, newText))
    } catch (err: any) {
      setError(err.message || '对比失败，请稍后再试')
    } finally {
      setLoading(false)
    }
  }

  const stats = result ? [
    { v: result.added, label: '新增段', cls: 'text-accent-green' },
    { v: result.removed, label: '删除段', cls: 'text-accent-red' },
    { v: result.changed, label: '改动处', cls: 'text-accent-amber' },
    { v: result.unchanged, label: '未变段', cls: 'text-muted' },
  ] : []

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-display text-2xl font-semibold text-text">版本对比</h2>
        <p className="text-sm text-muted font-kai mt-1">把两版合同文本分别贴进来，改动逐段为您标出——删掉的划朱，新增的着青</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-surface-2 border border-surface-3 rounded-xl">
          <div className="px-4 py-3 border-b border-surface-3">
            <h3 className="font-display font-semibold text-text">改前文本</h3>
          </div>
          <div className="p-4">
            <textarea
              value={oldText}
              onChange={e => setOldText(e.target.value)}
              className="w-full h-64 bg-surface-1 border border-surface-3 rounded-lg p-3 text-sm font-mono text-text placeholder:text-muted resize-none focus:outline-none focus:border-accent-cyan"
              placeholder="粘贴上一版合同内容..."
            />
          </div>
        </div>

        <div className="bg-surface-2 border border-surface-3 rounded-xl">
          <div className="px-4 py-3 border-b border-surface-3">
            <h3 className="font-display font-semibold text-text">改后文本</h3>
          </div>
          <div className="p-4">
            <textarea
              value={newText}
              onChange={e => setNewText(e.target.value)}
              className="w-full h-64 bg-surface-1 border border-surface-3 rounded-lg p-3 text-sm font-mono text-text placeholder:text-muted resize-none focus:outline-none focus:border-accent-cyan"
              placeholder="粘贴这一版合同内容..."
            />
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-accent-red/10 border border-accent-red/30 rounded-xl px-4 py-3 text-sm text-accent-red">
          {error}
        </div>
      )}

      <div className="text-center">
        <button
          onClick={handleCompare}
          disabled={!oldText.trim() || !newText.trim() || loading}
          className="px-6 py-2 bg-accent-cyan text-white rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 transition"
        >
          {loading ? '比对中...' : '开始比对'}
        </button>
      </div>

      {loading && <LoadingSpinner text="正在比对..." />}

      {result && !loading && (
        <div className="space-y-4">
          {/* 改动账目 */}
          <div className="bg-surface-2 border border-surface-3 rounded-xl px-4 py-3 flex items-center gap-6 flex-wrap">
            {stats.map(s => (
              <div key={s.label} className="flex items-baseline gap-1.5">
                <span className={`font-mono text-xl font-bold ${s.cls}`}>{s.v}</span>
                <span className="text-xs font-kai text-muted">{s.label}</span>
              </div>
            ))}
            <p className="text-xs text-muted font-kai ml-auto">{result.summary}</p>
          </div>

          {/* 校勘纸面 */}
          <div className="paper-card rounded-xl p-6 space-y-4 max-h-[70vh] overflow-y-auto">
            {toBlocks(result.items).map((b, i) => {
              if (b.kind === 'calm') {
                return (
                  <p key={i} className="font-display text-[15px] leading-7 text-paper-ink/65">
                    {b.text}
                  </p>
                )
              }
              if (b.kind === 'removed') {
                return (
                  <p key={i} className="font-display text-[15px] leading-7 border-l-[3px] border-accent-red bg-accent-red/5 px-4 py-2">
                    <span className="text-[10px] tracking-[0.25em] text-accent-red mr-2 align-middle">删</span>
                    {renderMarked(b.text, 'old')}
                  </p>
                )
              }
              if (b.kind === 'added') {
                return (
                  <p key={i} className="font-display text-[15px] leading-7 border-l-[3px] border-accent-green bg-accent-green/5 px-4 py-2">
                    <span className="text-[10px] tracking-[0.25em] text-accent-green mr-2 align-middle">增</span>
                    {renderMarked(b.text, 'new')}
                  </p>
                )
              }
              return (
                <div key={i} className="border-l-[3px] border-accent-amber bg-accent-amber/5 px-4 py-3">
                  <p className="text-[10px] tracking-[0.25em] text-accent-amber mb-2">改</p>
                  <div className="grid md:grid-cols-2 gap-2">
                    <div className="rounded-lg bg-accent-red/5 border border-accent-red/20 p-2.5">
                      <p className="text-[10px] tracking-[0.25em] text-accent-red/80 mb-1">改 前</p>
                      <p className="font-display text-sm leading-6 text-paper-ink">{renderMarked(b.old, 'old')}</p>
                    </div>
                    <div className="rounded-lg bg-accent-green/5 border border-accent-green/20 p-2.5">
                      <p className="text-[10px] tracking-[0.25em] text-accent-green/90 mb-1">改 后</p>
                      <p className="font-display text-sm leading-6 text-paper-ink">{renderMarked(b.new, 'new')}</p>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
