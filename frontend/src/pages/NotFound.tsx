import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import logoUrl from '@/assets/birdscreen-logo.webp'

export function NotFound() {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col items-center justify-center gap-5 py-24 text-center">
      <img
        src={logoUrl}
        alt={t('app.title')}
        className="h-44 w-44 -rotate-6 rounded-2xl border border-bark/30 shadow-md"
      />
      <h2 className="font-display text-5xl text-robin">{t('notFound.title')}</h2>
      <p className="max-w-md font-body text-lg text-ink-soft">{t('notFound.message')}</p>
      <Link
        to="/"
        className="rounded-full bg-robin px-6 py-2 font-body text-lg text-parchment transition-colors hover:bg-robin/90"
      >
        {t('notFound.back')}
      </Link>
    </div>
  )
}
