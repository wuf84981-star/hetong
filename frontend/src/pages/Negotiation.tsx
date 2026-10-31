import { useState, useEffect } from 'react'
import { api } from '../api/client'
import LoadingSpinner from '../components/LoadingSpinner'
import StatusBadge from '../components/StatusBadge'

const STATUS_MAP: Record<string, { label: string; variant: 'error' | 'warning' | 'info' | 'success' }> = {
  active: { label: '进行中', variant: 'info' },
  completed: { label: '已完成', variant: 'success' },
  rejected: { label: '已拒绝', variant: 'error' },
}

const DECISION_MAP: Record<string, { label: string; variant: 'error' | 'warning' | 'info' | 'success' }> = {
  approve: { label: '批准', variant: 'success' },
  reject: { label: '驳回', variant: 'error' },
  modify: { label: '修改', variant: 'warning' },
}

export default function Negotiation() {
  const [sessions, setSessions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState<any>(null)
  const [selectedSession, setSelectedSession] = useState<any>(null)
  const [showFeedbackModal, setShowFeedbackModal] = useState(false)
  const [feedbackForm, setFeedbackForm] = useState({
    reviewer: '',
    decision: 'approve',
    comments: '',
  })

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      const [statsData, sessionsData] = await Promise.all([
        api.getNegotiationStats(),
        api.listNegotiations(),
      ])
      setStats(statsData)
      setSessions(sessionsData.sessions || [])
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleFeedback = async () => {
    if (!selectedSession) return
    try {
      await api.submitNegotiationFeedback(selectedSession.session_id, {
        reviewer: feedbackForm.reviewer,
        decision: feedbackForm.decision,
        comments: feedbackForm.comments,
      })
      setShowFeedbackModal(false)
      setFeedbackForm({ reviewer: '', decision: 'approve', comments: '' })
      // Refresh session data
      const updatedSession = await api.getNegotiation(selectedSession.session_id)
      setSelectedSession(updatedSession)
    } catch (err: any) {
      alert(err.message)
    }
  }

  const handleComplete = async (sessionId: string) => {
    try {
      await api.completeNegotiation(sessionId)
      loadData()
      if (selectedSession?.session_id === sessionId) {
        const updated = await api.getNegotiation(sessionId)
        setSelectedSession(updated)
      }
    } catch (err: any) {
      alert(err.message)
    }
  }

  const handleReject = async (sessionId: string) => {
    const reason = prompt('请输入拒绝原因:')
    if (!reason) return
    try {
      await api.rejectNegotiation(sessionId, reason)
      loadData()
      if (selectedSession?.session_id === sessionId) {
        const updated = await api.getNegotiation(sessionId)
        setSelectedSession(updated)
      }
    } catch (err: any) {
      alert(err.message)
    }
  }

  if (loading) return <LoadingSpinner text="加载协商数据..." />

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-text">协商追踪</h2>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-surface-2 border border-surface-3 rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-accent-cyan">{stats.total_sessions}</div>
            <div className="text-xs text-muted mt-1">总会话数</div>
          </div>
          <div className="bg-surface-2 border border-surface-3 rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-accent-amber">{stats.active_sessions}</div>
            <div className="text-xs text-muted mt-1">进行中</div>
          </div>
          <div className="bg-surface-2 border border-surface-3 rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-accent-green">{stats.completed}</div>
            <div className="text-xs text-muted mt-1">已完成</div>
          </div>
          <div className="bg-surface-2 border border-surface-3 rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-accent-red">{stats.rejected}</div>
            <div className="text-xs text-muted mt-1">已拒绝</div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Session List */}
        <div className="lg:col-span-1">
          <div className="bg-surface-2 border border-surface-3 rounded-xl">
            <div className="p-4 border-b border-surface-3">
              <h3 className="font-semibold text-text">协商会话</h3>
            </div>
            <div className="p-2 max-h-[600px] overflow-y-auto">
              {sessions.length === 0 ? (
                <p className="text-sm text-muted text-center py-8">暂无协商会话</p>
              ) : (
                sessions.map(session => {
                  const status = STATUS_MAP[session.status] || STATUS_MAP.active
                  return (
                    <div
                      key={session.session_id}
                      onClick={() => setSelectedSession(session)}
                      className={`p-3 rounded-lg cursor-pointer mb-2 transition ${
                        selectedSession?.session_id === session.session_id
                          ? 'bg-accent-cyan/10 border border-accent-cyan/30'
                          : 'hover:bg-surface-3 border border-transparent'
                      }`}
                    >
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-text">
                          {session.session_id.slice(0, 12)}...
                        </span>
                        <StatusBadge label={status.label} variant={status.variant} />
                      </div>
                      <p className="text-xs text-muted mt-1">
                        审查: {session.review_id.slice(0, 8)}...
                      </p>
                      <p className="text-xs text-muted">
                        轮次: {session.current_round} | 更新: {new Date(session.updated_at).toLocaleDateString()}
                      </p>
                    </div>
                  )
                })
              )}
            </div>
          </div>
        </div>

        {/* Session Detail */}
        <div className="lg:col-span-2">
          {selectedSession ? (
            <div className="bg-surface-2 border border-surface-3 rounded-xl">
              <div className="p-4 border-b border-surface-3 flex justify-between items-center">
                <h3 className="font-semibold text-text">会话详情</h3>
                <div className="flex gap-2">
                  {selectedSession.status === 'active' && (
                    <>
                      <button
                        onClick={() => setShowFeedbackModal(true)}
                        className="px-3 py-1 bg-accent-cyan text-white rounded text-sm hover:opacity-90"
                      >
                        提交反馈
                      </button>
                      <button
                        onClick={() => handleComplete(selectedSession.session_id)}
                        className="px-3 py-1 bg-accent-green text-white rounded text-sm hover:opacity-90"
                      >
                        完成
                      </button>
                      <button
                        onClick={() => handleReject(selectedSession.session_id)}
                        className="px-3 py-1 bg-accent-red text-white rounded text-sm hover:opacity-90"
                      >
                        拒绝
                      </button>
                    </>
                  )}
                </div>
              </div>
              <div className="p-4">
                <div className="grid grid-cols-2 gap-4 mb-4">
                  <div>
                    <p className="text-xs text-muted">会话ID</p>
                    <p className="text-sm text-text font-mono">{selectedSession.session_id}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted">审查ID</p>
                    <p className="text-sm text-text font-mono">{selectedSession.review_id}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted">状态</p>
                    <StatusBadge
                      label={STATUS_MAP[selectedSession.status]?.label || selectedSession.status}
                      variant={STATUS_MAP[selectedSession.status]?.variant || 'info'}
                    />
                  </div>
                  <div>
                    <p className="text-xs text-muted">当前轮次</p>
                    <p className="text-sm text-text">{selectedSession.current_round}</p>
                  </div>
                </div>

                {/* Feedback History */}
                <h4 className="font-medium text-text mb-3">反馈历史</h4>
                {selectedSession.rounds.length === 0 ? (
                  <p className="text-sm text-muted">暂无反馈记录</p>
                ) : (
                  <div className="space-y-3">
                    {selectedSession.rounds.map((round: any) => {
                      const decision = DECISION_MAP[round.decision] || DECISION_MAP.approve
                      return (
                        <div key={round.round_number} className="p-3 bg-surface-1 rounded-lg border border-surface-3">
                          <div className="flex justify-between items-center mb-2">
                            <span className="text-sm font-medium text-text">
                              第 {round.round_number} 轮
                            </span>
                            <div className="flex items-center gap-2">
                              <StatusBadge label={decision.label} variant={decision.variant} />
                              <span className="text-xs text-muted">
                                {new Date(round.timestamp).toLocaleString()}
                              </span>
                            </div>
                          </div>
                          <p className="text-xs text-muted">审核人: {round.reviewer}</p>
                          {round.comments && (
                            <p className="text-sm text-text mt-1">{round.comments}</p>
                          )}
                          {round.modifications && round.modifications.length > 0 && (
                            <div className="mt-2 space-y-1">
                              {round.modifications.map((mod: any, idx: number) => (
                                <div key={idx} className="text-xs bg-surface-2 rounded p-2">
                                  <span className="text-accent-red line-through">{mod.original_text}</span>
                                  <span className="text-accent-green ml-2">{mod.new_text}</span>
                                  {mod.reason && <span className="text-muted ml-2">({mod.reason})</span>}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="bg-surface-2 border border-surface-3 rounded-xl p-8 text-center">
              <p className="text-muted">选择一个会话查看详情</p>
            </div>
          )}
        </div>
      </div>

      {/* Feedback Modal */}
      {showFeedbackModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-surface-2 border border-surface-3 rounded-xl p-6 w-full max-w-md">
            <h3 className="text-lg font-semibold text-text mb-4">提交反馈</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-muted mb-1">审核人</label>
                <input
                  type="text"
                  value={feedbackForm.reviewer}
                  onChange={e => setFeedbackForm({ ...feedbackForm, reviewer: e.target.value })}
                  className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-sm text-text"
                  placeholder="请输入审核人姓名"
                />
              </div>
              <div>
                <label className="block text-sm text-muted mb-1">决定</label>
                <select
                  value={feedbackForm.decision}
                  onChange={e => setFeedbackForm({ ...feedbackForm, decision: e.target.value })}
                  className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-sm text-text"
                >
                  <option value="approve">批准</option>
                  <option value="reject">驳回</option>
                  <option value="modify">修改</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-muted mb-1">意见</label>
                <textarea
                  value={feedbackForm.comments}
                  onChange={e => setFeedbackForm({ ...feedbackForm, comments: e.target.value })}
                  className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-sm text-text h-24"
                  placeholder="请输入审核意见"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => setShowFeedbackModal(false)}
                className="px-4 py-2 bg-surface-3 text-text rounded-lg text-sm hover:bg-surface-4"
              >
                取消
              </button>
              <button
                onClick={handleFeedback}
                disabled={!feedbackForm.reviewer}
                className="px-4 py-2 bg-accent-cyan text-white rounded-lg text-sm hover:opacity-90 disabled:opacity-50"
              >
                提交
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}