import { useState } from 'react'
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
  const rows: [string, string | null][] = [
    [t('tvs.statusName'), status.name],
    [t('tvs.statusModel'), status.model],
    [t('tvs.statusResolution'), status.resolution],
    [t('tvs.statusFirmware'), status.firmware],
    [t('tvs.statusArtMode'), status.art_mode ? t('tvs.yes') : t('tvs.no')],
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
    </dl>
  )
}

export function TvCard({ tv, onChange, onRemove }: TvCardProps) {
  const { t } = useTranslation()
  const [status, setStatus] = useState<TvStatus | 'loading' | null>(null)

  function check() {
    if (tv.ip === '') return
    setStatus('loading')
    void api
      .tvStatus(tv.ip)
      .then(setStatus)
      .catch(() => {
        setStatus(null)
      })
  }

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
              onClick={check}
              disabled={tv.ip === ''}
              className="rounded-full border border-bark/40 px-4 py-2 font-body text-sm text-ink-soft transition-colors hover:bg-parchment disabled:opacity-50"
            >
              {t('tvs.check')}
            </button>
          </div>
        </Field>
        <Toggle
          checked={tv.monitor_art_mode}
          label={t('tvs.monitorArt')}
          onChange={(v) => {
            onChange({ monitor_art_mode: v })
          }}
        />
        {status !== null ? <StatusView status={status} /> : null}
      </div>
    </section>
  )
}
