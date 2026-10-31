import { clsx } from 'clsx'
import { MOTION } from '../lib/motion'

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  text?: string
  className?: string
}

const sizes = { sm: 'w-4 h-4', md: 'w-8 h-8', lg: 'w-12 h-12' }

export default function LoadingSpinner({ size = 'md', text, className }: LoadingSpinnerProps) {
  return (
    <div className={clsx('flex flex-col items-center justify-center py-16', className)}>
      <div className={clsx(`${MOTION.spin} border-4 border-accent-cyan border-t-transparent rounded-full`, sizes[size])} />
      {text && <p className="mt-3 text-sm text-muted">{text}</p>}
    </div>
  )
}
