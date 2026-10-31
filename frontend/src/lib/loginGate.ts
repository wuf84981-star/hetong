import { isAuthed } from '../hooks/useAuth'

type Action = () => void

let opener: ((onSuccess: Action) => void) | null = null
let pending: Action[] = []

/** 由 Layout 挂载的登录弹层注册唤起入口 */
export function setLoginOpener(fn: ((onSuccess: Action) => void) | null) {
  opener = fn
}

/**
 * 需要登录的动作门：已登录立即执行；访客弹登录层，登录成功后自动续做。
 * 兜底：若弹层尚未挂载（罕见时序），退回登录页并用 ?from= 回跳。
 */
export function requireLogin(action?: Action): boolean {
  if (isAuthed()) {
    action?.()
    return true
  }
  // 只保留最近一次待续做的动作，避免登录成功后执行一串遗留点击
  if (action) pending = [action]
  if (opener) {
    opener(() => {
      const queued = pending.splice(0)
      queued.forEach(fn => fn())
    })
  } else {
    window.location.href = `/login?from=${encodeURIComponent(window.location.pathname + window.location.search)}`
  }
  return false
}
