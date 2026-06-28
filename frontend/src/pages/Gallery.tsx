import { useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type GenerationLogEntry, type PosterInfo } from '@/api/client'
import { Lightbox } from '@/components/Lightbox'
import { PageHero } from '@/components/PageHero'
import galleryHero from '@/assets/heroes/gallery.webp'

export function Gallery() {
  const { t } = useTranslation()
  const [posters, setPosters] = useState<PosterInfo[] | null>(null)
  const [records, setRecords] = useState<Record<string, GenerationLogEntry>>({})
  const [error, setError] = useState<string | null>(null)
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)

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
    void api
      .generations()
      .then((gens) => {
        if (!active) return
        const map: Record<string, GenerationLogEntry> = {}
        for (const g of gens) {
          if (g.output !== null) map[g.output] = g
        }
        setRecords(map)
      })
      .catch(() => {
        // metadata is best-effort
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
        {posters.map((poster, index) => {
          const record = records[poster.name]
          const when = record ? record.created_at : poster.date
          const title =
            when !== null
              ? new Date(when).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
              : poster.name
          const birds = record ? record.birds.join(', ') : ''
          return (
            <li key={poster.name}>
              <button
                type="button"
                onClick={() => {
                  setSelectedIndex(index)
                }}
                className="block w-full overflow-hidden rounded-lg border border-bark/30 bg-paper text-left shadow-sm transition hover:shadow-md"
              >
                <img
                  src={api.thumbUrl(poster.name)}
                  alt={poster.name}
                  loading="lazy"
                  className="aspect-video w-full bg-parchment object-cover"
                />
                <div className="px-3 py-2">
                  <p className="font-display text-lg text-ink">{title}</p>
                  {birds !== '' ? (
                    <p className="truncate font-body text-sm text-ink-soft">{birds}</p>
                  ) : null}
                </div>
              </button>
            </li>
          )
        })}
      </ul>
    )
  }

  const selectedPoster =
    selectedIndex !== null && posters !== null ? (posters[selectedIndex] ?? null) : null

  return (
    <section>
      <PageHero title={t('gallery.heading')} image={galleryHero} intro={t('gallery.intro')} />
      {content}
      {selectedPoster !== null && selectedIndex !== null && posters !== null ? (
        <Lightbox
          name={selectedPoster.name}
          record={records[selectedPoster.name]}
          onClose={() => {
            setSelectedIndex(null)
          }}
          onPrev={
            selectedIndex > 0
              ? () => {
                  setSelectedIndex(selectedIndex - 1)
                }
              : undefined
          }
          onNext={
            selectedIndex < posters.length - 1
              ? () => {
                  setSelectedIndex(selectedIndex + 1)
                }
              : undefined
          }
        />
      ) : null}
    </section>
  )
}
