import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import logoUrl from '@/assets/birdscreen-logo.webp'
import galleryIcon from '@/assets/icons/gallery.png'
import logsIcon from '@/assets/icons/logs.png'
import settingsIcon from '@/assets/icons/settings.png'
import scheduleIcon from '@/assets/icons/schedule.png'
import tvsIcon from '@/assets/icons/tvs.png'

const NAV_ITEMS = [
  { to: '/', icon: galleryIcon, labelKey: 'nav.gallery' },
  { to: '/logs', icon: logsIcon, labelKey: 'nav.logs' },
  { to: '/settings', icon: settingsIcon, labelKey: 'nav.settings' },
  { to: '/schedule', icon: scheduleIcon, labelKey: 'nav.schedule' },
  { to: '/tvs', icon: tvsIcon, labelKey: 'nav.tvs' },
] as const

function linkClasses({ isActive }: { isActive: boolean }): string {
  const base = 'flex items-center gap-4 rounded-xl px-4 py-3 font-body text-2xl transition-colors'
  return isActive
    ? `${base} bg-robin/15 text-robin`
    : `${base} text-ink-soft hover:bg-parchment hover:text-ink`
}

export function Sidebar() {
  const { t } = useTranslation()
  return (
    <aside className="flex w-72 flex-col border-r border-bark/25 bg-parchment-deep">
      <div className="px-4 pt-5 pb-4">
        <img src={logoUrl} alt={t('app.title')} className="w-full" />
        <div className="-mt-1 text-center">
          <p className="font-display text-4xl leading-none font-semibold text-ink">
            {t('app.title')}
          </p>
          <p className="font-body text-base text-robin italic">{t('app.subtitle')}</p>
        </div>
      </div>
      <nav className="flex flex-1 flex-col gap-1 px-3">
        {NAV_ITEMS.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.to === '/'} className={linkClasses}>
            <img src={item.icon} alt="" className="h-11 w-11 shrink-0" />
            {t(item.labelKey)}
          </NavLink>
        ))}
      </nav>
      <p className="px-5 py-4 font-body text-xs text-ink-soft">{t('app.tagline')}</p>
    </aside>
  )
}
