import type { ReactNode } from 'react'

interface PageHeroProps {
  title: string
  image: string
  intro?: string
  action?: ReactNode
}

/** Page header with a watercolour hero illustration (cut-out, sits on parchment). */
export function PageHero({ title, image, intro, action }: PageHeroProps) {
  return (
    <div className="mb-6 flex flex-col-reverse items-start gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex flex-col gap-2">
        <h2 className="font-display text-3xl text-ink">{title}</h2>
        {intro !== undefined ? <p className="max-w-md font-body text-ink-soft">{intro}</p> : null}
        {action !== undefined ? <div>{action}</div> : null}
      </div>
      <img src={image} alt="" className="h-44 w-auto shrink-0 sm:h-52" />
    </div>
  )
}
