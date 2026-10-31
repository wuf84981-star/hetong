import { useEffect, useRef, useState } from 'react'
import { Activity } from 'lucide-react'
import AuthForm from './AuthForm'
import { setLoginOpener } from '../lib/loginGate'
import { MOTION } from '../lib/motion'

/**
 * 全局登录弹层：免登录直入的「用功能时再登录」入口。
 * ① requireLogin 动作门唤起（登录后自动续做原动作）；
 * ② API 401 事件唤起（会话过期时）。挂在 Layout 内，全站共用一个。
 */
export default function LoginModal() {
  const [open, setOpen] = useState(false)
  const onSuccessRef = useRef<(() => void) | undefined>(undefined)

  useEffect(() => {
    setLoginOpener(onSuccess => {
      onSuccessRef.current = onSuccess
      setOpen(true)
    })
    const onUnauthorized = () => setOpen(true)
    window.addEventListener('unauthorized', onUnauthorized)
    return () => {
      setLoginOpener(null)
      window.removeEventListener('unauthorized', onUnauthorized)
    }
  }, [])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="登录"
      onClick={() => setOpen(false)}
    >
      <div
        className={`w-full max-w-sm bg-surface-2 border border-accent-cyan/45 rounded-2xl shadow-glow p-6 ${MOTION.develop}`}
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center gap-2.5 mb-5">
          <div className="w-9 h-9 rounded-xl bg-accent-cyan/16 border border-accent-cyan/50 flex items-center justify-center">
            <Activity className="w-5 h-5 text-accent-cyan" />
          </div>
          <div>
            <h3 className="font-display text-base font-semibold text-text">立卷需要署名</h3>
            <p className="text-xs text-muted font-kai">登录后继续刚才的操作，表单内容不会丢</p>
          </div>
        </div>
        <AuthForm
          onSuccess={() => {
            setOpen(false)
            onSuccessRef.current?.()
            onSuccessRef.current = undefined
          }}
        />
      </div>
    </div>
  )
}
