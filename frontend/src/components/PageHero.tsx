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
    <div className="mb-6 flex items-center gap-5">
      <img src={image} alt="" className="w-52 shrink-0 sm:w-64" />
      <div className="flex flex-col items-start gap-2">
        <h2 className="font-display text-3xl text-ink">{title}</h2>
        {intro !== undefined ? <p className="max-w-md font-body text-ink-soft">{intro}</p> : null}
        {action !== undefined ? <div className="mt-1">{action}</div> : null}
      </div>
    </div>
  )
}
