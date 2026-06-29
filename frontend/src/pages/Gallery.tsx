import { useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type GenerationLogEntry, type PosterInfo } from '@/api/client'
import { Lightbox } from '@/components/Lightbox'
import { PageHero } from '@/components/PageHero'
import galleryHero from '@/assets/heroes/gallery.webp'

interface DateGroup {
  label: string
  items: { poster: PosterInfo; index: number }[]
}

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

  const posterTime = (poster: PosterInfo): string | null =>
    records[poster.name]?.created_at ?? poster.date

  const dayLabel = (d: Date): string => {
    const startOfDay = (x: Date): number =>
      new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
    const diff = Math.round((startOfDay(new Date()) - startOfDay(d)) / 86_400_000)
    if (diff === 0) return t('gallery.today')
    if (diff === 1) return t('gallery.yesterday')
    return d.toLocaleDateString([], {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    })
  }

  const renderCard = (poster: PosterInfo, index: number): ReactNode => {
    const record = records[poster.name]
    const when = posterTime(poster)
    const label =
      when !== null
        ? new Date(when).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        : poster.name
    const birds = record?.birds.join(', ') ?? ''
    // Rich hover tooltip: full date, species, model/size, weather, cost.
    const tooltip = [
      when !== null
        ? new Date(when).toLocaleString([], { dateStyle: 'full', timeStyle: 'short' })
        : poster.name,
      record && record.birds.length > 0
        ? `${t('gallery.infoBirds')}: ${record.birds.join(', ')}`
        : null,
      record ? `${record.model} · ${record.image_size}` : null,
      record?.weather ?? null,
      record?.cost_usd != null ? `≈ $${record.cost_usd.toFixed(4)}` : null,
    ]
      .filter(Boolean)
      .join('\n')
    return (
      <li key={poster.name}>
        <button
          type="button"
          title={tooltip}
          onClick={() => {
            setSelectedIndex(index)
          }}
          className="relative block w-full overflow-hidden rounded-lg border border-bark/30 bg-paper text-left shadow-sm transition-all duration-200 ease-out hover:z-10 hover:-translate-y-1 hover:scale-[1.04] hover:shadow-xl"
        >
          <img
            src={api.thumbUrl(poster.name)}
            alt={poster.name}
            loading="lazy"
            className="aspect-video w-full bg-parchment object-cover"
          />
          <div className="px-3 py-2">
            <p className="font-display text-lg text-ink">{label}</p>
            {birds !== '' ? (
              <p className="truncate font-body text-sm text-ink-soft">{birds}</p>
            ) : null}
          </div>
        </button>
      </li>
    )
  }

  let content: ReactNode
  if (error !== null) {
    content = <p className="text-robin">{t('gallery.loadError')}</p>
  } else if (posters === null) {
    content = <p className="text-ink-soft">{t('gallery.loading')}</p>
  } else if (posters.length === 0) {
    content = <p className="text-ink-soft">{t('gallery.empty')}</p>
  } else {
    // Group by calendar day (posters arrive newest-first, so groups stay in that order).
    const groups = new Map<string, DateGroup>()
    posters.forEach((poster, index) => {
      const when = posterTime(poster)
      const day = when !== null ? new Date(when) : null
      const key = day !== null ? day.toLocaleDateString('en-CA') : 'undated'
      const group = groups.get(key) ?? {
        label: day !== null ? dayLabel(day) : t('gallery.undated'),
        items: [],
      }
      group.items.push({ poster, index })
      groups.set(key, group)
    })
    content = (
      <div className="flex flex-col gap-8">
        {[...groups.entries()].map(([key, group]) => (
          <section key={key}>
            <h2 className="mb-3 font-display text-2xl text-ink-soft">{group.label}</h2>
            <ul className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {group.items.map(({ poster, index }) => renderCard(poster, index))}
            </ul>
          </section>
        ))}
      </div>
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
