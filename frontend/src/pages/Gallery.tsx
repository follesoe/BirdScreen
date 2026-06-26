import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type PosterInfo } from '@/api/client'
import { PageHeading } from '@/components/PageHeading'

export function Gallery() {
  const { t } = useTranslation()
  const [posters, setPosters] = useState<PosterInfo[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    void api
      .posters()
      .then((data) => {
        if (active) setPosters(data)
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : String(err))
      })
    return () => {
      active = false
    }
  }, [])

  if (error !== null) {
    return <p className="text-robin">{t('gallery.loadError')}</p>
  }
  if (posters === null) {
    return <p className="text-ink-soft">{t('gallery.loading')}</p>
  }

  return (
    <section>
      <PageHeading>{t('gallery.heading')}</PageHeading>
      {posters.length === 0 ? (
        <p className="text-ink-soft">{t('gallery.empty')}</p>
      ) : (
        <ul className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {posters.map((poster) => (
            <li
              key={poster.name}
              className="overflow-hidden rounded-lg border border-bark/30 bg-parchment-deep shadow-sm"
            >
              <a href={api.imageUrl(poster.name)} target="_blank" rel="noreferrer">
                <img
                  src={api.thumbUrl(poster.name)}
                  alt={poster.name}
                  loading="lazy"
                  className="aspect-video w-full bg-parchment object-cover"
                />
              </a>
              <p className="px-3 py-2 font-display text-lg text-ink">
                {poster.date !== null ? new Date(poster.date).toLocaleString() : poster.name}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
