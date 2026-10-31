import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { MOTION } from '../lib/motion'

/** 邮箱验证码注册表单：60 秒发送冷却内置，成功后回调 onSuccess（useAuth 已自动登录） */
export default function RegisterForm({ onSuccess }: { onSuccess: () => void }) {
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [cooldown, setCooldown] = useState(0)
  const { register } = useAuth()

  // 冷却倒计时：归零自动解禁「发送验证码」钮
  useEffect(() => {
    if (cooldown <= 0) return
    const t = setInterval(() => setCooldown(c => c - 1), 1000)
    return () => clearInterval(t)
  }, [cooldown])

  const handleSendCode = async () => {
    setError('')
    setInfo('')
    if (!email.trim()) {
      setError('请先填写邮箱')
      return
    }
    setSending(true)
    try {
      await api.sendRegisterCode(email.trim())
      setCooldown(60) // 冷却 60 秒，与后端 COOLDOWN_SECONDS 一致
      setInfo('验证码已发至邮箱，5 分钟内有效')
    } catch (err: any) {
      setError(err.message || '验证码发送失败')
    } finally {
      setSending(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await register(username.trim(), email.trim(), password, code.trim())
      onSuccess()
    } catch (err: any) {
      setError(err.message || '注册失败')
    } finally {
      setLoading(false)
    }
  }

  const inputCls =
    'w-full px-3 py-2.5 bg-surface-1 border border-surface-3 rounded-lg text-sm text-text placeholder:text-muted focus:outline-none focus:border-accent-cyan transition-colors duration-300'

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-xs font-medium text-muted mb-1.5">用户名</label>
        <input
          type="text"
          value={username}
          onChange={e => setUsername(e.target.value)}
          className={inputCls}
          placeholder="3-50 个字符"
          minLength={3}
          maxLength={50}
          required
          autoFocus
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-muted mb-1.5">邮箱</label>
        <input
          type="email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          className={inputCls}
          placeholder="用于接收验证码"
          required
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-muted mb-1.5">密码</label>
        <input
          type="password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          className={inputCls}
          placeholder="至少 6 位"
          minLength={6}
          required
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-muted mb-1.5">验证码</label>
        <div className="flex gap-2">
          <input
            type="text"
            value={code}
            onChange={e => setCode(e.target.value)}
            className={inputCls}
            placeholder="6 位数字"
            maxLength={6}
            required
          />
          <button
            type="button"
            onClick={handleSendCode}
            disabled={sending || cooldown > 0}
            className="shrink-0 px-3 py-2.5 bg-surface-1 border border-accent-cyan/50 rounded-lg text-sm text-accent-cyan hover:bg-accent-cyan/10 disabled:opacity-50 disabled:hover:bg-surface-1 transition-colors duration-300"
          >
            {cooldown > 0 ? `${cooldown}s` : sending ? <span className={MOTION.spin}>发送中</span> : '发送验证码'}
          </button>
        </div>
      </div>

      {info && <p className="text-accent-cyan text-sm">{info}</p>}
      {error && <p className="text-accent-red text-sm">{error}</p>}

      <button
        type="submit"
        disabled={loading}
        className="w-full bg-accent-cyan text-white py-2.5 rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-[color,background-color,opacity] duration-300"
      >
        {loading ? '注册中...' : '注册'}
      </button>
    </form>
  )
}
