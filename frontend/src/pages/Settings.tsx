import { useTheme } from '../hooks/useTheme'
import { useAuth } from '../hooks/useAuth'
import Card from '../components/Card'
import StatusBadge from '../components/StatusBadge'

export default function Settings() {
  const { theme, toggle } = useTheme()
  const { username, role } = useAuth()

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h2 className="text-2xl font-bold text-text">系统设置</h2>
        <p className="text-sm text-muted mt-1">查看本人署名与角色，切换亮暗主题；此处不改动审查数据。</p>
      </div>

      <Card>
        <h3 className="font-semibold text-text mb-4">用户信息</h3>
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted">用户名</span>
            <span className="text-sm text-text">{username || '访客 · 未署名'}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted">角色</span>
            <StatusBadge label={role || 'viewer'} variant={role === 'admin' ? 'info' : 'default'} />
          </div>
        </div>
      </Card>

      <Card>
        <h3 className="font-semibold text-text mb-4">外观设置</h3>
        <div className="flex justify-between items-center">
          <span className="text-sm text-muted">主题模式</span>
          <button onClick={toggle}
            className="px-4 py-2 bg-surface-3 text-text rounded-lg text-sm hover:bg-surface-4 transition">
            {theme === 'dark' ? '切换为亮色' : '切换为暗色'}
          </button>
        </div>
      </Card>
    </div>
  )
}
