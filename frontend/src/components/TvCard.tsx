import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type TvConfig, type TvStatus } from '@/api/client'
import { Field } from '@/components/form/Field'
import { Toggle } from '@/components/form/Toggle'
import { controlClass } from '@/components/form/styles'
import tvIcon from '@/assets/icons/tv.png'

interface TvCardProps {
  tv: TvConfig
  onChange: (patch: Partial<TvConfig>) => void
  onRemove: () => void
}

function StatusView({ status }: { status: TvStatus | 'loading' }) {
  const { t } = useTranslation()
  if (status === 'loading') {
    return <p className="text-sm text-ink-soft">{t('tvs.checking')}</p>
  }
  if (!status.connected) {
    return (
      <div className="rounded-lg border border-robin/40 bg-robin/5 p-3 text-sm">
        <p className="text-robin">{status.message ?? t('tvs.unreachable')}</p>
        <p className="mt-1 text-ink-soft">{t('tvs.pairingHint')}</p>
      </div>
    )
  }
  let inArtMode: string
  if (status.art_mode_on === null) {
    inArtMode = t('tvs.unknown')
  } else {
    inArtMode = status.art_mode_on ? t('tvs.yes') : t('tvs.no')
  }
  const rows: [string, string | null][] = [
    [t('tvs.statusName'), status.name],
    [t('tvs.statusModel'), status.model],
    [t('tvs.statusResolution'), status.resolution],
    [t('tvs.statusFirmware'), status.firmware],
    [t('tvs.statusSupportsArt'), status.supports_art_mode ? t('tvs.yes') : t('tvs.no')],
    [t('tvs.statusInArt'), inArtMode],
  ]
  return (
    <dl className="rounded-lg border border-bark/25 bg-parchment p-3 text-sm">
      {rows.map(([label, value]) =>
        value !== null ? (
          <div key={label} className="flex justify-between gap-4 py-0.5">
            <dt className="text-ink-soft">{label}</dt>
            <dd className="text-ink">{value}</dd>
          </div>
        ) : null,
      )}
      {!status.paired ? <p className="mt-2 text-xs text-ink-soft">{t('tvs.pairHint')}</p> : null}
    </dl>
  )
}

export function TvCard({ tv, onChange, onRemove }: TvCardProps) {
  const { t } = useTranslation()
  const [status, setStatus] = useState<TvStatus | 'loading' | null>(null)

  const check = useCallback(
    (pair = false) => {
      if (tv.ip === '') {
        setStatus(null)
        return
      }
      setStatus('loading')
      void api
        .tvStatus(tv.ip, pair)
        .then((s) => {
          setStatus(s)
        })
        .catch(() => {
          setStatus(null)
        })
    },
    [tv.ip],
  )

  // Auto-check on load — popup-free (pair=false); the manual button pairs.
  useEffect(() => {
    const id = setTimeout(() => {
      check(false)
    }, 500)
    return () => {
      clearTimeout(id)
    }
  }, [check])

  return (
    <section className="rounded-2xl border border-bark/25 bg-parchment-deep/50 p-5">
      <div className="mb-4 flex items-center gap-3">
        <img src={tvIcon} alt="" className="h-12 w-12 shrink-0" />
        <input
          value={tv.name}
          onChange={(e) => {
            onChange({ name: e.target.value })
          }}
          className={`${controlClass} flex-1 font-display text-xl`}
        />
        {!tv.enabled ? (
          <span className="rounded-full bg-bark/20 px-2.5 py-0.5 font-body text-xs tracking-wide text-ink-soft uppercase">
            {t('tvs.paused')}
          </span>
        ) : null}
        <button
          type="button"
          onClick={onRemove}
          className="font-body text-sm text-robin hover:underline"
        >
          {t('tvs.remove')}
        </button>
      </div>
      <div className="flex flex-col gap-4">
        <Field label={t('tvs.ip')} hint={t('tvs.ipHint')}>
          <div className="flex items-center gap-2">
            <input
              value={tv.ip}
              onChange={(e) => {
                onChange({ ip: e.target.value })
              }}
              placeholder="192.168.1.219"
              className={`${controlClass} flex-1`}
            />
            <button
              type="button"
              onClick={() => {
                check(true)
              }}
              disabled={tv.ip === ''}
              className="rounded-full border border-bark/40 px-4 py-2 font-body text-sm text-ink-soft transition-colors hover:bg-parchment disabled:opacity-50"
            >
              {t('tvs.check')}
            </button>
          </div>
        </Field>
        <div className="flex flex-wrap gap-x-8 gap-y-2">
          <Toggle
            checked={tv.enabled}
            label={t('tvs.enabled')}
            onChange={(v) => {
              onChange({ enabled: v })
            }}
          />
          <Toggle
            checked={tv.monitor_art_mode}
            label={t('tvs.monitorArt')}
            onChange={(v) => {
              onChange({ monitor_art_mode: v })
            }}
          />
        </div>
        {status !== null ? <StatusView status={status} /> : null}
      </div>
    </section>
  )
}
