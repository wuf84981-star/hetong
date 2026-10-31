import { useEffect, useState } from 'react'

/**
 * 用户是否要求「减少动态效果」。CSS 动画有 index.css 全局降级兜底，
 * SVG/SMIL 动画不受 CSS 管辖，渲染判断用它。
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches,
  )
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = () => setReduced(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  return reduced
}
