import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import logoUrl from '@/assets/birdscreen-logo.webp'
import treeUrl from '@/assets/sidebar-tree.webp'
import galleryIcon from '@/assets/icons/gallery.png'
import statusIcon from '@/assets/icons/status.png'
import logsIcon from '@/assets/icons/logs.png'
import settingsIcon from '@/assets/icons/settings.png'
import scheduleIcon from '@/assets/icons/schedule.png'
import tvsIcon from '@/assets/icons/tvs.png'

const NAV_ITEMS = [
  { to: '/', icon: galleryIcon, labelKey: 'nav.gallery' },
  { to: '/status', icon: statusIcon, labelKey: 'nav.status' },
  { to: '/logs', icon: logsIcon, labelKey: 'nav.logs' },
  { to: '/settings', icon: settingsIcon, labelKey: 'nav.settings' },
  { to: '/schedule', icon: scheduleIcon, labelKey: 'nav.schedule' },
  { to: '/tvs', icon: tvsIcon, labelKey: 'nav.tvs' },
] as const

const GITHUB_URL = 'https://github.com/follesoe/BirdScreen'

function linkClasses({ isActive }: { isActive: boolean }): string {
  const base = 'flex items-center gap-4 rounded-xl px-4 py-3 font-body text-2xl transition-colors'
  return isActive
    ? `${base} bg-robin/15 text-robin`
    : `${base} text-ink-soft hover:bg-parchment hover:text-ink`
}

interface SidebarProps {
  open: boolean
  onClose: () => void
}

export function Sidebar({ open, onClose }: SidebarProps) {
  const { t } = useTranslation()
  // On phones the sidebar is an off-canvas drawer; from md up it's a static column.
  const drawer = open ? 'translate-x-0' : '-translate-x-full'
  return (
    <>
      {open ? (
        <button
          type="button"
          aria-label={t('nav.close')}
          onClick={onClose}
          className="fixed inset-0 z-30 bg-ink/40 md:hidden"
        />
      ) : null}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-bark/25 bg-parchment-deep transition-transform md:static md:z-auto md:translate-x-0 ${drawer}`}
      >
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
          <div className="px-4 pt-5 pb-4">
            <img src={logoUrl} alt={t('app.title')} className="w-full" />
            <div className="mt-4 text-center">
              <p className="font-display text-4xl leading-none font-semibold text-ink">
                {t('app.title')}
              </p>
              <p className="font-body text-base text-robin italic">{t('app.subtitle')}</p>
            </div>
          </div>
          <nav className="flex flex-col gap-1 px-3">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                onClick={onClose}
                className={linkClasses}
              >
                <img src={item.icon} alt="" className="h-11 w-11 shrink-0" />
                {t(item.labelKey)}
              </NavLink>
            ))}
          </nav>
          {/* Tree of Norwegian birds, top tucked under the last menu item. It's cut off
              at the scroll area's bottom edge; scroll the sidebar to see the whole tree. */}
          <img
            src={treeUrl}
            alt=""
            aria-hidden="true"
            className="mt-6 w-full shrink-0 select-none"
          />
        </div>
        {/* Pinned footer: the playful tagline + a GitHub link. */}
        <div className="shrink-0 border-t border-bark/20 bg-parchment-deep px-4 py-3 text-center">
          <p className="font-body text-sm text-ink-soft italic">{t('app.tagline')}</p>
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noreferrer"
            className="mt-1.5 inline-flex items-center gap-1.5 font-body text-sm text-ink-soft transition-colors hover:text-robin"
          >
            <svg viewBox="0 0 16 16" aria-hidden="true" className="h-4 w-4" fill="currentColor">
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82A7.65 7.65 0 0 1 8 3.83c.68 0 1.36.09 2 .27 1.53-1.03 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
            </svg>
            {t('app.github')}
          </a>
        </div>
      </aside>
    </>
  )
}
