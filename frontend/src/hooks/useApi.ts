import { useState, useEffect, useCallback, useRef } from 'react'
import { ApiError } from '../api/client'

interface UseApiState<T> {
  data: T | null
  loading: boolean
  error: string | null
  /** 请求失败时的 HTTP 状态码（401/403…），供页面区分鉴权失败类型 */
  status: number | null
}

export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []) {
  const [state, setState] = useState<UseApiState<T>>({ data: null, loading: true, error: null, status: null })

  const loadData = useCallback(async () => {
    setState(s => ({ ...s, loading: true, error: null, status: null }))
    try {
      const data = await fetcher()
      setState({ data, loading: false, error: null, status: null })
    } catch (e) {
      setState({
        data: null,
        loading: false,
        error: e instanceof Error ? e.message : String(e),
        status: e instanceof ApiError ? e.status : null,
      })
    }
  }, deps)

  useEffect(() => { loadData() }, [loadData])

  return { ...state, refetch: loadData }
}

export function usePolling<T>(fetcher: () => Promise<T>, intervalMs: number = 10000) {
  const [data, setData] = useState<T | null>(null)
  const savedFetcher = useRef(fetcher)
  savedFetcher.current = fetcher

  useEffect(() => {
    let active = true
    const poll = async () => {
      try {
        const result = await savedFetcher.current()
        if (active) setData(result)
      } catch {}
    }
    poll()
    const id = setInterval(poll, intervalMs)
    return () => { active = false; clearInterval(id) }
  }, [intervalMs])

  return { data }
}
