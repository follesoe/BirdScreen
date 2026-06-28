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
  { to: '/status', icon: statusIcon, labelKey: 'nav.status' },
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
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col overflow-y-auto border-r border-bark/25 bg-parchment-deep transition-transform md:static md:z-auto md:translate-x-0 ${drawer}`}
      >
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
            at the sidebar's bottom edge; scroll the sidebar to see the whole tree. */}
        <img src={treeUrl} alt="" aria-hidden="true" className="mt-6 w-full shrink-0 select-none" />
      </aside>
    </>
  )
}
