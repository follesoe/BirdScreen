import type { ReactNode } from 'react'

interface PageHeadingProps {
  children: ReactNode
  action?: ReactNode
}

/** Consistent heading for content pages (Gallery, Logs, config screens). */
export function PageHeading({ children, action }: PageHeadingProps) {
  return (
    <div className="mb-5 flex items-center justify-between">
      <h2 className="font-display text-3xl text-ink">{children}</h2>
      {action}
    </div>
  )
}
