import { useState, useEffect } from 'react'
import { api } from '../api/client'
import LoadingSpinner from '../components/LoadingSpinner'
import StatusBadge from '../components/StatusBadge'

const CATEGORY_MAP: Record<string, { label: string; variant: 'error' | 'warning' | 'info' | 'success' }> = {
  civil: { label: '民法', variant: 'info' },
  labor: { label: '劳动法', variant: 'warning' },
  commercial: { label: '商法', variant: 'success' },
}

export default function Regulations() {
  const [regulations, setRegulations] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [category, setCategory] = useState('')
  const [selectedReg, setSelectedReg] = useState<any>(null)
  const [matchText, setMatchText] = useState('')
  const [matchResults, setMatchResults] = useState<any[]>([])
  const [matching, setMatching] = useState(false)

  useEffect(() => {
    loadRegulations()
  }, [category])

  const loadRegulations = async () => {
    setLoading(true)
    try {
      const data = await api.listRegulations(category || undefined)
      setRegulations(data.regulations || [])
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleMatch = async () => {
    if (!matchText.trim()) return
    setMatching(true)
    try {
      const data = await api.matchRegulations(matchText)
      setMatchResults(data.matches || [])
    } catch (err: any) {
      alert(err.message)
    } finally {
      setMatching(false)
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-text">法规引用</h2>

      {/* Category filter */}
      <div className="flex gap-2">
        {[
          { key: '', label: '全部' },
          { key: 'civil', label: '民法' },
          { key: 'labor', label: '劳动法' },
          { key: 'commercial', label: '商法' },
        ].map(c => (
          <button
            key={c.key}
            onClick={() => setCategory(c.key)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
              category === c.key
                ? 'bg-accent-cyan text-white'
                : 'bg-surface-2 border border-surface-3 text-muted hover:text-text'
            }`}
          >
            {c.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Regulations List */}
        <div className="bg-surface-2 border border-surface-3 rounded-xl">
          <div className="p-4 border-b border-surface-3">
            <h3 className="font-semibold text-text">法规条文</h3>
          </div>
          <div className="p-2 max-h-[600px] overflow-y-auto">
            {loading ? (
              <LoadingSpinner text="加载法规..." />
            ) : regulations.length === 0 ? (
              <p className="text-sm text-muted text-center py-8">暂无法规数据</p>
            ) : (
              regulations.map(reg => {
                const cat = CATEGORY_MAP[reg.category] || CATEGORY_MAP.civil
                return (
                  <div
                    key={reg.id}
                    onClick={() => setSelectedReg(reg)}
                    className={`p-3 rounded-lg cursor-pointer mb-2 transition ${
                      selectedReg?.id === reg.id
                        ? 'bg-accent-cyan/10 border border-accent-cyan/30'
                        : 'hover:bg-surface-3 border border-transparent'
                    }`}
                  >
                    <div className="flex justify-between items-center">
                      <span className="text-sm font-medium text-text">{reg.article}</span>
                      <StatusBadge label={cat.label} variant={cat.variant} />
                    </div>
                    <p className="text-xs text-muted mt-1 line-clamp-2">{reg.description}</p>
                  </div>
                )
              })
            )}
          </div>
        </div>

        {/* Regulation Detail / Match */}
        <div className="space-y-6">
          {/* Detail */}
          {selectedReg && (
            <div className="bg-surface-2 border border-surface-3 rounded-xl">
              <div className="p-4 border-b border-surface-3">
                <h3 className="font-semibold text-text">{selectedReg.name} {selectedReg.article}</h3>
              </div>
              <div className="p-4">
                <p className="text-sm text-text leading-relaxed">{selectedReg.content}</p>
                <div className="mt-4">
                  <p className="text-xs text-muted mb-2">关键词</p>
                  <div className="flex flex-wrap gap-1">
                    {selectedReg.keywords?.map((kw: string, i: number) => (
                      <span key={i} className="px-2 py-1 bg-surface-3 rounded text-xs text-muted">
                        {kw}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Match Tool */}
          <div className="bg-surface-2 border border-surface-3 rounded-xl">
            <div className="p-4 border-b border-surface-3">
              <h3 className="font-semibold text-text">法规匹配</h3>
            </div>
            <div className="p-4">
              <textarea
                value={matchText}
                onChange={e => setMatchText(e.target.value)}
                className="w-full h-32 bg-surface-1 border border-surface-3 rounded-lg p-3 text-sm text-text placeholder:text-muted resize-none"
                placeholder="输入合同文本，匹配相关法规..."
              />
              <button
                onClick={handleMatch}
                disabled={!matchText.trim() || matching}
                className="mt-3 px-4 py-2 bg-accent-cyan text-white rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
              >
                {matching ? '匹配中...' : '匹配法规'}
              </button>

              {matchResults.length > 0 && (
                <div className="mt-4 space-y-2">
                  <p className="text-xs text-muted">匹配到 {matchResults.length} 条相关法规</p>
                  {matchResults.map((match, i) => (
                    <div key={i} className="p-3 bg-surface-1 rounded-lg border border-surface-3">
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-text">
                          {match.regulation_name} {match.article}
                        </span>
                        <span className="text-xs text-accent-cyan">相关度: {match.relevance}%</span>
                      </div>
                      <p className="text-xs text-accent-amber mt-1">匹配关键词: {match.matched_keyword}</p>
                      <p className="text-xs text-muted mt-1 line-clamp-2">{match.content}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}