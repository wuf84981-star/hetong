import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'

interface AuthState {
  token: string | null
  role: string | null
  username: string | null
  isAuthenticated: boolean
}

function readAuth(): AuthState {
  return {
    token: localStorage.getItem('access_token'),
    role: localStorage.getItem('user_role'),
    username: localStorage.getItem('username'),
    isAuthenticated: !!localStorage.getItem('access_token'),
  }
}

/** 非组件环境（事件回调、门函数）里的登录态查询 */
export function isAuthed(): boolean {
  return !!localStorage.getItem('access_token')
}

/** 把服务端签发的 JWT 落到本地并广播登录态变化 */
export function applyLogin(accessToken: string, username: string) {
  const payload = JSON.parse(atob(accessToken.split('.')[1]))
  localStorage.setItem('access_token', accessToken)
  localStorage.setItem('user_role', payload.role || 'viewer')
  localStorage.setItem('username', username)
  window.dispatchEvent(new Event('auth-changed'))
}

export function useAuth() {
  const [auth, setAuth] = useState<AuthState>(readAuth)

  // 登录态跨组件同步：登录弹层/其他页签改了 storage，这里即时跟上新
  useEffect(() => {
    const sync = () => setAuth(readAuth())
    window.addEventListener('auth-changed', sync)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener('auth-changed', sync)
      window.removeEventListener('storage', sync)
    }
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const res = await api.login({ username, password })
    applyLogin(res.access_token, username)
    setAuth(readAuth())
    return res
  }, [])

  const register = useCallback(async (username: string, email: string, password: string, code: string) => {
    await api.register({ username, email, password, code })
    // 注册成功后立刻登录进工作台（register 响应仍是 UserResponse，契约未动）
    const res = await api.login({ username, password })
    applyLogin(res.access_token, username)
    setAuth(readAuth())
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('user_role')
    localStorage.removeItem('username')
    window.dispatchEvent(new Event('auth-changed'))
    setAuth(readAuth())
  }, [])

  return { ...auth, login, register, logout }
}
