import { clsx } from 'clsx'

type BadgeVariant = 'success' | 'warning' | 'error' | 'info' | 'default'

const variantStyles: Record<BadgeVariant, string> = {
  success: 'bg-accent-green/10 text-accent-green border-accent-green/20',
  warning: 'bg-accent-amber/10 text-accent-amber border-accent-amber/20',
  error: 'bg-accent-red/10 text-accent-red border-accent-red/20',
  info: 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/20',
  default: 'bg-surface-3 text-muted border-surface-4',
}

interface StatusBadgeProps {
  label: string
  variant?: BadgeVariant
}

export default function StatusBadge({ label, variant = 'default' }: StatusBadgeProps) {
  return (
    <span className={clsx(
      'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border',
      variantStyles[variant],
    )}>
      {label}
    </span>
  )
}
