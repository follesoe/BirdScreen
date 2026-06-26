import type { ReactNode } from 'react'

interface FieldProps {
  label: string
  hint?: string
  icon?: string
  children: ReactNode
}

export function Field({ label, hint, icon, children }: FieldProps) {
  return (
    <div className="flex flex-col gap-1">
      <span className="flex items-center gap-2 font-body text-ink">
        {icon !== undefined ? <img src={icon} alt="" className="h-9 w-9" /> : null}
        {label}
      </span>
      {children}
      {hint !== undefined ? <span className="font-body text-xs text-ink-soft">{hint}</span> : null}
    </div>
  )
}
