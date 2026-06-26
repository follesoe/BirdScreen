import { useTranslation } from 'react-i18next'
import { PageHero } from '@/components/PageHero'
import tvsHero from '@/assets/heroes/tvs.webp'

export function Tvs() {
  const { t } = useTranslation()
  return (
    <section className="max-w-2xl">
      <PageHero title={t('tvs.heading')} image={tvsHero} intro={t('tvs.intro')} />
      <div className="rounded-2xl border border-dashed border-bark/40 bg-parchment-deep/40 p-8 text-center font-body text-lg text-ink-soft">
        {t('tvs.comingSoon')}
      </div>
    </section>
  )
}
