import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

const POLL_MS = 60_000

/** 与案头页同一判据：幕僚核毕等人工定夺的卷宗 */
function isAwaiting(item: { status: string; needs_human_review: boolean }): boolean {
  return item.status === 'awaiting_human' || (item.needs_human_review && !['approved', 'rejected'].includes(item.status))
}

/**
 * 待把关提醒：每分钟查一遍卷宗台账——
 * ① 页签标题挂上「(N 待把关)」；
 * ② 出现新增待把关卷宗时发一次浏览器通知（拒绝授权则静默）。
 */
export function useAwaitingAlert(): number {
  const [awaitingCount, setAwaitingCount] = useState(0)
  const seenRef = useRef<Set<string>>(new Set())
  const readyRef = useRef(false)

  useEffect(() => {
    const originalTitle = document.title
    let stopped = false

    const tick = async () => {
      // 访客无卷可查，跳过本轮；登录后下一次轮询自动恢复
      if (!localStorage.getItem('access_token')) return
      try {
        const res = await api.listReviews(1, 50)
        if (stopped) return
        const awaiting = res.items.filter(isAwaiting)
        const ids = new Set(awaiting.map(i => i.review_id))
        setAwaitingCount(ids.size)
        document.title = ids.size > 0 ? `(${ids.size} 待把关) ${originalTitle}` : originalTitle

        const isFirst = !readyRef.current
        const fresh = Array.from(ids).filter(rid => !seenRef.current.has(rid))
        seenRef.current = ids
        readyRef.current = true

        if (typeof Notification === 'undefined') return
        if (!isFirst && fresh.length > 0) {
          if (Notification.permission === 'granted') {
            new Notification('合同审查待您把关', {
              body: `有 ${fresh.length} 卷幕僚已核毕，等您定夺`,
              tag: 'fencun-contract-awaiting',
            })
          } else if (Notification.permission === 'default') {
            // 第一次真有消息时报请许可；浏览器若要求交互授权则静默作罢
            Notification.requestPermission().catch(() => {})
          }
        }
      } catch {
        // 未登录、后端不可达等情形不打扰案头，静默跳过
      }
    }

    tick()
    const timer = window.setInterval(tick, POLL_MS)
    return () => {
      stopped = true
      window.clearInterval(timer)
      document.title = originalTitle
    }
  }, [])

  return awaitingCount
}
