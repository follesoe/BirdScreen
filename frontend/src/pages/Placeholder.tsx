import { useTranslation } from 'react-i18next'
import logoUrl from '@/assets/birdscreen-logo.webp'

interface PlaceholderProps {
  titleKey: string
}

export function Placeholder({ titleKey }: PlaceholderProps) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col items-center justify-center gap-5 py-24 text-center">
      <img
        src={logoUrl}
        alt={t('app.title')}
        className="h-36 w-36 rotate-2 rounded-2xl border border-bark/30 shadow-md"
      />
      <h2 className="font-display text-4xl text-ink">{t(titleKey)}</h2>
      <p className="max-w-sm font-body text-lg text-ink-soft">{t('pages.comingSoon')}</p>
    </div>
  )
}
