import { useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { Activity, LogIn, UserPlus } from 'lucide-react'
import AuthForm from '../components/AuthForm'
import RegisterForm from '../components/RegisterForm'
import { MOTION } from '../lib/motion'

export default function Login() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const from = params.get('from')
  const [mode, setMode] = useState<'login' | 'register'>('login')

  const goWorkspace = () => navigate(from || '/dashboard', { replace: true })

  const tabCls = (active: boolean) =>
    `flex-1 flex items-center justify-center gap-1.5 py-2 text-sm rounded-lg transition-colors duration-300 ${
      active
        ? 'bg-accent-cyan/16 text-accent-cyan border border-accent-cyan/50'
        : 'text-muted hover:text-text border border-transparent'
    }`

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-surface-1 px-4">
      {/* 题签：深空里的字号 */}
      <div className={`mb-8 text-center ${MOTION.develop}`}>
        <div className="flex items-center justify-center gap-2.5 mb-3">
          <div className="w-10 h-10 rounded-xl bg-accent-cyan/16 border border-accent-cyan/50 flex items-center justify-center">
            <Activity className="w-5 h-5 text-accent-cyan" />
          </div>
        </div>
        <h1 className="font-display text-3xl font-semibold text-text tracking-wide">分寸合同</h1>
        <p className="text-xs text-muted font-mono mt-1.5 tracking-[0.3em]">MULTI-AGENT REVIEW</p>
      </div>

      <div className={`w-full max-w-md bg-surface-2 border border-surface-3 rounded-2xl shadow-glow p-8 ${MOTION.lift}`}>
        {/* 登录 / 注册切换 */}
        <div className="flex gap-2 mb-6">
          <button type="button" className={tabCls(mode === 'login')} onClick={() => setMode('login')}>
            <LogIn className="w-4 h-4" />
            登录
          </button>
          <button type="button" className={tabCls(mode === 'register')} onClick={() => setMode('register')}>
            <UserPlus className="w-4 h-4" />
            注册
          </button>
        </div>

        {/* key 让切面重挂载，播放显影入场 */}
        <div key={mode} className={MOTION.develop}>
          {mode === 'login' ? (
            <AuthForm onSuccess={goWorkspace} onSwitchToRegister={() => setMode('register')} />
          ) : (
            <RegisterForm onSuccess={goWorkspace} />
          )}
        </div>

        <p className="mt-5 pt-4 border-t border-surface-3 text-center">
          <Link to="/regulations" className="text-xs text-muted hover:text-accent-cyan transition-colors duration-300">
            先随便看看 —— 法规库免登录可查
          </Link>
        </p>
      </div>
    </div>
  )
}
