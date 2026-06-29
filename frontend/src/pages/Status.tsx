import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type GenerationLogEntry, type StatusResponse } from '@/api/client'
import { Lightbox } from '@/components/Lightbox'
import { PageHeading } from '@/components/PageHeading'
import { PageHero } from '@/components/PageHero'
import { Button } from '@/components/form/Button'
import { Section } from '@/components/form/Section'
import statusHero from '@/assets/heroes/status.webp'
import binocularsIcon from '@/assets/icons/binoculars.png'
import easelIcon from '@/assets/icons/easel.png'
import framesIcon from '@/assets/icons/frames.png'

const STATE_TONE: Record<string, string> = {
  ready: 'bg-sage/25 text-ink',
  cooldown: 'bg-amber/30 text-ink',
  outside_window: 'bg-amber/30 text-ink',
  cap_reached: 'bg-robin/20 text-robin',
  no_tvs: 'bg-robin/20 text-robin',
}

function fmtTime(iso: string | null): string {
  if (iso === null) return '—'
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
}

function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString([], {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-bark/15 py-1.5 last:border-0">
      <dt className="font-body text-ink-soft">{label}</dt>
      <dd className="text-right font-body text-ink">{value}</dd>
    </div>
  )
}

export function Status() {
  const { t } = useTranslation()
  const [status, setStatus] = useState<StatusResponse | null>(null)
  const [history, setHistory] = useState<GenerationLogEntry[]>([])
  const [busy, setBusy] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)

  const generate = useCallback(() => {
    setBusy(true)
    void api
      .generate()
      .then((result) => {
        if (!result.started) {
          setBusy(false)
          return
        }
        // Poll while it renders (~30–60s); refresh history + status as it lands.
        let elapsed = 0
        const id = setInterval(() => {
          elapsed += 5
          void api
            .generations()
            .then((g) => {
              setHistory(g)
            })
            .catch(() => {
              // ignore transient errors while polling
            })
          void api
            .status()
            .then((s) => {
              setStatus(s)
            })
            .catch(() => {
              // ignore transient errors while polling
            })
          if (elapsed >= 120) {
            clearInterval(id)
            setBusy(false)
          }
        }, 5000)
      })
      .catch(() => {
        setBusy(false)
      })
  }, [])

  const load = useCallback(() => {
    void api
      .status()
      .then((s) => {
        setStatus(s)
      })
      .catch(() => {
        // transient; keep showing the last status
      })
    void api
      .generations()
      .then((g) => {
        setHistory(g)
      })
      .catch(() => {
        // ignore
      })
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 30000)
    return () => {
      clearInterval(id)
    }
  }, [load])

  if (status === null) {
    return (
      <section>
        <PageHeading>{t('status.heading')}</PageHeading>
        <p className="text-ink-soft">{t('status.loading')}</p>
      </section>
    )
  }

  const selectedEntry = selectedIndex !== null ? (history[selectedIndex] ?? null) : null

  const windowValue = status.in_active_window
    ? `${t('status.active')} · ${status.current_window ?? ''}`
    : status.next_window_start !== null
      ? `${t('status.inactive')} · ${t('status.nextAt')} ${fmtTime(status.next_window_start)}`
      : t('status.inactive')
  const speciesValue = status.species_today.length > 0 ? status.species_today.join(', ') : '—'
  const tvsValue =
    status.tvs.length === 0
      ? '—'
      : status.tvs
          .map((tv) => (tv.enabled ? tv.name : `${tv.name} (${t('status.paused')})`))
          .join(', ')

  return (
    <section className="max-w-3xl">
      <PageHero
        title={t('status.heading')}
        image={statusHero}
        intro={t('status.intro')}
        action={
          <Button onClick={generate} disabled={busy}>
            {busy ? t('status.generating') : t('status.generateNow')}
          </Button>
        }
      />

      <div className="flex flex-col gap-5">
        <Section title={t('status.nowTitle')} icon={binocularsIcon}>
          <dl>
            <Row label={t('status.activeWindow')} value={windowValue} />
            <Row label={t('status.location')} value={status.location_name ?? '—'} />
            <Row label={t('status.weather')} value={status.weather ?? '—'} />
            <Row
              label={t('status.birdnet')}
              value={status.birdnet_connected ? t('status.connected') : t('status.disconnected')}
            />
            <Row label={t('status.speciesToday')} value={speciesValue} />
            <Row label={t('status.tvsTitle')} value={tvsValue} />
          </dl>
        </Section>

        <Section title={t('status.nextTitle')} icon={easelIcon}>
          <span
            className={`inline-block rounded-full px-3 py-1 font-body text-sm ${
              STATE_TONE[status.next_state] ?? 'bg-parchment text-ink'
            }`}
          >
            {t(`status.state.${status.next_state}`)}
          </span>
          <p className="mt-3 font-body text-ink-soft">{status.next_reason}</p>
          <dl className="mt-3">
            <Row label={t('status.eligibleAt')} value={fmtTime(status.next_eligible_at)} />
            {status.next_light_refresh !== null && status.next_light_refresh_kind !== null ? (
              <Row
                label={t('status.lightRefresh')}
                value={`${t(`status.lightKind.${status.next_light_refresh_kind}`)} · ${fmtTime(status.next_light_refresh)}`}
              />
            ) : null}
            <Row
              label={t('status.generationsToday')}
              value={`${String(status.generations_today)} / ${String(status.daily_cap)}`}
            />
            <Row label={t('status.willInclude')} value={speciesValue} />
          </dl>
        </Section>

        <Section title={t('status.historyTitle')} icon={framesIcon}>
          {history.length === 0 ? (
            <p className="text-ink-soft">{t('status.historyEmpty')}</p>
          ) : (
            <ul className="flex flex-col gap-3">
              {history.map((g, index) => (
                <li key={g.id} className="rounded-lg border border-bark/20 bg-parchment p-3">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="font-display text-lg text-ink">
                      {fmtDateTime(g.created_at)}
                    </span>
                    <span className="font-body text-xs text-ink-soft">{g.trigger}</span>
                  </div>
                  {g.reason !== null ? (
                    <p className="font-body text-sm text-ink-soft">{g.reason}</p>
                  ) : null}
                  <p className="mt-1 font-body text-sm text-ink">{g.birds.join(', ')}</p>
                  <p className="font-body text-xs text-ink-soft">
                    {[g.location, g.season, g.weather].filter(Boolean).join(' · ')}
                  </p>
                  {g.total_tokens !== null || g.cost_usd !== null ? (
                    <p className="font-body text-xs text-ink-soft">
                      {[
                        g.total_tokens !== null
                          ? `${g.total_tokens.toLocaleString()} tokens`
                          : null,
                        g.cost_usd !== null ? `$${g.cost_usd.toFixed(4)}` : null,
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </p>
                  ) : null}
                  {g.output !== null ? (
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedIndex(index)
                      }}
                      className="font-body text-sm text-robin hover:underline"
                    >
                      {t('status.viewPoster')}
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      {selectedEntry !== null && selectedIndex !== null ? (
        <Lightbox
          name={selectedEntry.output ?? ''}
          record={selectedEntry}
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
            selectedIndex < history.length - 1
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
