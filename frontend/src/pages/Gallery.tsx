import { useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type PosterInfo } from '@/api/client'
import { PageHero } from '@/components/PageHero'
import galleryHero from '@/assets/heroes/gallery.webp'

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

  let content: ReactNode
  if (error !== null) {
    content = <p className="text-robin">{t('gallery.loadError')}</p>
  } else if (posters === null) {
    content = <p className="text-ink-soft">{t('gallery.loading')}</p>
  } else if (posters.length === 0) {
    content = <p className="text-ink-soft">{t('gallery.empty')}</p>
  } else {
    content = (
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
    )
  }

  return (
    <section>
      <PageHero title={t('gallery.heading')} image={galleryHero} intro={t('gallery.intro')} />
      {content}
    </section>
  )
}
