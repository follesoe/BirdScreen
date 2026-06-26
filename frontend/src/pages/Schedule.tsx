import { useTranslation } from 'react-i18next'
import { api } from '@/api/client'
import { PageHeading } from '@/components/PageHeading'
import { Field } from '@/components/form/Field'
import { SaveButton } from '@/components/form/SaveButton'
import { Section } from '@/components/form/Section'
import { controlClass } from '@/components/form/styles'
import { WindowList } from '@/components/form/WindowList'
import { useEditableConfig } from '@/hooks/useEditableConfig'
import birdIcon from '@/assets/icons/bird.png'
import calendarIcon from '@/assets/icons/calendar.png'
import hourglassIcon from '@/assets/icons/hourglass.png'
import moonIcon from '@/assets/icons/moon.png'
import owlIcon from '@/assets/icons/owl.png'
import sunIcon from '@/assets/icons/sun.png'

export function Schedule() {
  const { t } = useTranslation()
  const { config, status, update, save } = useEditableConfig(api.schedule, api.saveSchedule)

  if (config === null) {
    return (
      <section>
        <PageHeading>{t('pages.schedule')}</PageHeading>
        <p className="text-ink-soft">{t('schedule.loading')}</p>
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
        {t('pages.schedule')}
      </PageHeading>

      <div className="flex flex-col gap-5">
        <Section
          title={t('schedule.dayTitle')}
          description={t('schedule.dayDesc')}
          icon={calendarIcon}
        >
          <Field label={t('schedule.dayReset')} hint={t('schedule.dayResetHint')} icon={moonIcon}>
            <input
              type="time"
              value={config.day_reset}
              onChange={(e) => {
                update('day_reset', e.target.value)
              }}
              className={controlClass}
            />
          </Field>
          <Field label={t('schedule.dailyCap')} hint={t('schedule.dailyCapHint')}>
            <input
              type="number"
              min={1}
              max={48}
              value={config.daily_cap}
              onChange={(e) => {
                update('daily_cap', Number(e.target.value))
              }}
              className={controlClass}
            />
          </Field>
        </Section>

        <Section
          title={t('schedule.cadenceTitle')}
          description={t('schedule.cadenceDesc')}
          icon={hourglassIcon}
        >
          <Field label={t('schedule.debounce')} hint={t('schedule.debounceHint')}>
            <input
              type="number"
              min={0}
              value={config.debounce_minutes}
              onChange={(e) => {
                update('debounce_minutes', Number(e.target.value))
              }}
              className={controlClass}
            />
          </Field>
          <Field label={t('schedule.spacing')} hint={t('schedule.spacingHint')}>
            <input
              type="number"
              min={0}
              value={config.min_spacing_minutes}
              onChange={(e) => {
                update('min_spacing_minutes', Number(e.target.value))
              }}
              className={controlClass}
            />
          </Field>
        </Section>

        <Section
          title={t('schedule.activeTitle')}
          description={t('schedule.activeDesc')}
          icon={sunIcon}
        >
          <Field label={t('schedule.weekdays')} icon={birdIcon}>
            <WindowList
              windows={config.weekday_windows}
              onChange={(w) => {
                update('weekday_windows', w)
              }}
            />
          </Field>
          <Field label={t('schedule.weekends')} icon={owlIcon}>
            <WindowList
              windows={config.weekend_windows}
              onChange={(w) => {
                update('weekend_windows', w)
              }}
            />
          </Field>
        </Section>
      </div>
    </section>
  )
}
