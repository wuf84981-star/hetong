import { clsx } from 'clsx'
import { ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  className?: string
  onClick?: () => void
}

export default function Card({ children, className, onClick }: CardProps) {
  return (
    <div
      onClick={onClick}
      className={clsx(
        'bg-surface-2 border border-surface-3 rounded-xl p-5',
        onClick && 'cursor-pointer hover:border-accent-cyan/30 transition-colors',
        className,
      )}
    >
      {children}
    </div>
  )
}
