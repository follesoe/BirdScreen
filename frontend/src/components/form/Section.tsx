import type { ReactNode } from 'react'

interface SectionProps {
  title: string
  description?: string
  icon?: string
  children: ReactNode
}

export function Section({ title, description, icon, children }: SectionProps) {
  return (
    <section className="rounded-2xl border border-bark/25 bg-parchment-deep/50 p-5">
      <h3 className="flex items-center gap-3 font-display text-2xl text-ink">
        {icon !== undefined ? <img src={icon} alt="" className="h-14 w-14" /> : null}
        {title}
      </h3>
      {description !== undefined ? (
        <p className="font-body text-sm text-ink-soft">{description}</p>
      ) : null}
      <div className="mt-4 flex flex-col gap-4">{children}</div>
    </section>
  )
}
