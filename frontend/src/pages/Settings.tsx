import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type BirdnetStatus, type StorageInfo } from '@/api/client'
import { PageHeading } from '@/components/PageHeading'
import { PageHero } from '@/components/PageHero'
import { StatusError } from '@/components/StatusError'
import { Field } from '@/components/form/Field'
import { SaveButton } from '@/components/form/SaveButton'
import { Section } from '@/components/form/Section'
import { Toggle } from '@/components/form/Toggle'
import { controlClass } from '@/components/form/styles'
import { useEditableConfig } from '@/hooks/useEditableConfig'
import settingsHero from '@/assets/heroes/settings.webp'
import aiIcon from '@/assets/icons/ai.png'
import birdnetIcon from '@/assets/icons/birdnet.png'
import storageIcon from '@/assets/icons/storage.png'
import weatherIcon from '@/assets/icons/weather.png'

const MODELS = ['gemini-3-pro-image', 'gemini-2.5-flash-image']
const SIZES = ['1K', '2K', '4K']

function BirdnetStatusLine({ status }: { status: BirdnetStatus | 'loading' }) {
  const { t } = useTranslation()
  if (status === 'loading') {
    return <p className="text-sm text-ink-soft">{t('settings.birdnetChecking')}</p>
  }
  if (!status.connected) {
    return (
      <div className="text-sm">
        <StatusError
          message={status.message ?? t('settings.birdnetError')}
          detail={status.detail}
        />
      </div>
    )
  }
  return <p className="text-sm text-sage">{t('settings.birdnetOk')}</p>
}

function fmtBytes(bytes: number): string {
  if (bytes >= 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${String(bytes)} B`
}

function StorageRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b border-bark/15 py-1.5 last:border-0">
      <dt className="font-body text-ink-soft">{label}</dt>
      <dd className="text-right font-body break-all text-ink">{value}</dd>
    </div>
  )
}

export function Settings() {
  const { t } = useTranslation()
  const { config, status, update, save } = useEditableConfig(api.settings, api.saveSettings)

  // Verify the BirdNET-Go connection on load (debounced re-check if the URL is edited).
  const birdnetUrl = config?.birdnet_url ?? ''
  const [birdnet, setBirdnet] = useState<BirdnetStatus | 'loading' | null>(null)
  const checkBirdnet = useCallback(() => {
    if (birdnetUrl === '') {
      setBirdnet(null)
      return
    }
    setBirdnet('loading')
    void api
      .birdnetStatus(birdnetUrl)
      .then((s) => {
        setBirdnet(s)
      })
      .catch(() => {
        setBirdnet(null)
      })
  }, [birdnetUrl])

  // Verify on load (and re-check, debounced, if the URL is edited).
  useEffect(() => {
    const id = setTimeout(checkBirdnet, 500)
    return () => {
      clearTimeout(id)
    }
  }, [checkBirdnet])

  const [storage, setStorage] = useState<StorageInfo | null>(null)
  useEffect(() => {
    void api
      .storage()
      .then((s) => {
        setStorage(s)
      })
      .catch(() => {
        // best-effort
      })
  }, [])

  if (config === null) {
    return (
      <section>
        <PageHeading>{t('pages.settings')}</PageHeading>
        <p className="text-ink-soft">{t('settings.loading')}</p>
      </section>
    )
  }

  return (
    <section className="max-w-2xl">
      <PageHero
        title={t('pages.settings')}
        image={settingsHero}
        intro={t('settings.intro')}
        action={
          <SaveButton
            status={status}
            onClick={() => {
              save(config)
            }}
          />
        }
      />

      <div className="flex flex-col gap-5">
        <Section
          title={t('settings.renderTitle')}
          description={t('settings.renderDesc')}
          icon={aiIcon}
        >
          <Field label={t('settings.model')}>
            <select
              value={config.model}
              onChange={(e) => {
                update('model', e.target.value)
              }}
              className={controlClass}
            >
              {MODELS.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t('settings.imageSize')}>
            <select
              value={config.image_size}
              onChange={(e) => {
                update('image_size', e.target.value)
              }}
              className={controlClass}
            >
              {SIZES.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </Field>
          <Toggle
            checked={config.upscale}
            label={t('settings.upscale')}
            onChange={(v) => {
              update('upscale', v)
            }}
          />
        </Section>

        <Section
          title={t('settings.birdnetTitle')}
          description={t('settings.birdnetDesc')}
          icon={birdnetIcon}
        >
          <Field label={t('settings.birdnetUrl')} hint={t('settings.birdnetUrlHint')}>
            <input
              type="url"
              value={config.birdnet_url}
              onChange={(e) => {
                update('birdnet_url', e.target.value)
              }}
              className={controlClass}
            />
          </Field>
          {birdnet !== null ? <BirdnetStatusLine status={birdnet} /> : null}
        </Section>

        <Section
          title={t('settings.weatherTitle')}
          description={t('settings.weatherDesc')}
          icon={weatherIcon}
        >
          <Toggle
            checked={config.use_weather}
            label={t('settings.useWeather')}
            onChange={(v) => {
              update('use_weather', v)
            }}
          />
        </Section>

        {storage !== null ? (
          <Section
            title={t('settings.storageTitle')}
            description={t('settings.storageDesc')}
            icon={storageIcon}
          >
            <dl className="flex flex-col">
              <StorageRow
                label={t('settings.storagePosters')}
                value={`${fmtBytes(storage.posters_bytes)} · ${String(storage.posters_count)} ${t('settings.storageFiles')}`}
              />
              <StorageRow
                label={t('settings.storageDatabase')}
                value={fmtBytes(storage.database_bytes)}
              />
              <StorageRow label={t('settings.storagePath')} value={storage.working_dir} />
            </dl>
          </Section>
        ) : null}
      </div>
    </section>
  )
}
