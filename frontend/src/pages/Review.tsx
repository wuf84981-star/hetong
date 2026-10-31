import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { requireLogin } from '../lib/loginGate'
import LoadingSpinner from '../components/LoadingSpinner'
import PipelineGraph from '../components/PipelineGraph'
import type { DetailedReview, ReviewPosition, StepEvent } from '../types'

const POSITIONS: { key: ReviewPosition; label: string; hint: string }[] = [
  { key: 'buyer', label: '买方（甲方）', hint: '站在买方立场，重点找对买方不利之处，建议修改向我方倾斜' },
  { key: 'seller', label: '卖方（乙方）', hint: '站在卖方立场，重点找对卖方不利之处，建议修改向我方倾斜' },
  { key: 'neutral', label: '中立', hint: '兼顾双方，公允评估' },
]

const TERMINAL_STATUSES = new Set(['completed', 'approved', 'rejected', 'awaiting_human'])

export default function Review() {
  const [text, setText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [trackingId, setTrackingId] = useState<string | null>(null)
  const [stepLog, setStepLog] = useState<StepEvent[]>([])
  const [currentStep, setCurrentStep] = useState('')
  const [progress, setProgress] = useState(0)
  const [pollError, setPollError] = useState('')
  const [mode, setMode] = useState<'text' | 'file' | 'batch'>('text')
  const [position, setPosition] = useState<ReviewPosition>('neutral')
  const [files, setFiles] = useState<File[]>([])
  const [batchResult, setBatchResult] = useState<string>('')
  const fileRef = useRef<HTMLInputElement>(null)
  const batchRef = useRef<HTMLInputElement>(null)
  const pollTimer = useRef<number | null>(null)
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    const state = location.state as { text?: string; file?: File } | null
    if (state?.text) {
      setText(state.text)
      setMode('text')
    } else if (state?.file) {
      // 案头拖拽上传直接带到文件页，等用户确认后再开审
      setFiles([state.file])
      setMode('file')
    }
  }, [location.state])

  const stopPolling = useCallback(() => {
    if (pollTimer.current !== null) {
      window.clearTimeout(pollTimer.current)
      pollTimer.current = null
    }
  }, [])

  useEffect(() => () => stopPolling(), [stopPolling])

  const poll = useCallback((id: string) => {
    const tick = async () => {
      try {
        const data: DetailedReview = await api.getReview(id)
        setStepLog(data.step_log || [])
        setCurrentStep(data.current_step || '')
        setProgress(data.progress || 0)

        if (data.errors && data.errors.length > 0 && TERMINAL_STATUSES.has(data.status) === false && data.current_step === '') {
          const lastErr = data.step_log?.slice().reverse().find(e => e.status === 'error')
          if (lastErr) {
            setPollError(lastErr.message || data.errors[0])
            return
          }
        }

        if (TERMINAL_STATUSES.has(data.status)) {
          stopPolling()
          navigate(`/review/${id}`)
          return
        }
      } catch (err: any) {
        // 瞬态失败（429 限流 / 5xx / 网络抖动）：退避 2 秒继续轮询，不放弃跟踪
        if (err instanceof ApiError && (err.status === 429 || err.status >= 500)) {
          pollTimer.current = window.setTimeout(() => tick(), 2000)
          return
        }
        setPollError(err.message || '轮询失败')
        stopPolling()
        return
      }
      pollTimer.current = window.setTimeout(() => tick(), 1000)
    }
    tick()
  }, [navigate, stopPolling])

  const startTracking = useCallback((reviewId: string) => {
    setTrackingId(reviewId)
    setStepLog([])
    setCurrentStep('')
    setProgress(0)
    setPollError('')
    poll(reviewId)
  }, [poll])

  const handleCancel = () => {
    stopPolling()
    setTrackingId(null)
    setSubmitting(false)
  }

  // 递交门：访客先触发登录弹层，登录成功后自动续做（弹层遮罩挡住页面，表单值不会失真）
  const doSubmitText = async () => {
    if (!text.trim()) return
    setSubmitting(true)
    setPollError('')
    try {
      const result = await api.createReview(text, true, position)
      startTracking(result.review_id)
    } catch (err: any) {
      setPollError(err.message)
      setSubmitting(false)
    }
  }
  const handleSubmitText = () => requireLogin(doSubmitText)

  const doSubmitFile = async () => {
    if (mode === 'batch') {
      if (files.length === 0) return
      setSubmitting(true)
      setPollError('')
      try {
        const result = await api.batchReview(files, true, position)
        setBatchResult(`批量审查完成：${result.completed}/${result.total} 成功${result.failed > 0 ? `，${result.failed} 个失败` : ''}`)
      } catch (err: any) {
        setPollError(err.message)
      } finally {
        setSubmitting(false)
        setFiles([])
        if (batchRef.current) batchRef.current.value = ''
      }
      return
    }

    if (files.length === 0) return
    setSubmitting(true)
    setPollError('')
    try {
      const result = await api.uploadReview(files[0], true, position)
      startTracking(result.review_id)
    } catch (err: any) {
      setPollError(err.message)
      setSubmitting(false)
    } finally {
      setFiles([])
      if (fileRef.current) fileRef.current.value = ''
    }
  }
  const handleSubmitFile = () => requireLogin(doSubmitFile)

  if (trackingId) {
    return (
      <div className="space-y-6">
        <h2 className="text-2xl font-bold text-text">合同审查</h2>
        <PipelineGraph
          mode="run"
          stepLog={stepLog}
          currentStep={currentStep}
          progress={progress}
          error={pollError}
        />
        <div className="text-center">
          <button
            onClick={handleCancel}
            className="text-sm text-muted hover:text-text transition-colors duration-300"
          >
            取消并返回
          </button>
        </div>
      </div>
    )
  }

  if (submitting && !trackingId) {
    return <LoadingSpinner text="提交审查任务..." />
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-text">合同审查</h2>

      {batchResult && (
        <div className="bg-accent-green/16 border border-accent-green/50 rounded-xl p-4 flex items-center justify-between">
          <p className="text-sm text-accent-green">{batchResult}</p>
          <button onClick={() => setBatchResult('')} className="text-xs text-muted hover:text-text">关闭</button>
        </div>
      )}

      {/* Mode tabs */}
      <div className="flex gap-2">
        {[
          { key: 'text', label: '文本输入' },
          { key: 'file', label: '文件上传' },
          { key: 'batch', label: '批量上传' },
        ].map(m => (
          <button
            key={m.key}
            onClick={() => { setMode(m.key as 'text' | 'file' | 'batch'); setFiles([]); setBatchResult('') }}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-[color,background-color,border-color] duration-300 ${
              mode === m.key ? 'bg-accent-cyan text-white' : 'bg-surface-2 border border-surface-3 text-muted hover:text-text'
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* 审查立场：幕僚按此立场衡量利害 */}
      <div className="paper-card rounded-xl px-5 py-4 flex items-center gap-3 flex-wrap">
        <span className="text-[10px] tracking-[0.25em] text-muted font-kai">审查立场</span>
        {POSITIONS.map(p => (
          <button
            key={p.key}
            onClick={() => setPosition(p.key)}
            title={p.hint}
            className={`px-3.5 py-1.5 rounded-lg text-sm border transition-[color,background-color,border-color] duration-300 ${
              position === p.key
                ? 'border-accent-cyan/50 bg-accent-cyan/16 text-accent-cyan font-medium'
                : 'border-surface-3 bg-surface-2 text-muted hover:text-text'
            }`}
          >
            {p.label}
          </button>
        ))}
        <span className="text-xs text-muted font-kai ml-auto hidden sm:block">
          {POSITIONS.find(p => p.key === position)?.hint}
        </span>
      </div>

      {mode === 'text' && (
        <div className="bg-surface-2 border border-surface-3 rounded-xl p-6">
          <textarea
            className="w-full h-64 bg-surface-1 border border-surface-3 rounded-lg p-4 text-sm font-mono text-text placeholder:text-muted resize-none focus:outline-none focus:border-accent-cyan"
            placeholder="请粘贴合同文本内容..."
            value={text}
            onChange={e => setText(e.target.value)}
          />
          <div className="mt-4 flex items-center justify-between">
            <span className="text-xs text-muted">{text.length} 字符</span>
            <button
              onClick={handleSubmitText}
              disabled={!text.trim()}
              className="px-6 py-2 bg-accent-cyan text-white rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-[color,background-color,opacity] duration-300"
            >
              开始审查
            </button>
          </div>
        </div>
      )}

      {mode === 'file' && (
        <div className="bg-surface-2 border border-surface-3 rounded-xl p-6">
          <div className="border-2 border-dashed border-surface-4 rounded-lg p-8 text-center hover:border-accent-cyan transition-colors duration-300">
            <input ref={fileRef} type="file" accept=".pdf,.docx,.doc,.txt"
              onChange={e => setFiles(Array.from(e.target.files || []))} className="hidden" />
            <button onClick={() => fileRef.current?.click()} className="text-accent-cyan hover:underline text-sm">
              选择文件
            </button>
            <p className="text-xs text-muted mt-2">支持 PDF、DOCX、TXT 格式</p>
            {files.length > 0 && (
              <p className="text-xs text-accent-green mt-2">已选择：{files.map(f => f.name).join(', ')}</p>
            )}
          </div>
          <div className="mt-4 flex justify-end">
            <button onClick={handleSubmitFile} disabled={files.length === 0}
              className="px-6 py-2 bg-accent-cyan text-white rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-[color,background-color,opacity] duration-300">
              上传并审查
            </button>
          </div>
        </div>
      )}

      {mode === 'batch' && (
        <div className="bg-surface-2 border border-surface-3 rounded-xl p-6">
          <div className="border-2 border-dashed border-surface-4 rounded-lg p-8 text-center hover:border-accent-cyan transition-colors duration-300">
            <input ref={batchRef} type="file" accept=".pdf,.docx,.doc,.txt" multiple
              onChange={e => setFiles(Array.from(e.target.files || []))} className="hidden" />
            <button onClick={() => batchRef.current?.click()} className="text-accent-cyan hover:underline text-sm">
              选择多个文件
            </button>
            <p className="text-xs text-muted mt-2">最多 10 个文件，支持 PDF/DOCX/TXT</p>
            {files.length > 0 && (
              <p className="text-xs text-accent-green mt-2">已选择 {files.length} 个文件</p>
            )}
          </div>
          <div className="mt-4 flex justify-end">
            <button onClick={handleSubmitFile} disabled={files.length === 0}
              className="px-6 py-2 bg-accent-cyan text-white rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-[color,background-color,opacity] duration-300">
              批量审查 ({files.length} 个文件)
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
