import { useTranslation } from 'react-i18next'
import { api } from '@/api/client'
import { PageHeading } from '@/components/PageHeading'
import { Field } from '@/components/form/Field'
import { SaveButton } from '@/components/form/SaveButton'
import { Section } from '@/components/form/Section'
import { Toggle } from '@/components/form/Toggle'
import { controlClass } from '@/components/form/styles'
import { useEditableConfig } from '@/hooks/useEditableConfig'

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
      <PageHeading
        action={
          <SaveButton
            status={status}
            onClick={() => {
              save(config)
            }}
          />
        }
      >
        {t('pages.settings')}
      </PageHeading>

      <div className="flex flex-col gap-5">
        <Section title={t('settings.renderTitle')} description={t('settings.renderDesc')}>
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
      </div>
    </section>
  )
}
