import { useState } from 'react'
import { useAuth } from '../hooks/useAuth'

/** 登录表单：登录页与登录弹层共用，成功后回调 onSuccess；传入 onSwitchToRegister 时底部换成注册入口 */
export default function AuthForm({ onSuccess, onSwitchToRegister }: {
  onSuccess: () => void
  onSwitchToRegister?: () => void
}) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username, password)
      onSuccess()
    } catch (err: any) {
      setError(err.message || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-xs font-medium text-muted mb-1.5">用户名</label>
        <input
          type="text"
          value={username}
          onChange={e => setUsername(e.target.value)}
          className="w-full px-3 py-2.5 bg-surface-1 border border-surface-3 rounded-lg text-sm text-text placeholder:text-muted focus:outline-none focus:border-accent-cyan transition-colors duration-300"
          placeholder="请输入用户名"
          required
          autoFocus
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-muted mb-1.5">密码</label>
        <input
          type="password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          className="w-full px-3 py-2.5 bg-surface-1 border border-surface-3 rounded-lg text-sm text-text placeholder:text-muted focus:outline-none focus:border-accent-cyan transition-colors duration-300"
          placeholder="请输入密码"
          required
        />
      </div>

      {error && <p className="text-accent-red text-sm">{error}</p>}

      <button
        type="submit"
        disabled={loading}
        className="w-full bg-accent-cyan text-white py-2.5 rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-[color,background-color,opacity] duration-300"
      >
        {loading ? '登录中...' : '登录'}
      </button>
      {onSwitchToRegister ? (
        <p className="text-xs text-muted font-kai text-center">
          没有账号？
          <button
            type="button"
            onClick={onSwitchToRegister}
            className="text-accent-cyan hover:underline transition-colors duration-300"
          >
            立即邮箱注册
          </button>
        </p>
      ) : (
        <p className="text-xs text-muted font-kai text-center">尚无账号？请管理员发放后即可开卷</p>
      )}
    </form>
  )
}
