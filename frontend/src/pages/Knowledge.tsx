import { useRef, useState } from 'react'
import { Library, Upload, ClipboardPaste, Trash2 } from 'lucide-react'
import { api } from '../api/client'
import { useApi } from '../hooks/useApi'
import { useAuth } from '../hooks/useAuth'
import { requireLogin } from '../lib/loginGate'
import LoadingSpinner from '../components/LoadingSpinner'
import StatusBadge from '../components/StatusBadge'
import { MOTION } from '../lib/motion'
import type { KnowledgeWriteResult } from '../types'

const CATEGORY_MAP: Record<string, string> = {
  civil: '民事',
  labor: '劳动',
  commercial: '商事',
  other: '其他',
}

export default function Knowledge() {
  const { isAuthenticated, role } = useAuth()
  // 知识库接口：列表 admin/reviewer，入库/粘贴/删除仅 admin（全局共享语料，写权限管理员收口）；客户端预判角色，不发注定 401/403 的请求
  const canView = isAuthenticated && (role === 'admin' || role === 'reviewer')
  const canWrite = isAuthenticated && role === 'admin'
  const { data, loading, refetch, error } = useApi(
    () => (canView ? api.listKnowledge() : Promise.resolve(null)),
    [canView],
  )
  const [uploading, setUploading] = useState(false)
  const [lastResult, setLastResult] = useState<KnowledgeWriteResult | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const [fileCategory, setFileCategory] = useState('civil')
  const [fileTitle, setFileTitle] = useState('')
  const [textForm, setTextForm] = useState({ title: '', category: 'civil', content: '' })

  const st = data?.status

  const runWrite = async (fn: () => Promise<KnowledgeWriteResult>) => {
    setUploading(true)
    setLastResult(null)
    try {
      const r = await fn()
      setLastResult(r)
      refetch()
    } catch (err: any) {
      alert(err.message)
    } finally {
      setUploading(false)
    }
  }

  const handleUpload = () => {
    const file = fileRef.current?.files?.[0]
    if (!file) { alert('请先选择文件'); return }
    void runWrite(() => api.uploadKnowledgeDoc(file, fileCategory, fileTitle))
      .then(() => { if (fileRef.current) fileRef.current.value = '' })
  }

  const handlePaste = () => {
    if (!textForm.title.trim() || !textForm.content.trim()) { alert('标题与条文内容都不能为空'); return }
    void runWrite(() => api.createKnowledgeText(textForm.title, textForm.category, textForm.content))
      .then(() => setTextForm({ title: '', category: textForm.category, content: '' }))
  }

  const handleDelete = async (docId: string, title: string) => {
    if (!confirm(`确定从知识库移除《${title}》？已入库向量将退出检索（物理索引不回收）。`)) return
    try {
      await api.deleteKnowledgeDoc(docId)
      refetch()
    } catch (err: any) { alert(err.message) }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-text">知识库</h2>
        <p className="text-sm text-muted mt-1">上传法规条例或粘贴条文，向量化后供审查检索；批注将透出「检索参考」引用</p>
      </div>

      {!isAuthenticated ? (
        /* 访客：页内引导卡，不弹层 */
        <div className={`bg-surface-2 border border-accent-cyan/45 rounded-xl p-12 text-center ${MOTION.develop}`}>
          <Library className="w-10 h-10 text-accent-cyan/70 mx-auto mb-3" />
          <p className="font-display text-xl font-semibold text-text">知识库需署名调阅</p>
          <p className="text-sm text-muted font-kai mt-2">法规入库由管理员执行，审查员可查库；登录即可查看向量状态与已入库清单。</p>
          <button
            onClick={() => requireLogin()}
            className="mt-4 px-5 py-2 bg-accent-cyan text-white rounded-lg text-sm font-medium hover:opacity-90 transition-[color,background-color,opacity] duration-300"
          >
            登录入库
          </button>
        </div>
      ) : !canView ? (
        /* 查看者：403 区分文案，不弹层 */
        <div className="bg-surface-2 border border-accent-amber/50 rounded-xl p-12 text-center">
          <p className="font-display text-xl font-semibold text-text">当前角色为查看者</p>
          <p className="text-sm text-muted font-kai mt-2">知识库仅向管理员与审查员开放；审查卷宗中的「检索参考」不受影响，照常可见。</p>
        </div>
      ) : (
        <>
          {error && !loading && (
            <div className="bg-accent-red/16 border border-accent-red/50 rounded-xl p-4 text-accent-red text-sm">{error}</div>
          )}

          {st && (
            <div className="grid grid-cols-4 gap-4">
              {[
                {
                  value: st.ready ? '已就绪' : '未就绪',
                  label: '检索引擎',
                  color: st.ready ? 'text-accent-green' : st.model_mismatch ? 'text-accent-red' : 'text-accent-amber',
                },
                { value: st.active_chunks, label: '活跃向量块', color: 'text-text' },
                { value: st.doc_count, label: '已入库文档', color: 'text-text' },
                { value: st.embedding_model.split('/').pop() || st.embedding_model, label: '嵌入模型', color: 'text-text' },
              ].map(({ value, label, color }) => (
                <div key={label} className={`bg-surface-2 border border-surface-3 rounded-xl p-4 text-center hover:border-accent-cyan/50 ${MOTION.lift}`}>
                  <div className={`text-xl font-bold ${color} truncate`}>{value}</div>
                  <div className="text-xs text-muted mt-1">{label}</div>
                </div>
              ))}
              {st.reason && (
                <div className="col-span-4 bg-accent-amber/10 border border-accent-amber/40 rounded-xl px-4 py-2.5 text-sm text-accent-amber">
                  {st.reason}
                  {st.total_chunks > st.active_chunks && ` （已软删 ${st.total_chunks - st.active_chunks} 块不再参与检索）`}
                </div>
              )}
            </div>
          )}

          {/* 入库操作：文件上传 + 粘贴条文（仅 admin 可写） */}
          {canWrite && (
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-surface-2 border border-surface-3 rounded-xl p-5">
              <h3 className="font-semibold text-text mb-3 flex items-center gap-2">
                <Upload className="w-4 h-4 text-accent-cyan" />上传法规文档
              </h3>
              <label className="block border-2 border-dashed border-surface-4 rounded-xl p-6 text-center cursor-pointer hover:border-accent-cyan/60 transition-colors duration-300">
                <input
                  ref={fileRef}
                  type="file"
                  accept=".pdf,.docx,.doc,.txt"
                  className="hidden"
                  disabled={uploading}
                />
                <p className="text-sm text-muted">点击选择 .pdf / .docx / .doc / .txt（≤20MB）</p>
              </label>
              <div className="grid grid-cols-2 gap-3 mt-3">
                <select value={fileCategory} onChange={e => setFileCategory(e.target.value)}
                  className="px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-sm text-text">
                  {Object.entries(CATEGORY_MAP).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
                <input placeholder="文档名（留空取文件名）" value={fileTitle} onChange={e => setFileTitle(e.target.value)}
                  className="px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-sm text-text placeholder:text-muted" />
              </div>
              <button onClick={handleUpload} disabled={uploading}
                className="mt-3 w-full px-4 py-2 bg-accent-cyan text-white rounded-lg text-sm hover:opacity-90 disabled:opacity-50 disabled:cursor-wait transition-[color,background-color,opacity] duration-300">
                {uploading ? '正在嵌入索引，请稍候…' : '解析并入库'}
              </button>
            </div>

            <div className="bg-surface-2 border border-surface-3 rounded-xl p-5">
              <h3 className="font-semibold text-text mb-3 flex items-center gap-2">
                <ClipboardPaste className="w-4 h-4 text-accent-cyan" />粘贴条文
              </h3>
              <div className="grid grid-cols-2 gap-3">
                <input placeholder="名称，如 民法典·合同编" value={textForm.title}
                  onChange={e => setTextForm({ ...textForm, title: e.target.value })}
                  className="px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-sm text-text placeholder:text-muted" />
                <select value={textForm.category} onChange={e => setTextForm({ ...textForm, category: e.target.value })}
                  className="px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-sm text-text">
                  {Object.entries(CATEGORY_MAP).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
              <textarea rows={5} placeholder="粘贴法条原文，按「第X条 / 一、 / 1.」自动分块…" value={textForm.content}
                onChange={e => setTextForm({ ...textForm, content: e.target.value })}
                className="mt-3 w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-sm text-text placeholder:text-muted resize-y" />
              <button onClick={handlePaste} disabled={uploading}
                className="mt-3 w-full px-4 py-2 bg-accent-cyan text-white rounded-lg text-sm hover:opacity-90 disabled:opacity-50 disabled:cursor-wait transition-[color,background-color,opacity] duration-300">
                {uploading ? '正在嵌入索引，请稍候…' : '切块并入库'}
              </button>
            </div>
          </div>
          )}

          {lastResult && (
            <div className="bg-accent-green/10 border border-accent-green/40 rounded-xl px-4 py-2.5 text-sm text-accent-green">
              入库成功：{lastResult.chunk_count} 块已建索引{lastResult.rag.ready ? '，审查检索即时生效' : `，但检索器未就绪（${lastResult.rag.reason || '未知原因'}）`}
            </div>
          )}

          {/* 文档清单 */}
          {loading ? <LoadingSpinner /> : (
            <div className="bg-surface-2 border border-surface-3 rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-surface-1 border-b border-surface-3">
                  <tr>
                    <th className="px-4 py-3 text-left text-muted">文档</th>
                    <th className="px-4 py-3 text-left text-muted">类别</th>
                    <th className="px-4 py-3 text-center text-muted">块数</th>
                    <th className="px-4 py-3 text-left text-muted">来源</th>
                    <th className="px-4 py-3 text-left text-muted">上传人</th>
                    <th className="px-4 py-3 text-left text-muted">时间</th>
                    <th className="px-4 py-3 text-right text-muted">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {data?.docs?.length ? data.docs.map(d => (
                    <tr key={d.doc_id} className={`sweep-band border-b border-surface-3 hover:bg-surface-1 transition-colors duration-300 ${MOTION.sweep}`}>
                      <td className="px-4 py-3 text-text">{d.title}</td>
                      <td className="px-4 py-3"><StatusBadge label={CATEGORY_MAP[d.category] || d.category} variant="info" /></td>
                      <td className="px-4 py-3 text-center font-mono text-xs text-text">{d.chunk_count}</td>
                      <td className="px-4 py-3 text-muted text-xs">{d.source_type === 'upload' ? d.filename || '文件' : '粘贴条文'}</td>
                      <td className="px-4 py-3 text-muted text-xs">{d.uploaded_by || '—'}</td>
                      <td className="px-4 py-3 text-muted text-xs">{d.uploaded_at ? d.uploaded_at.replace('T', ' ').slice(0, 16) : '—'}</td>
                      <td className="px-4 py-3 text-right">
                        {canWrite && (
                        <button onClick={() => handleDelete(d.doc_id, d.title)} disabled={uploading}
                          className="inline-flex items-center gap-1 text-accent-red hover:opacity-80 text-xs disabled:opacity-50">
                          <Trash2 className="w-3.5 h-3.5" />移除
                        </button>
                        )}
                      </td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan={7} className="px-4 py-10 text-center text-muted text-sm">
                        知识库为空——上传一部法规或粘贴一组条文，审查批注即可获得可审计的「检索参考」
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}
