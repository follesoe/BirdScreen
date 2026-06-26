import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type TvConfig } from '@/api/client'
import { PageHeading } from '@/components/PageHeading'
import { PageHero } from '@/components/PageHero'
import { SaveButton } from '@/components/form/SaveButton'
import { TvCard } from '@/components/TvCard'
import type { SaveStatus } from '@/hooks/useEditableConfig'
import tvsHero from '@/assets/heroes/tvs.webp'

export function Tvs() {
  const { t } = useTranslation()
  const [tvs, setTvs] = useState<TvConfig[] | null>(null)
  const [status, setStatus] = useState<SaveStatus>('idle')

  useEffect(() => {
    let active = true
    void api
      .tvs()
      .then((list) => {
        if (active) setTvs(list)
      })
      .catch(() => {
        // leave null → loading state
      })
    return () => {
      active = false
    }
  }, [])

  function mutate(next: TvConfig[]) {
    setTvs(next)
    setStatus('idle')
  }

  function save(list: TvConfig[]) {
    setStatus('saving')
    void api
      .saveTvs(list)
      .then((saved) => {
        setTvs(saved)
        setStatus('saved')
      })
      .catch(() => {
        setStatus('idle')
      })
  }

  if (tvs === null) {
    return (
      <section>
        <PageHeading>{t('tvs.heading')}</PageHeading>
        <p className="text-ink-soft">{t('tvs.loading')}</p>
      </section>
    )
  }

  return (
    <section className="max-w-2xl">
      <PageHero
        title={t('tvs.heading')}
        image={tvsHero}
        intro={t('tvs.intro')}
        action={
          <SaveButton
            status={status}
            onClick={() => {
              save(tvs)
            }}
          />
        }
      />

      <p className="mb-5 rounded-xl border border-amber/50 bg-amber/10 p-4 font-body text-sm text-ink-soft">
        {t('tvs.pairingHint')}
      </p>

      <div className="flex flex-col gap-4">
        {tvs.map((tv, index) => (
          <TvCard
            key={index}
            tv={tv}
            onChange={(patch) => {
              mutate(tvs.map((item, i) => (i === index ? { ...item, ...patch } : item)))
            }}
            onRemove={() => {
              mutate(tvs.filter((_, i) => i !== index))
            }}
          />
        ))}
        {tvs.length === 0 ? <p className="text-ink-soft">{t('tvs.empty')}</p> : null}
        <button
          type="button"
          onClick={() => {
            mutate([...tvs, { name: t('tvs.defaultName'), ip: '', monitor_art_mode: true }])
          }}
          className="self-start rounded-full border border-bark/40 px-5 py-2 font-body text-ink-soft transition-colors hover:bg-parchment-deep"
        >
          {t('tvs.add')}
        </button>
      </div>
    </section>
  )
}
