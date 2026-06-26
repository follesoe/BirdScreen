import { useTranslation } from 'react-i18next'
import { api } from '@/api/client'
import { PageHeading } from '@/components/PageHeading'
import { PageHero } from '@/components/PageHero'
import { Field } from '@/components/form/Field'
import { SaveButton } from '@/components/form/SaveButton'
import { Section } from '@/components/form/Section'
import { Toggle } from '@/components/form/Toggle'
import { controlClass } from '@/components/form/styles'
import { useEditableConfig } from '@/hooks/useEditableConfig'
import settingsHero from '@/assets/heroes/settings.webp'
import aiIcon from '@/assets/icons/ai.png'
import birdnetIcon from '@/assets/icons/birdnet.png'
import weatherIcon from '@/assets/icons/weather.png'

const MODELS = ['gemini-3-pro-image', 'gemini-2.5-flash-image']
const SIZES = ['1K', '2K', '4K']

export function Settings() {
  const { t } = useTranslation()
  const { config, status, update, save } = useEditableConfig(api.settings, api.saveSettings)

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
      </div>
    </section>
  )
}
