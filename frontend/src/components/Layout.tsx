import { Link, NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useState } from 'react'
import {
  LayoutDashboard, FileSearch, Scale, FileText,
  Settings, LogOut, LogIn, Activity, Sun, Moon,
  BookOpen, GitCompare, MessageSquare, Menu, History as HistoryIcon, Library,
} from 'lucide-react'
import { usePolling } from '../hooks/useApi'
import { useTheme } from '../hooks/useTheme'
import { useAuth } from '../hooks/useAuth'
import { useAwaitingAlert } from '../hooks/useAwaitingAlert'
import { api } from '../api/client'
import { MOTION } from '../lib/motion'
import LoginModal from './LoginModal'
import { useCallback } from 'react'

const nav = [
  { to: '/dashboard', label: '案头', icon: LayoutDashboard },
  { to: '/review', label: '合同审查', icon: FileSearch },
  { to: '/history', label: '审查历史', icon: HistoryIcon },
  { to: '/rules', label: '规则管理', icon: Scale },
  { to: '/templates', label: '模板管理', icon: FileText },
  { to: '/knowledge', label: '知识库', icon: Library },
  { to: '/regulations', label: '法规引用', icon: BookOpen },
  { to: '/diff', label: '版本对比', icon: GitCompare },
  { to: '/negotiation', label: '协商追踪', icon: MessageSquare },
  { to: '/settings', label: '系统设置', icon: Settings },
]

export default function Layout() {
  const [collapsed, setCollapsed] = useState(false)
  const [hovered, setHovered] = useState(false)
  const fetchHealth = useCallback(() => api.health(), [])
  const { data: health } = usePolling(fetchHealth, 15000)
  const awaitingCount = useAwaitingAlert()
  const { theme, toggle } = useTheme()
  const { username, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const goLogin = () => navigate(`/login?from=${encodeURIComponent(location.pathname + location.search)}`)

  const isExpanded = !collapsed || hovered

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside
        className={`${isExpanded ? 'w-56' : 'w-16'} flex-shrink-0 bg-surface-1 border-r border-surface-3 flex flex-col transition-all duration-300`}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        {/* Logo & Toggle */}
        <div className={`border-b border-surface-3 flex items-center ${isExpanded ? 'px-4 py-4' : 'px-3 py-4 justify-center'}`}>
          {isExpanded ? (
            <div className="flex items-center justify-between w-full">
              <Link to="/" title="产品首页 · 系统介绍" className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-accent-cyan/16 border border-accent-cyan/50 flex items-center justify-center">
                  <Activity className="w-4 h-4 text-accent-cyan" />
                </div>
                <div>
                  <h1 className="text-sm font-semibold text-text tracking-tight">合同审查</h1>
                  <p className="text-[10px] text-muted font-kai tracking-wider">AI 法务幕僚</p>
                </div>
              </Link>
              <button
                onClick={() => setCollapsed(!collapsed)}
                className="text-muted hover:text-text p-1 rounded"
              >
                <Menu className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <Link to="/" title="产品首页 · 系统介绍" className="w-8 h-8 rounded-lg bg-accent-cyan/16 border border-accent-cyan/50 flex items-center justify-center">
              <Activity className="w-4 h-4 text-accent-cyan" />
            </Link>
          )}
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-2 py-3 space-y-1 overflow-y-auto">
          {nav.map(({ to, label, icon: Icon }) => {
            const showBadge = to === '/history' && awaitingCount > 0
            return (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-lg text-sm transition-[color,background-color,border-color] duration-300 ${
                    isExpanded ? 'px-3 py-2.5' : 'px-3 py-2.5 justify-center'
                  } ${
                    isActive
                      ? 'bg-accent-cyan/16 text-accent-cyan border border-accent-cyan/50'
                      : 'text-muted hover:text-text hover:bg-surface-2 border border-transparent'
                  }`
                }
                title={!isExpanded ? (showBadge ? `${label}：${awaitingCount} 卷待把关` : label) : undefined}
              >
                <span className="relative shrink-0">
                  <Icon className="w-4 h-4" />
                  {showBadge && (
                    <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-accent-red" aria-hidden="true" />
                  )}
                </span>
                {isExpanded && <span className="font-medium whitespace-nowrap">{label}</span>}
                {isExpanded && showBadge && (
                  <span className="ml-auto text-[10px] font-mono text-accent-red" aria-label={`${awaitingCount} 卷待把关`}>
                    {awaitingCount} 待把关
                  </span>
                )}
              </NavLink>
            )
          })}
        </nav>

        {/* Bottom */}
        <div className={`border-t border-surface-3 space-y-2 ${isExpanded ? 'px-3 py-3' : 'px-2 py-3'}`}>
          <button
            onClick={toggle}
            className={`flex items-center gap-2 w-full rounded-lg text-xs font-mono text-muted hover:text-text hover:bg-surface-2 transition-[color,background-color] duration-300 ${
              isExpanded ? 'px-3 py-2' : 'px-3 py-2 justify-center'
            }`}
            title={!isExpanded ? (theme === 'dark' ? '亮色模式' : '暗色模式') : undefined}
          >
            {theme === 'dark' ? <Sun className="w-3.5 h-3.5 flex-shrink-0" /> : <Moon className="w-3.5 h-3.5 flex-shrink-0" />}
            {isExpanded && <span>{theme === 'dark' ? '亮色模式' : '暗色模式'}</span>}
          </button>

          <div className={`flex items-center ${isExpanded ? 'justify-between' : 'justify-center'}`}>
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full flex-shrink-0 ${health?.status === 'healthy' ? `bg-accent-green ${MOTION.breathe}` : 'bg-accent-red'}`} />
              {isExpanded && <span className="text-xs font-mono text-muted">{health?.status === 'healthy' ? '已连接' : '未连接'}</span>}
            </div>
            {username ? (
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted">{username}</span>
                <button onClick={handleLogout} title="退出登录" className="text-muted hover:text-accent-red transition-colors duration-300">
                  <LogOut className="w-3.5 h-3.5" />
                </button>
              </div>
            ) : (
              <button
                onClick={goLogin}
                title="登录并立卷"
                className={`flex items-center gap-1.5 rounded-lg text-xs font-medium text-accent-cyan border border-accent-cyan/50 bg-accent-cyan/16 px-2 py-1 hover:bg-accent-cyan/18 transition-[color,background-color,border-color] duration-300 ${isExpanded ? '' : 'justify-center'}`}
              >
                <LogIn className="w-3.5 h-3.5 flex-shrink-0" />
                {isExpanded && <span>登录立卷</span>}
              </button>
            )}
          </div>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">
        <div className="p-6">
          <Outlet />
        </div>
      </main>

      {/* 全局登录弹层：写操作门与 401 事件的落点 */}
      <LoginModal />
    </div>
  )
}
